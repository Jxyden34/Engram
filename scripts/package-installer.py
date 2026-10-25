#!/usr/bin/env python3
"""Compile the wizard on its native OS and make a distributable package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import runpy
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def create_dmg(command):
    # macOS disk-image/Spotlight locks are transient; never retry other packaging errors.
    for attempt in range(4):
        result=subprocess.run(command,capture_output=True,text=True)
        print(result.stdout or '',end='')
        print(result.stderr or '',end='',file=sys.stderr)
        if result.returncode==0:return
        if 'Resource busy' not in (result.stdout or '')+(result.stderr or '') or attempt==3:
            result.check_returncode()
        time.sleep(2**(attempt+1))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload',type=Path,default=ROOT/'dist/payload')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/packages')
    args=parser.parse_args()
    payload=args.payload.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    build=json.loads((payload/'BUILD.json').read_text())
    platform={'win32':'windows','darwin':'macos','linux':'linux'}[sys.platform]
    version=os.environ.get('GITHUB_REF_NAME','')
    if not version.startswith('v3.'):version='v3.0-dev-'+build['commit'][:12]
    if not all(c.isalnum() or c in '.-_' for c in version):raise ValueError('Invalid package version')
    work=output/'native-build';dist=work/'dist'
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
                    '--name','EngramInstaller','--distpath',str(dist),'--workpath',str(work/'work'),
                    '--specpath',str(work),'--add-data',str(payload)+':payload',str(ROOT/'install.py')],check=True)
    runtime=dist/'EngramInstaller'
    executable=runtime/('EngramInstaller.exe' if platform=='windows' else 'EngramInstaller')
    subprocess.run([str(executable),'--self-test'],check=True)
    name=f'engram-{version}-{platform}-{build["architecture"]}'
    if platform=='windows':
        target=output/(name+'.zip')
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            for path in sorted(runtime.rglob('*')):
                if path.is_file():archive.write(path,Path('EngramInstaller')/path.relative_to(runtime))
        store=runpy.run_path(str(ROOT/'scripts/package-installer-msix.py'))
        store['package'](runtime,output,name)
    elif platform=='linux':
        target=output/(name+'.tar.gz')
        with tarfile.open(target,'w:gz',compresslevel=1) as archive:archive.add(runtime,arcname='EngramInstaller')
    else:
        folder=work/'dmg';app=folder/'Engram Installer.app';contents=app/'Contents'
        (contents/'MacOS').mkdir(parents=True)
        (contents/'Resources').mkdir()
        shutil.copytree(runtime,contents/'Resources/runtime',symlinks=True)
        with (contents/'Info.plist').open('wb') as handle:
            plistlib.dump({'CFBundleName':'Engram Installer','CFBundleIdentifier':'tech.hindley.engram.installer',
                          'CFBundleExecutable':'launch','CFBundlePackageType':'APPL','CFBundleVersion':'1',
                          'CFBundleShortVersionString':'3.0','NSHighResolutionCapable':True},handle)
        launcher=contents/'MacOS/launch'
        launcher.write_text('#!/bin/sh\nDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec open -a Terminal "$DIR/../Resources/install.command"\n')
        launcher.chmod(0o755)
        command=contents/'Resources/install.command'
        command.write_text('#!/bin/sh\nDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$DIR/runtime/EngramInstaller"\n')
        command.chmod(0o755)
        target=output/(name+'.dmg')
        create_dmg(['hdiutil','create','-volname','Engram Installer','-srcfolder',str(folder),'-format','UDZO','-ov',str(target)])
    with target.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    target.with_name(target.name+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print('Created native package:',target)


if __name__=='__main__':main()
