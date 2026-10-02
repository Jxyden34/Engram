from types import SimpleNamespace

from app import chatgpt_import, document_memory_import, oauth


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return _Rows(self.rows)


def test_safe_import_failures_do_not_expose_exception_details(monkeypatch, caplog):
    monkeypatch.setattr(chatgpt_import, "connect", lambda: _Connection([{"id": "chat"}]))
    monkeypatch.setattr(document_memory_import, "connect", lambda: _Connection([{"id": "document"}]))
    monkeypatch.setattr(chatgpt_import, "accept_candidate", lambda *_: (_ for _ in ()).throw(RuntimeError("database password")))
    monkeypatch.setattr(document_memory_import, "accept_candidate", lambda *_: (_ for _ in ()).throw(RuntimeError("database password")))

    chat_result = chatgpt_import.accept_safe_candidates("admin")
    document_result = document_memory_import.accept_safe("admin")

    assert chat_result["errors"] == [{"candidate_id": "chat", "error": "Unable to accept candidate"}]
    assert document_result["errors"] == [{"candidate_id": "document", "error": "Unable to accept candidate"}]
    assert "database password" not in str(chat_result)
    assert "database password" not in str(document_result)
    assert "database password" in caplog.text


def test_bulk_document_job_failure_does_not_expose_exception_details(monkeypatch, caplog):
    monkeypatch.setattr(document_memory_import, "list_ready_documents", lambda: [{"id": "document", "filename": "notes.pdf", "pending_candidates": 0}])
    monkeypatch.setattr(document_memory_import, "create_job", lambda *_: (_ for _ in ()).throw(RuntimeError("database password")))

    result = document_memory_import.create_jobs_for_all_ready("admin", None)

    assert result["error_items"] == [{"document_id": "document", "filename": "notes.pdf", "error": "Unable to create import job"}]
    assert "database password" not in str(result)
    assert "database password" in caplog.text


def test_cimd_fetch_requires_tls_1_2_or_newer(monkeypatch):
    class Context:
        minimum_version = None

        def wrap_socket(self, sock, *, server_hostname):
            assert server_hostname == "example.com"
            return sock

    class Socket:
        def sendall(self, _):
            pass

        def close(self):
            pass

    class Response:
        status = 200

        def __init__(self, _):
            pass

        def begin(self):
            pass

        def getheader(self, *_):
            return "application/json"

        def read(self, _):
            return b'{"client_id":"https://example.com/client"}'

    context = Context()
    monkeypatch.setattr(oauth, "settings", lambda: SimpleNamespace(oauth_cimd_timeout_seconds=1, oauth_cimd_max_kb=1))
    monkeypatch.setattr(oauth, "_resolve_public_host", lambda *_: ["93.184.216.34"])
    monkeypatch.setattr(oauth.socket, "create_connection", lambda *_args, **_kwargs: Socket())
    monkeypatch.setattr(oauth.ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(oauth.http.client, "HTTPResponse", Response)

    assert oauth._fetch_cimd("https://example.com/client")["client_id"] == "https://example.com/client"
    assert context.minimum_version is oauth.ssl.TLSVersion.TLSv1_2
