import base64
from unittest.mock import patch

import httpx

from app import connectors


def test_selected_branch_filters_and_new_sources_share_the_sync_budget():
    requests = []
    source_items = []
    repo = {"full_name": "example/project", "default_branch": "main",
            "html_url": "https://github.com/example/project"}
    config = connectors._validate_github_config({
        "installation_id": "12",
        "repositories": ["example/project"],
        "branches": {"Example/Project": "release/current"},
        "sync_code": True,
        "sync_issues": False,
        "sync_pulls": False,
        "sync_commits": True,
        "sync_releases": True,
        "ignore_patterns": ["vendor/*"],
        "code_extensions": [".PY"],
        "max_items_per_sync": 10,
    })

    def handle(request):
        requests.append(request)
        endpoint = request.url.path.split("/repos/example/project/")[1]
        payloads = {
            "readme": {"path": "README.md", "content": base64.b64encode(b"readme").decode()},
            "commits": [{"sha": "abc", "commit": {"message": "Improve import\n\nDetails"}}],
            "releases": [
                {"id": 1, "draft": True, "tag_name": "private"},
                {"id": 2, "tag_name": "v1", "body": "Release notes"},
            ],
            "git/trees/release/current": {"tree": [
                {"path": "vendor/dependency.py", "type": "blob", "sha": "ignored"},
                {"path": "script.js", "type": "blob", "sha": "wrong-language"},
                {"path": "main.py", "type": "blob", "sha": "selected"},
            ]},
            "git/blobs/selected": {"encoding": "base64", "content": "cHJpbnQoMSk="},
        }
        return httpx.Response(200, json=payloads[endpoint])

    def store(_connector, _run, *item):
        source_items.append(item)
        return True

    counters = {"seen": 0, "changed": 0, "skipped": 0, "errors": 0}
    with httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handle)) as client:
        with patch.object(connectors, "_upsert_source_item", side_effect=store):
            connectors._sync_repo(client, {}, "run", repo, config, counters)
            assert counters == {"seen": 5, "changed": 5, "skipped": 0, "errors": 0}
            assert [item[1] for item in source_items] == [
                "repository", "readme", "commit", "release", "repository_file",
            ]
            assert requests[0].url.params["ref"] == "release/current"
            assert requests[1].url.params["sha"] == "release/current"
            assert b"/git/trees/release%2Fcurrent" in requests[3].url.raw_path
            assert source_items[-1][0] == "file:example/project:release/current:main.py"
            assert not any("private" in item[0] for item in source_items)

            requests.clear()
            counters["seen"] = 9
            connectors._sync_repo(client, {}, "run", repo, config, counters)
            assert counters["seen"] == 10
            assert requests == []
