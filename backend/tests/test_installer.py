from pathlib import Path
import hashlib
import json
import runpy
import subprocess
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ET

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


def test_dmg_retries_only_transient_busy_errors():
    native=runpy.run_path(str(ROOT/'scripts/package-installer.py'))
    busy=subprocess.CompletedProcess(['hdiutil'],1,'','hdiutil: create failed - Resource busy')
    good=subprocess.CompletedProcess(['hdiutil'],0,'created','')
    with patch('subprocess.run',side_effect=[busy,good]) as run,patch('time.sleep') as sleep:
        native['create_dmg'](['hdiutil','create'])
        assert run.call_count==2
        sleep.assert_called_once_with(2)
    with patch('subprocess.run',return_value=subprocess.CompletedProcess(['hdiutil'],1,'','Invalid argument')) as run:
        with pytest.raises(subprocess.CalledProcessError):native['create_dmg'](['hdiutil','create'])
        assert run.call_count==1


def test_store_identity_requires_complete_metadata_and_store_version():
    store=runpy.run_path(str(ROOT/'scripts/package-installer-msix.py'))
    preview=store['identity']({'MS_STORE_VERSION':''})
    assert preview['identity_configured'] is False and preview['version']=='3.0.1.0'
    with pytest.raises(ValueError,match='all three'):
        store['identity']({'MS_STORE_IDENTITY_NAME':'Reserved.Engram'})
    for version in ['3.0.0.1','3.0.0','3.0.65536.0','3.0.x.0']:
        with pytest.raises(ValueError,match='Store version'):store['identity']({'MS_STORE_VERSION':version})
    info=store['identity']({'MS_STORE_IDENTITY_NAME':'Reserved.Engram','MS_STORE_PUBLISHER':'CN=A & B',
                            'MS_STORE_PUBLISHER_DISPLAY_NAME':'A & B <Dev>'})
    root=ET.fromstring(store['manifest'](info))
    ns=store['NS']
    assert root.find('{'+ns['']+'}Identity').attrib['Publisher']=='CN=A & B'
    assert root.find('{'+ns['']+'}Properties/{'+ns['']+'}PublisherDisplayName').text=='A & B <Dev>'
    app=root.find('{'+ns['']+'}Applications/{'+ns['']+'}Application')
    assert app.attrib['{'+ns['uap10']+'}TrustLevel']=='mediumIL'
    assert root.find('{'+ns['']+'}Capabilities/{'+ns['rescap']+'}Capability').attrib['Name']=='runFullTrust'


def test_msix_uses_physical_home_folder_for_docker_mounts(tmp_path):
    default=installer['default_directory']
    with patch.dict(default.__globals__,{'packaged_windows':lambda:True}),patch.object(Path,'home',return_value=tmp_path):
        assert default()==tmp_path/'Engram'
    with patch.dict(default.__globals__,{'packaged_windows':lambda:False}),patch.object(sys,'platform','win32'),patch.dict('os.environ',{'LOCALAPPDATA':str(tmp_path/'AppData/Local')}):
        assert default()==tmp_path/'AppData/Local/Engram'
