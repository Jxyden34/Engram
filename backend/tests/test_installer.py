from pathlib import Path
import base64
import runpy
import pytest

ROOT=Path(__file__).resolve().parents[2]
installer=runpy.run_path(str(ROOT/'install.py'))


def source(tmp_path,edition='community'):
    (tmp_path/'.env.example').write_bytes((ROOT/'.env.example').read_bytes())
    (tmp_path/'gateway').mkdir()
    (tmp_path/'gateway/Caddyfile').write_bytes((ROOT/'gateway/Caddyfile').read_bytes())
    (tmp_path/'backend/app').mkdir(parents=True)
    (tmp_path/'backend/app/EDITION').write_text(edition)
    return tmp_path


def test_installer_secrets_and_existing_config_are_preserved(tmp_path):
    root=source(tmp_path)
    values=installer['prepare'](root,'personal','memory.example.com','proxy',18080)
    secrets=[values[name] for name in ['POSTGRES_PASSWORD','REDIS_PASSWORD','MINIO_ROOT_PASSWORD','BACKUP_ENCRYPTION_PASSWORD']]
    assert len(set(secrets))==4 and all(len(value)>=40 for value in secrets)
    assert values['MINIO_SECRET_KEY']==values['MINIO_ROOT_PASSWORD']
    assert values['POSTGRES_PASSWORD'] in values['DATABASE_URL']
    assert '127.0.0.1:18080:8080' in (root/'docker-compose.install.yml').read_text()
    original=(root/'.env').read_bytes()
    with pytest.raises(ValueError,match='Existing installation'):installer['prepare'](root,'personal','other.example.com','https',8080)
    assert (root/'.env').read_bytes()==original


def test_installer_accepts_only_public_ed25519_keys(tmp_path):
    root=source(tmp_path,'commercial')
    private=tmp_path/'private.pem';private.write_text('-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----')
    with pytest.raises(ValueError,match='PUBLIC key'):installer['prepare'](root,'commercial','memory.example.com','https',8080,private)
    assert not (root/'.env').exists()
    public=tmp_path/'public.pem';public.write_text('-----BEGIN PUBLIC KEY-----\n'+base64.b64encode(bytes.fromhex('302a300506032b6570032100')+b'x'*32).decode()+'\n-----END PUBLIC KEY-----\n')
    installer['prepare'](root,'commercial','memory.example.com','https',8080,public)
    assert (root/'secrets/commercial-license-public.pem').read_text()==public.read_text()
    assert '80:80' in (root/'docker-compose.install.yml').read_text()
    assert 'memory.example.com, :8080 {' in (root/'gateway/Caddyfile.install').read_text()
