#!/usr/bin/env python3
"""Prepare an unsigned MSIX for Microsoft Store signing after account/certification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NS={'':'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
    'uap':'http://schemas.microsoft.com/appx/manifest/uap/windows10',
    'uap10':'http://schemas.microsoft.com/appx/manifest/uap/windows10/10',
    'rescap':'http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities'}


def identity(environ):
    names=('MS_STORE_IDENTITY_NAME','MS_STORE_PUBLISHER','MS_STORE_PUBLISHER_DISPLAY_NAME')
    values=[environ.get(key,'').strip() for key in names]
    configured=all(values)
    if any(values) and not configured:raise ValueError('Configure all three Microsoft Store identity values, or leave all unset for preview')
    name,publisher,display=values if configured else ('JaydenHindley.Engram.Preview','CN=EngramPreview','Engram Preview')
    if not re.fullmatch(r'[A-Za-z0-9.-]{3,50}',name):raise ValueError('Invalid Store package identity name')
    if not publisher.startswith('CN=') or len(publisher)>8192:raise ValueError('Use the exact Publisher value from Partner Center')
    if not display or len(display)>256 or any(ord(c)<32 for c in publisher+display):raise ValueError('Invalid Store publisher display name')
    version=environ.get('MS_STORE_VERSION') or (ROOT/'VERSION').read_text().strip()+'.0'
    parts=version.split('.')
    if len(parts)!=4 or any(not p.isascii() or not p.isdigit() or int(p)>65535 for p in parts) or parts[-1]!='0':
        raise ValueError('Store version must be four numbers, each 0–65535, with a final .0')
    return {'name':name,'publisher':publisher,'display_name':display,'version':version,'identity_configured':configured}


def manifest(info):
    for prefix,uri in NS.items():ET.register_namespace(prefix,uri)
    def tag(name,prefix=''):return '{'+NS[prefix]+'}'+name
    package=ET.Element(tag('Package'),{'IgnorableNamespaces':'uap uap10 rescap'})
    ET.SubElement(package,tag('Identity'),{'Name':info['name'],'Publisher':info['publisher'],
                                       'Version':info['version'],'ProcessorArchitecture':'x64'})
    properties=ET.SubElement(package,tag('Properties'))
    for key,value in [('DisplayName','Engram Setup' if info['identity_configured'] else 'Engram Setup Preview'),
                      ('PublisherDisplayName',info['display_name']),('Logo','Assets/StoreLogo.png')]:
        ET.SubElement(properties,tag(key)).text=value
    dependencies=ET.SubElement(package,tag('Dependencies'))
    ET.SubElement(dependencies,tag('TargetDeviceFamily'),{'Name':'Windows.Desktop','MinVersion':'10.0.19041.0','MaxVersionTested':'10.0.26100.0'})
    resources=ET.SubElement(package,tag('Resources'));ET.SubElement(resources,tag('Resource'),{'Language':'en-us'})
    applications=ET.SubElement(package,tag('Applications'))
    app=ET.SubElement(applications,tag('Application'),{'Id':'EngramSetup','Executable':'EngramInstaller.exe',
        'EntryPoint':'Windows.FullTrustApplication',tag('RuntimeBehavior','uap10'):'packagedClassicApp',tag('TrustLevel','uap10'):'mediumIL'})
    ET.SubElement(app,tag('VisualElements','uap'),{'DisplayName':'Engram Setup','Description':'Set up a private Engram server on this computer. Docker Desktop with Linux containers is required.',
        'BackgroundColor':'#090a0c','Square150x150Logo':'Assets/Square150x150Logo.png','Square44x44Logo':'Assets/Square44x44Logo.png'})
    capabilities=ET.SubElement(package,tag('Capabilities'))
    ET.SubElement(capabilities,tag('Capability','rescap'),{'Name':'runFullTrust'})
    return ET.tostring(package,encoding='utf-8',xml_declaration=True)


def sdk_tool(name):
    found=shutil.which(name)
    if found:return found
    root=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Windows Kits/10/bin'
    tools=sorted(root.glob('*/x64/'+name),reverse=True)
    if not tools:raise ValueError(f'Install the Windows SDK: {name} is required')
    return str(tools[0])


def package(runtime,output,name):
    if sys.platform!='win32':raise ValueError('Build MSIX with the Windows SDK on a Windows runner')
    info=identity(os.environ)
    staging=output/'native-build/msix-root'
    shutil.copytree(runtime,staging)
    subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/installer-store-assets.ps1'),
                    '-Source',str(ROOT/'web/public/icon-512.png'),'-Destination',str(staging/'Assets')],check=True)
    (staging/'AppxManifest.xml').write_bytes(manifest(info))
    target=output/(name+'-store-submission.msix')
    tool=sdk_tool('makeappx.exe')
    subprocess.run([tool,'pack','/d',str(staging),'/p',str(target),'/o'],check=True)
    unpacked=output/'native-build/msix-validation'
    subprocess.run([tool,'unpack','/p',str(target),'/d',str(unpacked),'/o'],check=True)
    if (unpacked/'AppxSignature.p7x').exists():raise ValueError('Store submission must not contain a development test signature')
    packaged=ET.parse(unpacked/'AppxManifest.xml').getroot().find('{'+NS['']+'}Identity')
    if packaged.attrib['Name']!=info['name'] or packaged.attrib['Publisher']!=info['publisher']:raise ValueError('MSIX identity changed while packaging')
    subprocess.run([str(unpacked/'EngramInstaller.exe'),'--self-test'],check=True)
    with target.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    target.with_name(target.name+'.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    (output/(name+'-store-identity.json')).write_text(json.dumps({**info,'unsigned':True,'sdk_pack_unpack_validated':True,
        'requires_store_certification':True,'docker_desktop_device_qualification':'pending',
        'note':'Microsoft signs only after accepted Store submission. Preview identity values must be replaced.'},indent=2)+'\n',encoding='utf-8')
    print('Created unsigned Microsoft Store submission package:',target)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--name',required=True)
    args=parser.parse_args();package(args.runtime,args.output,args.name)
