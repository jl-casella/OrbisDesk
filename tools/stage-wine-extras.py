#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Stage Wine modules the sealed prefix lacks, for both views: common controls v6 and audio codecs.

W175 (phase 7). From the pinned host Wine tree (.deps/wine/runtime/build), unpatched:
- comctl32_v6.dll: SysLink and the other v6 classes. winecfg's About page (and any program
  with a common-controls 6.0 manifest) needs it; v5 comctl32 does not register SysLink and
  the page could not be created (W173). Also as the side-by-side assembly Wine's setupapi
  installs (dlls/setupapi/fakedll.c, register_manifest): winsxs\\<arch>_microsoft.windows.
  common-controls_6595b64144ccf1df_6.0.2600.2982_none_deadbeef\\comctl32.dll and its manifest in
  winsxs\\manifests, with processorArchitecture filled in.
- imaadp32.acm, msadp32.acm, msg711.acm: ACM codecs system.ini [drivers32] already names
  (winecfg's test sound is IMA ADPCM, W173); msacm32.drv and midimap.dll, the wave and MIDI
  mappers winmm installs by name (dlls/winmm/lolvldrv.c). msgsm32.acm (libgsm) and
  l3codeca.acm (mpg123) need Unix libraries and are left out.
- W175: aero.msstyles, Wine's only visual style, for winecfg's theme list: one file in
  resources\\themes\\aero (wine.inf), which uxtheme opens as a resource file from either view.
- W221: dpnhpast.dll, the DirectPlay NAT helper. The DirectX SDK's GetDXVersion reports 8.1 only
  when it loads by that name; without it GTA Vice City stops at "DirectX 8.1 is required" (W219,
  docs/investigacion-gta-vc-base-0x400000.md). Imports kernel32, ntdll and ucrtbase only.
Output: out/wine-extras/{x86_64,i386}-windows/, out/wine-extras/winsxs/, out/wine-extras/themes/
and manifest.json, copied by build-wine-hardware.py.
"""
import hashlib,json,pathlib,re,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';out=ROOT/'out/wine-extras'
MODULES=(('comctl32_v6','comctl32_v6.dll'),('imaadp32.acm','imaadp32.acm'),('msadp32.acm','msadp32.acm'),
         ('msg711.acm','msg711.acm'),('msacm32.drv','msacm32.drv'),('midimap','midimap.dll'),
         ('dpnhpast','dpnhpast.dll'))
ARCHES={'x86_64':'amd64','i386':'x86'}  # Wine's build folder, winsxs processorArchitecture
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
wine_commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if wine_commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Extras require the pinned Wine revision')
if out.exists():shutil.rmtree(out)
modules={}
for arch in ARCHES:
    (out/(arch+'-windows')).mkdir(parents=True)
    for folder,name in MODULES:
        source=BUILD/'dlls'/folder/(arch+'-windows')/name
        if not source.is_file():raise SystemExit('Not built: %s (make dlls/%s/%s-windows/%s)'%(source,folder,arch,name))
        target=out/(arch+'-windows')/name;target.write_bytes(source.read_bytes())
        modules[arch+'/'+name]={'path':arch+'-windows/'+name,'sha256':sha(target),'source':str(source.relative_to(ROOT))}
# The assembly manifest is comctl32_v6's WINE_MANIFEST resource (dlls/comctl32_v6/rsrc.rc).
manifest_source=SOURCE/'dlls/comctl32_v6/comctl32.manifest';text=manifest_source.read_bytes()
identity=re.search(rb'<assemblyIdentity\b[^>]*>',text).group(0)
attrs={k.decode():v.decode() for k,v in re.findall(rb'(\w+)="([^"]*)"',identity)}
if attrs.get('processorArchitecture')!='' or 'language' in attrs:raise SystemExit('Unexpected assemblyIdentity: '+identity.decode())
winsxs={}
for arch,sxs_arch in ARCHES.items():
    # fakedll.c append_manifest_filename: arch_, name_ (lowercase), key_version_, lang_ ("none"), deadbeef
    name='%s_%s_%s_%s_none_deadbeef'%(sxs_arch,attrs['name'].lower(),attrs['publicKeyToken'],attrs['version'])
    if len(sxs_arch)>16 or len(attrs['name'])>40:raise SystemExit('fakedll.c would shorten '+name)
    filled=text.replace(identity,identity.replace(b'processorArchitecture=""',b'processorArchitecture="%s"'%sxs_arch.encode()),1)
    (out/'winsxs/manifests').mkdir(parents=True,exist_ok=True);(out/'winsxs'/name).mkdir(parents=True)
    (out/'winsxs/manifests'/(name+'.manifest')).write_bytes(filled)
    shutil.copyfile(out/(arch+'-windows')/'comctl32_v6.dll',out/'winsxs'/name/'comctl32.dll')
    winsxs[arch]={'assembly':name,
                  'dll':{'path':'winsxs/%s/comctl32.dll'%name,'sha256':sha(out/'winsxs'/name/'comctl32.dll')},
                  'manifest':{'path':'winsxs/manifests/%s.manifest'%name,'sha256':sha(out/'winsxs/manifests'/(name+'.manifest'))}}
aero=BUILD/'dlls/aero.msstyles/x86_64-windows/aero.msstyles'
if not aero.is_file():raise SystemExit('Not built: %s (make dlls/aero.msstyles/x86_64-windows/aero.msstyles)'%aero)
(out/'themes/aero').mkdir(parents=True);shutil.copyfile(aero,out/'themes/aero/aero.msstyles')
themes={'aero/aero.msstyles':{'path':'themes/aero/aero.msstyles','sha256':sha(out/'themes/aero/aero.msstyles'),
                              'source':str(aero.relative_to(ROOT))}}
manifest={'schema_version':1,'wine_commit':wine_commit,'builder_sha256':sha(__file__),'modules':modules,'winsxs':winsxs,
          'themes':themes,'source_patches':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':len(modules),'assemblies':[w['assembly'] for w in winsxs.values()]}))
