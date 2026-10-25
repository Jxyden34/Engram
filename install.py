#!/usr/bin/env python3
"""Engram setup wizard. Adapted from draft PR #85 for prebuilt, native packages."""
import argparse
import csv
import ctypes
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit
import webbrowser


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def ask(label, default=''):
    answer=input(label+(f' [{default}]' if default else '')+': ').strip()
    return answer or default


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    if sys.platform=='win32':
        row=next(csv.reader(subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True).splitlines()))
        sid=row[1]
        if not re.fullmatch(r'S-\d+(?:-\d+)+',sid):raise ValueError('Cannot determine the current Windows security identity')
        run(['icacls',str(path),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],stdout=subprocess.DEVNULL)


def prepare(root, hostname, mode, port, ollama=None):
    if (root/'.env').exists() or (root/'docker-compose.install.yml').exists():
        raise ValueError('Existing installation configuration found; nothing was overwritten')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?',hostname):
        raise ValueError('Enter a hostname without a scheme, port or path')
    if not 1024<=port<=65535:raise ValueError('Choose a port between 1024 and 65535')
    if mode not in {'local','proxy','https'}:raise ValueError('Choose local, proxy or https')
    if mode=='local' and hostname!='localhost':raise ValueError('Local HTTP setup binds only to localhost')
    if ollama:
        url=urlsplit(ollama)
        if url.scheme not in {'http','https'} or not url.hostname or any(c.isspace() for c in ollama):
            raise ValueError('Enter a valid Ollama HTTP or HTTPS URL')
    values=dict(line.split('=',1) for line in (root/'.env.example').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
    passwords={name:secrets.token_urlsafe(36) for name in ['POSTGRES_PASSWORD','REDIS_PASSWORD','MINIO_ROOT_PASSWORD','BACKUP_ENCRYPTION_PASSWORD']}
    values.update(passwords)
    values.update(PUBLIC_HOST=hostname,PUBLIC_ORIGIN=f'http://localhost:{port}' if mode=='local' else 'https://'+hostname,
                  COOKIE_SECURE='false' if mode=='local' else 'true',COMPOSE_PROJECT_NAME='engram-installer',
                  MINIO_ROOT_USER='engram-'+secrets.token_hex(6),MINIO_SECRET_KEY=passwords['MINIO_ROOT_PASSWORD'])
    values['MINIO_ACCESS_KEY']=values['MINIO_ROOT_USER']
    values['DATABASE_URL']=f"postgresql://{values['POSTGRES_USER']}:{passwords['POSTGRES_PASSWORD']}@db:5432/{values['POSTGRES_DB']}"
    values['REDIS_URL']=f"redis://:{passwords['REDIS_PASSWORD']}@redis:6379/0"
    if ollama:values['OLLAMA_URL']=ollama
    fd=os.open(root/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as handle:handle.write('\n'.join(f'{key}={value}' for key,value in values.items())+'\n')
    gateway=(root/'gateway/Caddyfile').read_text()
    if mode=='https':gateway=gateway.replace(':8080 {',hostname+', :8080 {',1)
    (root/'gateway/Caddyfile.install').write_text(gateway)
    ports=[f'127.0.0.1:{port}:8080']+(['80:80','443:443','443:443/udp'] if mode=='https' else [])
    override='services:\n  gateway:\n    ports: !override\n'+''.join(f'      - "{value}"\n' for value in ports)
    override+='    volumes:\n      - ./gateway/Caddyfile.install:/etc/caddy/Caddyfile:ro\n      - install_caddy_data:/data\n      - install_caddy_config:/config\n'
    if ollama:override+='  ollama:\n    profiles: [local-ai]\n'
    override+='volumes:\n  install_caddy_data:\n  install_caddy_config:\n'
    (root/'docker-compose.install.yml').write_text(override)
    return values


def payload():
    base=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent/'dist'
    return base/'payload'


def verify_payload(source):
    build=json.loads((source/'BUILD.json').read_text())
    if build.get('format')!=1:raise ValueError('Unsupported installer package')
    archive=source/'images.tar.gz'
    with archive.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    if digest!=build['images_sha256']:raise ValueError('Container image checksum mismatch; download the package again')
    return build


def packaged_windows():
    if sys.platform!='win32':return False
    length=ctypes.c_uint32(0)
    return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length),None)==122


