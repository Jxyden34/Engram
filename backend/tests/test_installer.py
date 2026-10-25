from pathlib import Path
import hashlib
import json
import runpy
from unittest.mock import patch

import pytest

ROOT=Path(__file__).resolve().parents[2]
installer=runpy.run_path(str(ROOT/'install.py'))
packager=runpy.run_path(str(ROOT/'scripts/build-installer-payload.py'))


def source(tmp_path):
    (tmp_path/'.env.example').write_bytes((ROOT/'.env.example').read_bytes())
    (tmp_path/'gateway').mkdir()
    (tmp_path/'gateway/Caddyfile').write_bytes((ROOT/'gateway/Caddyfile').read_bytes())
    return tmp_path


def test_installer_generates_distinct_secrets_local_binding_and_preserves_existing_config(tmp_path):
    root=source(tmp_path)
    values=installer['prepare'](root,'localhost','local',18080)
    assert values['PUBLIC_ORIGIN']=='http://localhost:18080' and values['COOKIE_SECURE']=='false'
    assert len({values[k] for k in ['POSTGRES_PASSWORD','REDIS_PASSWORD','MINIO_ROOT_PASSWORD','BACKUP_ENCRYPTION_PASSWORD']})==4
    assert '127.0.0.1:18080:8080' in (root/'docker-compose.install.yml').read_text()
    before=(root/'.env').read_bytes()
    with pytest.raises(ValueError,match='Existing installation'):
        installer['prepare'](root,'localhost','local',18081)
    assert before==(root/'.env').read_bytes()


def test_installer_rejects_remote_http_or_injected_configuration_before_writing_secrets(tmp_path):
    root=source(tmp_path)
    for host,mode,port in [('remote.example','local',8080),('host\nSECRET=value','proxy',8080),('localhost','local',80)]:
        with pytest.raises(ValueError):installer['prepare'](root,host,mode,port)
        assert not (root/'.env').exists()


def test_image_archive_checksum_and_runtime_compose_without_builds(tmp_path):
    archive=tmp_path/'images.tar.gz';archive.write_bytes(b'container export')
    manifest={'format':1,'images_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (tmp_path/'BUILD.json').write_text(json.dumps(manifest))
    assert installer['verify_payload'](tmp_path)==manifest
    archive.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='checksum'):installer['verify_payload'](tmp_path)
    compose=packager['runtime_compose']((ROOT/'docker-compose.yml').read_text(),'a'*40)
    assert '    build:' not in compose
    assert compose.count('image: engram/installer-api:')==3
    assert 'pull_policy: never' in compose


def test_remote_docker_context_is_refused():
    with patch('shutil.which',return_value='/usr/bin/docker'),patch.dict('os.environ',{'DOCKER_HOST':'ssh://remote-host','DOCKER_CONTEXT':''}):
        with pytest.raises(ValueError,match='remote Docker host'):installer['require_local_docker']()
