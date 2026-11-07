#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W166: 32-bit Vulkan calls in batches (prospero-win's command-stream batching), for Orbis.

W165 measured wined3d's command stream thread in SuperMarioKart (a 32-bit program, Direct3D 7 on
wined3d's Vulkan renderer) making ~80,000 Unix calls a second, one per Vulkan call, and spending
~18% of its time just switching FS on those 32->64-bit transitions (wow64native). prospero-win
(LGPL-2.1+, same Wine commit) queues a 32-bit program's void Vulkan calls in its PE winevulkan and
replays them on the Unix side in one call at the next call that returns something.

This stages a winevulkan tree with prospero-win's own tools/stage_vk_batch.py, which also
regenerates the thunks and the call codecs from the Vulkan registry Wine pins (vk.xml and
video.xml 1.4.357, in ~/.cache/wine; checked here to reproduce Wine's pinned generated files),
then builds:
- the 32-bit winevulkan.dll (PE) from the staged sources, with the pinned build's own compile and
  link commands (make -n), into out/winevulkan-batch;
- its Unix side is compiled from the same tree by tools/build-winevulkan-ps4.py.
64-bit programs keep Wine's plain thunks (the batching is #ifndef _WIN64 in the PE loader)."""
import hashlib,json,pathlib,shlex,shutil,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';UP=ROOT/'upstream/prospero-win'
tree=ROOT/'.deps/wine/winevulkan-batch/tree';check=ROOT/'.deps/wine/winevulkan-batch/check'
work=ROOT/'build/winevulkan-batch';out=ROOT/'out/winevulkan-batch'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
cache=pathlib.Path.home()/'.cache/wine'
xmls={'vk.xml':cache/'vk-1.4.357.xml','video.xml':cache/'video-1.4.357.xml'}
if any(not p.exists() for p in xmls.values()):raise SystemExit('Vulkan registry 1.4.357 missing in '+str(cache))
GENERATED=('dlls/winevulkan/vulkan_thunks.c','dlls/winevulkan/vulkan_thunks.h','dlls/winevulkan/loader_thunks.c',
           'dlls/winevulkan/loader_thunks.h','include/wine/vulkan.h','include/wine/vulkan_driver.h',
           'dlls/vulkan-1/vulkan-1.spec','dlls/winevulkan/winevulkan.spec')
def fresh(target):
    if target.exists():shutil.rmtree(target)
    (target/'dlls').mkdir(parents=True);(target/'include/wine').mkdir(parents=True)
    for d in ('winevulkan','vulkan-1'):shutil.copytree(SOURCE/'dlls'/d,target/'dlls'/d)
    for h in ('vulkan.h','vulkan_driver.h'):shutil.copyfile(SOURCE/'include/wine'/h,target/'include/wine'/h)
# the registry reproduces Wine's pinned generated files: it is the one Wine generated them from
fresh(check)
subprocess.run([sys.executable,'make_vulkan','-x',str(xmls['vk.xml']),'-X',str(xmls['video.xml'])],
               cwd=check/'dlls/winevulkan',check=True,capture_output=True)
for f in GENERATED:
    if sha(SOURCE/f)!=sha(check/f):raise SystemExit('Vulkan registry does not reproduce '+f)
fresh(tree)
staged=subprocess.run([sys.executable,str(UP/'tools/stage_vk_batch.py'),'--source',str(tree),'--repo',str(UP)],
                      check=True,capture_output=True,text=True)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
src=tree/'dlls/winevulkan'
PE_UNITS=('loader','loader_thunks','pw_vk_batch_pe','pw_vk_present_pe','pw_vk_retire','pw_vk_wire',
          'pw_vk_template_cache','pw_vk_command_stream','pw_vk_spsc','pw_vk_codec','pw_vk_generated')
dry=subprocess.run(['make','-n','-W../../source/dlls/winevulkan/loader.c','dlls/winevulkan/i386-windows/winevulkan.dll'],
                   cwd=BUILD,capture_output=True,text=True,check=True).stdout.replace('\\\n',' ')
compile_line=next(l for l in dry.splitlines() if 'dlls/winevulkan/i386-windows/loader.o' in l and ' -c ' in l)
link_line=next(l for l in dry.splitlines() if 'winegcc' in l and 'winevulkan.dll' in l)
objects=[]
for unit in PE_UNITS:
    obj=work/(unit+'.o')
    command=compile_line.replace('dlls/winevulkan/i386-windows/loader.o',str(obj))
    command=command.replace('../../source/dlls/winevulkan/loader.c',str(src/(unit+'.c')))
    command=command.replace('-I../../source/dlls/winevulkan','-I'+str(src))
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    objects.append(obj)
pinned_objects=['dlls/winevulkan/i386-windows/loader.o','dlls/winevulkan/i386-windows/loader_thunks.o']
for o in pinned_objects:
    if o not in link_line:raise SystemExit('Unexpected winevulkan link line: '+link_line[:300])
dll=work/'winevulkan.dll'
command=link_line.replace('-o dlls/winevulkan/i386-windows/winevulkan.dll','-o '+str(dll))
command=command.replace(' '.join(pinned_objects),' '.join(map(str,objects)))
command=command.replace('../../source/dlls/winevulkan/winevulkan.spec',str(src/'winevulkan.spec'))
run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
shutil.copyfile(dll,out/'winevulkan.dll')
manifest={'schema_version':1,'wine_commit':commit,'arch':'i386',
          'winevulkan':{'path':'winevulkan.dll','sha256':sha(out/'winevulkan.dll')},
          'registry':{k:{'path':str(v),'sha256':sha(v)} for k,v in xmls.items()},
          'stage_output':staged.stdout.strip().splitlines(),
          'prospero_win_sources':{p.name:sha(p) for p in sorted((UP/'wine/ps5/vulkan').glob('*.[ch]'))},
          'tree':str(tree.relative_to(ROOT)),
          'tree_sha256':{p.name:sha(p) for p in sorted(src.glob('*.[ch]'))},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'winevulkan':str((out/'winevulkan.dll').relative_to(ROOT)),'sha256':manifest['winevulkan']['sha256']}))