def default_directory():
    # Docker runs outside MSIX; AppData redirection would hide bind-mount files from it.
    if packaged_windows():return Path.home()/'Engram'
    if sys.platform=='win32':return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Engram'
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/Engram'
    return Path('/opt/engram') if os.geteuid()==0 else Path.home()/'.local/share/engram'


def require_local_docker():
    if not shutil.which('docker'):
        raise ValueError('Install and start Docker Desktop (Windows/Mac) or Docker Engine with Compose (Linux), then reopen this installer: https://docs.docker.com/get-started/get-docker/')
    endpoint=os.environ.get('DOCKER_HOST')
    if not endpoint or os.environ.get('DOCKER_CONTEXT'):
        context=json.loads(subprocess.check_output(['docker','context','inspect'],text=True))[0]
        endpoint=context['Endpoints']['docker']['Host']
    if not (endpoint.startswith(('unix://','npipe://')) or re.fullmatch(r'tcp://(?:127\.0\.0\.1|localhost):\d+',endpoint)):
        raise ValueError('Select a local Docker context. This installer will not deploy to a remote Docker host.')
    info=json.loads(subprocess.check_output(['docker','info','--format','{{json .}}'],text=True))
    if info.get('OSType')!='linux':raise ValueError('Switch Docker Desktop to Linux containers')
    match=re.match(r'v?(\d+)\.(\d+)\.(\d+)',subprocess.check_output(['docker','compose','version','--short'],text=True).strip())
    if not match or tuple(map(int,match.groups()))<(2,24,4):raise ValueError('Docker Compose 2.24.4 or newer is required')
    return {'x86_64':'amd64','aarch64':'arm64'}.get(info['Architecture'],info['Architecture'])


