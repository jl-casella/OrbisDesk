#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W071 (H2): compile winevulkan's Unix side (dlls/winevulkan/vulkan.c, vulkan_thunks.c) for
Orbis, unpatched, with each object's recipe from the OrbisDesk Makefile, as
build-win32u-ps4.py does for win32u. The two objects become one, whose hidden symbols stay
local to it as they would in winevulkan.so; its call tables are renamed for
platform/ps4/pw_wine_unixlibs.c, through which ntdll finds them instead of dlopen.
win32u gives it the RADV linked into the same ELF (build-win32u-ps4.py, W071)."""
import hashlib,json,pathlib,shlex,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP='-ffile-prefix-map=%s=. -ffile-prefix-map=%s=vk-h0'%(ROOT,pathlib.Path.home()/'vk-h0')
SOURCE=ROOT/'.deps/wine/source';UNIX=ROOT/'.deps/wine/ps4-unix';work=ROOT/'build/winevulkan-ps4'
work.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
makefile=(UNIX/'Makefile').read_text().splitlines()
def recipe(target):
    index=next((i for i,line in enumerate(makefile) if line.startswith(target+': ') and i+1<len(makefile)
                and makefile[i+1].startswith('\t$(CC)')),None)
    if index is None:raise SystemExit('No recipe for '+target)
    parts=[];index+=1
    while True:
        line=makefile[index];parts.append(line.rstrip().removesuffix('\\'))
        if not line.rstrip().endswith('\\'):break
        index+=1
    return ' '.join(parts).replace('$(CC)',str(UNIX/'orbis-cc')).replace('$(CFLAGS)','-g -O2 '+PREFIX_MAP)
report={'schema_version':1,'wine_commit':commit,'results':[],'objects':{}}
objects=[]
# W166: from the tree tools/build-winevulkan-batch.py stages (prospero-win's 32-bit Vulkan call
# batching): its vulkan.c and vulkan_thunks.c, and the Unix sides of the batch (replay, record
# framing, descriptor templates, generated call codecs), with vulkan.o's recipe and the tree's
# folder in place of the pinned one. The 32-bit winevulkan.dll from the same tree sends them.
batch_manifest=json.loads((ROOT/'out/winevulkan-batch/manifest.json').read_text())
BATCH=ROOT/batch_manifest['tree']/'dlls/winevulkan'
for name,digest in batch_manifest['tree_sha256'].items():
    if sha(BATCH/name)!=digest:raise SystemExit('Staged winevulkan tree changed after its build: '+name)
PINNED=str(SOURCE/'dlls/winevulkan')
report['batch_tree']=str(BATCH.relative_to(ROOT))
for unit in ('vulkan','vulkan_thunks','pw_vk_batch_unix','pw_vk_wire_unix','pw_vk_template_cache_unix',
             'pw_vk_command_stream_unix','pw_vk_spsc_unix','pw_vk_codec_unix','pw_vk_generated_unix'):
    output=work/(unit+'.o')
    base=recipe('dlls/winevulkan/'+(unit if unit in ('vulkan','vulkan_thunks') else 'vulkan')+'.o')
    base=base.replace(PINNED+'/'+(unit if unit in ('vulkan','vulkan_thunks') else 'vulkan')+'.c',str(BATCH/(unit+'.c')))
    base=base.replace('-I'+PINNED,'-I'+str(BATCH))
    command=shlex.split(base.replace('$@',str(output)))
    command+=['-D__ORBIS__','-I'+str(ROOT/'platform/ps4'),'-ffunction-sections','-fdata-sections',
              '-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),'-idirafter',str(ROOT/'.deps/wine/runtime/build/include')]
    with (work/(output.stem+'.log')).open('w') as log:
        run=subprocess.run(command,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
    report['results'].append({'unit':unit,'exit_code':run.returncode})
    if run.returncode:continue
    objects.append(output);report['objects'][str(output.relative_to(ROOT))]=sha(output)
failed=[r['unit'] for r in report['results'] if r['exit_code']]
if not failed:
    combined=work/'winevulkan-combined.o';final=work/'winevulkan.o'
    subprocess.run(['ld.lld','-r','-o',str(combined),*map(str,objects)],check=True)
    subprocess.run(['objcopy','--localize-hidden',
                    '--redefine-sym','__wine_unix_call_funcs=pw_winevulkan_unix_call_funcs',
                    '--redefine-sym','__wine_unix_call_wow64_funcs=pw_winevulkan_unix_call_wow64_funcs',
                    str(combined),str(final)],check=True)
    report['object']=str(final.relative_to(ROOT));report['object_sha256']=sha(final)
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'units':len(report['results']),'failed':failed}))
if failed:raise SystemExit(1)
