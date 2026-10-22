#!/usr/bin/env python3
"""Interactive host deployment. Uses only Python's standard library and Docker."""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit


def run(args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)


def ask(label,default=''):
    answer=input(f'{label}'+(f' [{default}]' if default else '')+': ').strip()
    return answer or default


def public_key(path):
    content=Path(path).read_text()
    if 'PRIVATE KEY' in content or not content.startswith('-----BEGIN PUBLIC KEY-----'):
        raise ValueError('Choose the issuer PUBLIC key, never its private key')
    raw=base64.b64decode(''.join(content.splitlines()[1:-1]),validate=True)
    if len(raw)!=44 or not raw.startswith(bytes.fromhex('302a300506032b6570032100')):
        raise ValueError('An Ed25519 issuer public key is required')
    return content


def prepare(root,edition,hostname,mode,port,key=None,ollama=None):
    if (root/'.env').exists() or (root/'docker-compose.install.yml').exists():
        raise ValueError('Existing installation configuration found. Use the upgrade guide; nothing was overwritten.')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?',hostname):
        raise ValueError('Enter a hostname without a scheme, port or path')
    if not 1024<=port<=65535:raise ValueError('Choose a local port between 1024 and 65535')
    if mode not in {'https','proxy'}:raise ValueError('Choose https or proxy')
    if edition not in {'personal','commercial'}:raise ValueError('Choose Personal or Commercial')
    marker=root/'backend/app/EDITION'
    if marker.exists() and marker.read_text().strip()!=('community' if edition=='personal' else 'commercial'):
        raise ValueError('This package belongs to another edition. Download the correct edition.')
    trust=public_key(key) if edition=='commercial' else None
    if ollama and (urlsplit(ollama).scheme not in {'http','https'} or not urlsplit(ollama).hostname or any(c.isspace() for c in ollama)):
        raise ValueError('Enter a valid Ollama HTTP or HTTPS URL')
    values=dict(line.split('=',1) for line in (root/'.env.example').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
    passwords={name:secrets.token_urlsafe(36) for name in ['POSTGRES_PASSWORD','REDIS_PASSWORD','MINIO_ROOT_PASSWORD','BACKUP_ENCRYPTION_PASSWORD']}
    values.update(passwords)
    values.update(PUBLIC_HOST=hostname,PUBLIC_ORIGIN='https://'+hostname,COOKIE_SECURE='true',
                  COMPOSE_PROJECT_NAME='engram-'+edition,MINIO_SECRET_KEY=passwords['MINIO_ROOT_PASSWORD'])
    values['MINIO_ROOT_USER']='engram-'+secrets.token_hex(6)
    values['MINIO_ACCESS_KEY']=values['MINIO_ROOT_USER']
    values['DATABASE_URL']=f"postgresql://{values['POSTGRES_USER']}:{passwords['POSTGRES_PASSWORD']}@db:5432/{values['POSTGRES_DB']}"
    values['REDIS_URL']=f"redis://:{passwords['REDIS_PASSWORD']}@redis:6379/0"
    if ollama:values['OLLAMA_URL']=ollama
    config='\n'.join(f'{key}={value}' for key,value in values.items())+'\n'
    fd=os.open(root/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as handle:handle.write(config)
    if trust:
        directory=root/'secrets';directory.mkdir(exist_ok=True)
        (directory/'commercial-license-public.pem').write_text(trust)
        (directory/'commercial-license-public.pem').chmod(0o644)
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


def api(port,path,data=None,token=None,method=None):
    request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,
        data=json.dumps(data).encode() if data is not None else None,method=method,
        headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
    with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--edition',choices=['personal','commercial'])
    parser.add_argument('--host')
    parser.add_argument('--mode',choices=['https','proxy'])
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--public-key',type=Path)
    parser.add_argument('--non-interactive',action='store_true')
    parser.add_argument('--skip-models',action='store_true')
    args=parser.parse_args()
    if sys.platform!='linux' or os.geteuid()!=0:raise ValueError('Run on your Linux host as root: sudo python3 install.py')
    run(['docker','info'],stdout=subprocess.DEVNULL)
    version=subprocess.check_output(['docker','compose','version','--short'],text=True).strip().lstrip('v')
    numbers=tuple(int(p) for p in re.match(r'(\d+)\.(\d+)\.(\d+)',version).groups())
    if numbers<(2,24,4):raise ValueError('Docker Compose 2.24.4 or newer is required')
    source=Path(__file__).resolve().parent
    packaged=json.loads((source/'BUILD.json').read_text())['edition'] if (source/'BUILD.json').exists() else None
    edition=(args.edition or packaged or ask('Edition: personal or commercial','personal')).lower()
    hostname=args.host or ask('Public domain (point DNS to this host first)')
    mode=(args.mode or ask('HTTPS automatically, or use an existing proxy/tunnel? Enter https or proxy','https')).lower()
    target=(args.directory or Path(ask('Install directory','/opt/engram'))).resolve()
    if target.exists():raise ValueError(f'{target} already exists. Choose an empty new directory; existing installations are preserved.')
    if source in target.parents:raise ValueError('Choose an installation directory outside the downloaded installer source')
    username=os.environ.get('ENGRAM_INSTALL_ADMIN_USER') or ask('Administrator username','admin')
    password=os.environ.get('ENGRAM_INSTALL_ADMIN_PASSWORD') or getpass.getpass('Administrator password (12+ characters): ')
    if not re.fullmatch(r'\S{3,254}',username) or not 12<=len(password)<=256:raise ValueError('Use a username of 3–254 characters and a password of 12–256 characters')
    if not args.non_interactive and password!=getpass.getpass('Repeat administrator password: '):raise ValueError('Passwords do not match')
    key=args.public_key
    if edition=='commercial' and not key:key=Path(ask('Path to the issuer PUBLIC key file'))
    ollama=None
    if not args.non_interactive and ask('Use built-in Ollama?','yes').lower() in {'n','no'}:ollama=ask('Existing Ollama server URL')
    project='engram-'+edition
    for resource in ['container','volume']:
        found=subprocess.check_output(['docker',resource,'ls','-aq' if resource=='container' else '-q','--filter',f'label=com.docker.compose.project={project}'],text=True)
        if found.strip():raise ValueError(f'Existing {project} Docker resources found. Use the upgrade guide.')
    for port in [args.port]+([80,443] if mode=='https' else []):
        with socket.socket() as test:test.bind(('0.0.0.0',port))
    print(f'\nInstall {edition.title()} at {target}; domain {hostname}; access {mode}.')
    if not args.non_interactive and ask('Build and deploy now?','yes').lower() not in {'y','yes'}:return
    def ignore(directory,names):
        relative=Path(directory).relative_to(source).as_posix()
        excluded={'.git','node_modules','.next','__pycache__','.env','.temp','dist','backups','data','secrets','imports','.venv','venv'}
        if relative=='backend':excluded.update({'owner','tests'})
        if relative=='backend/scripts':excluded.add('commercial_license.py')
        if relative=='backend/app' and edition=='personal':excluded.add('commercial')
        if relative=='.':excluded.add('docker-compose.licence-owner.yml')
        return set(names)&excluded
    shutil.copytree(source,target,ignore=ignore)
    values=prepare(target,edition,hostname,mode,args.port,key,ollama)
    edition_file=target/f'docker-compose.{"community" if edition=="personal" else "commercial"}.yml'
    if not edition_file.exists():edition_file=target/'docker-compose.override.yml'
    compose=['docker','compose','--project-directory',str(target),'-f',str(target/'docker-compose.yml'),'-f',str(edition_file),'-f',str(target/'docker-compose.install.yml')]
    run(compose+['config','--quiet'])
    run(compose+['build'])
    run(compose+['up','-d','--wait','--wait-timeout','240'])
    create="import json,sys; from app.database import connect; from app.security import hash_password; data=json.load(sys.stdin); conn=connect(); conn.execute('SELECT pg_advisory_xact_lock(370006)'); assert not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone(), 'Account already exists'; conn.execute('INSERT INTO users(username,password_hash,is_admin) VALUES(%s,%s,true)',(data['username'],hash_password(data['password']))); conn.commit(); print('Administrator created')"
    run(compose+['exec','-T','api','python','-c',create],input=json.dumps({'username':username,'password':password}),text=True)
    health=api(args.port,'/health');print('Healthy:',health['version'])
    if edition=='commercial':
        status=api(args.port,'/api/v1/edition');print('Installation ID:',status['installation_id'])
        licence='' if args.non_interactive else getpass.getpass('Commercial key (blank to activate later in the web setup): ')
        if licence:
            token=api(args.port,'/api/v1/mobile/login',{'username':username,'password':password})['token']
            api(args.port,'/api/v1/license',{'mode':'commercial','license_key':licence},token,'PUT')
            api(args.port,'/api/v1/mobile/logout',{},token)
            print('Commercial licence activated')
    if not args.skip_models and not ollama and (not args.non_interactive and ask('Download the embedding and chat models now? Several GB may be required.','yes').lower() in {'y','yes'}):
        for model in [values['EMBEDDING_MODEL'],values['CHAT_MODEL']]:run(compose+['exec','-T','ollama','ollama','pull',model])
    print('\nDeployment is healthy. Administrator:',username)
    print('Open: https://'+hostname+('/setup' if edition=='commercial' else '/login'))
    print('Configuration:',target/'.env')
    print('If using an existing proxy/tunnel, forward it to http://127.0.0.1:'+str(args.port))
    if mode=='https':
        try:
            with urllib.request.urlopen('https://'+hostname+'/health',timeout=30) as response:assert response.status==200
            print('Public HTTPS verified')
        except Exception:print('Local deployment passed; public HTTPS is not verified. Check DNS, inbound ports 80/443 and gateway logs.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        print('Setup stopped:',error,file=sys.stderr)
        print('Existing data was not removed. Retain the install directory for diagnosis or recovery.',file=sys.stderr)
        raise SystemExit(1)