def self_test(source):
    build=verify_payload(source)
    with tempfile.TemporaryDirectory(prefix='engram-installer-test-') as directory:
        root=Path(directory)/'configuration'
        private_directory(root)
        shutil.copy(source/'.env.example',root/'.env.example')
        shutil.copytree(source/'gateway',root/'gateway')
        values=prepare(root,'localhost','local',18080)
        assert values['PUBLIC_ORIGIN']=='http://localhost:18080' and values['COOKIE_SECURE']=='false'
        assert len({values[k] for k in ['POSTGRES_PASSWORD','REDIS_PASSWORD','MINIO_ROOT_PASSWORD','BACKUP_ENCRYPTION_PASSWORD']})==4
        before=(root/'.env').read_bytes()
        try:prepare(root,'localhost','local',18081)
        except ValueError:pass
        else:raise AssertionError('Existing configuration was overwritten')
        assert before==(root/'.env').read_bytes()
    print(json.dumps({'self_test':'passed','platform':platform.system(),'architecture':build['architecture'],'commit':build['commit']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--host')
    parser.add_argument('--mode',choices=['local','proxy','https'])
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--non-interactive',action='store_true')
    parser.add_argument('--skip-models',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    source=payload()
    if args.self_test:return self_test(source)
    build=verify_payload(source)
    architecture=require_local_docker()
    if architecture!=build['architecture']:raise ValueError('Download the package matching your Docker engine architecture')
    mode=args.mode or ('local' if args.non_interactive else ask('Access: local, proxy or https','local').lower())
    hostname=args.host or ('localhost' if mode=='local' else ask('Public domain'))
    target=(args.directory or (default_directory() if args.non_interactive else Path(ask('Install directory',str(default_directory()))))).expanduser().resolve()
    if target.exists():raise ValueError(f'{target} already exists. Choose a new directory; existing installations are preserved.')
    if source==target or source in target.parents:raise ValueError('Choose a directory outside the downloaded package')
    username=os.environ.get('ENGRAM_INSTALL_ADMIN_USER') or ask('Administrator username','admin')
    password=os.environ.get('ENGRAM_INSTALL_ADMIN_PASSWORD') or getpass.getpass('Administrator password (12+ characters): ')
    if not re.fullmatch(r'\S{3,254}',username) or not 12<=len(password)<=256:raise ValueError('Use a username of 3–254 characters and a password of 12–256 characters')
    if not args.non_interactive and password!=getpass.getpass('Repeat password: '):raise ValueError('Passwords do not match')
    for resource in ['container','volume']:
        found=subprocess.check_output(['docker',resource,'ls','-aq' if resource=='container' else '-q','--filter','label=com.docker.compose.project=engram-installer'],text=True)
        if found.strip():raise ValueError('Existing Engram installer resources found. Use the upgrade guide.')
    for port in [args.port]+([80,443] if mode=='https' else []):
        with socket.socket() as test:test.bind(('127.0.0.1',port))
    print(f'Install Engram at {target}; source {build["commit"][:12]}; access {mode}.')
    if not args.non_interactive and ask('Install now?','yes').lower() not in {'y','yes'}:return
    private_directory(target)
    shutil.copytree(source,target,dirs_exist_ok=True)
    values=prepare(target,hostname,mode,args.port)
    compose=['docker','compose','--project-directory',str(target),'-f',str(target/'docker-compose.yml'),'-f',str(target/'docker-compose.install.yml')]
    run(compose+['config','--quiet'])
    run(['docker','load','--input',str(target/'images.tar.gz')])
    run(compose+['up','-d','--no-build','--wait','--wait-timeout','300'])
    create="import json,sys; from app.database import connect; from app.security import hash_password; data=json.load(sys.stdin); conn=connect(); conn.execute('SELECT pg_advisory_xact_lock(300001)'); assert not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone(), 'Account already exists'; conn.execute('INSERT INTO users(username,password_hash,is_admin) VALUES(%s,%s,true)',(data['username'],hash_password(data['password']))); conn.commit(); print('Administrator created')"
    run(compose+['exec','-T','api','python','-c',create],input=json.dumps({'username':username,'password':password}),text=True)
    with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health',timeout=30) as response:
        assert json.load(response)['version']==build['source_version']
    if not args.skip_models and (not args.non_interactive and ask('Download AI models now? Several GB will be downloaded.','yes').lower() in {'y','yes'}):
        for model in [values['EMBEDDING_MODEL'],values['CHAT_MODEL']]:run(compose+['exec','-T','ollama','ollama','pull',model])
    url=values['PUBLIC_ORIGIN']+'/login'
    print('Engram is ready:',url)
    print('Configuration and data:',target)
    if not args.non_interactive:webbrowser.open(url)


if __name__=='__main__':
    try:
        if getattr(sys,'frozen',False) and sys.platform=='linux' and not sys.stdin.isatty() and not {'--non-interactive','--self-test','--help'}&set(sys.argv):
            for terminal,separator in [('x-terminal-emulator','-e'),('gnome-terminal','--'),('konsole','-e'),('xterm','-e')]:
                if shutil.which(terminal):
                    run([terminal,separator,sys.executable])
                    raise SystemExit(0)
            raise ValueError('Open this installer from a terminal on this Linux desktop')
        main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print('Setup stopped:',error,file=sys.stderr)
        print('Existing data was not deleted. Retain the installation folder for recovery.',file=sys.stderr)
        raise SystemExit(1)
    finally:
        if getattr(sys,'frozen',False) and sys.stdin.isatty() and '--non-interactive' not in sys.argv and '--self-test' not in sys.argv:
            input('Press Enter to close…')
