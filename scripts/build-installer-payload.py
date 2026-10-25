#!/usr/bin/env python3
"""Build Engram container images once; package runtime files without local source builds."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CONTEXTS={'api':'backend','web':'web','minio-init':'ops/minio-init','db-backup':'ops/db-backup',
          'object-backup':'ops/object-backup','dr-monitor':'ops/dr-monitor'}
ALIASES={'worker':'api','connector-scheduler':'api'}


def image(service,commit):return f'engram/installer-{ALIASES.get(service,service)}:{commit}'


def runtime_compose(text,commit):
    service=None
    lines=[]
    for line in text.splitlines():
        if line and not line.startswith(' '):service=None
        match=re.fullmatch(r'  ([a-z][a-z0-9-]*):',line)
        if match:
            service=match[1]
            lines.append(line)
            if service in CONTEXTS or service in ALIASES:
                lines.extend([f'    image: {image(service,commit)}','    pull_policy: never'])
            continue
        if service in CONTEXTS or service in ALIASES:
            if re.match(r'    (image|build):',line):
                if line.strip()=='build:':raise ValueError('Update the packager for multiline build definitions')
                continue
        lines.append(line)
    result='\n'.join(lines)+'\n'
    if re.search(r'^    build:',result,re.M):raise ValueError('An application build was not packaged')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--architecture',choices=['amd64','arm64'],required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'dist/payload')
    args=parser.parse_args()
    output=args.output.resolve()
    if output.exists():raise ValueError('Choose a new payload output directory')
    output.mkdir(parents=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for name,context in CONTEXTS.items():
        subprocess.run(['docker','build','--pull','--platform','linux/'+args.architecture,'-t',image(name,commit),str(ROOT/context)],check=True)
    images=[image(name,commit) for name in CONTEXTS]
    archive=output/'images.tar.gz'
    process=subprocess.Popen(['docker','save',*images],stdout=subprocess.PIPE)
    with gzip.open(archive,'wb',compresslevel=1) as target:
        shutil.copyfileobj(process.stdout,target)
    process.stdout.close()
    if process.wait():raise RuntimeError('Docker image export failed')
    with archive.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    for name in ['.env.example','VERSION','LICENSE','install.sh']:
        shutil.copy2(ROOT/name,output/name)
    for name in ['db','gateway']:
        shutil.copytree(ROOT/name,output/name)
    (output/'docker-compose.yml').write_text(runtime_compose((ROOT/'docker-compose.yml').read_text(),commit),encoding='utf-8')
    (output/'BUILD.json').write_text(json.dumps({'format':1,'track':'v3.0','commit':commit,
        'source_version':(ROOT/'VERSION').read_text().strip(),'architecture':args.architecture,
        'images_sha256':digest,'images':images},indent=2)+'\n',encoding='utf-8')
    (output/'START-HERE.txt').write_text('Engram v3.0 installer development package\n\nOpen EngramInstaller to begin guided setup. Docker Desktop (Windows/macOS) or Docker Engine and Compose (Linux) must be running. Linux hosts can use install.sh to install prerequisites. Engram application images are prebuilt and included; third-party base services and optional AI models download during installation. No Python installation or local application compilation is required.\n\nFresh installations only: existing folders, configurations and matching Docker resources are preserved. Installer previews are unsigned; operating-system trust prompts may require an explicit Open/Run action. macOS Windows Docker Desktop deployment still requires real-device qualification.\n',encoding='utf-8')
    print('Created prebuilt payload:',output)


if __name__=='__main__':main()
