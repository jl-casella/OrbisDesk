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
from wine_vk_batch_hotpath import patch_batch_hotpath, patch_present_logging
from wine_vk_descriptor_cache import patch_pe, patch_unix, patch_vulkan
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
# 04.33 (docs/SHADER_CACHE.md): in explorer's 32-bit world every program reaches winevulkan through the Khronos loader
# with MangoHud's implicit layer, and the loader hands the ICD the program's create info with its own
# VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO links still in pNext (Vulkan-Loader loader.c terminator_CreateInstance
# copies pCreateInfo). The batch's guard treated any instance pNext as unsafe and turned the batching off for the whole
# process: run-0253 (vk_batch=1) kept Zink's thread at ~225,000 crossings a second, as without it. The W167 relaunch had
# no loader or layer in the 32-bit process. The loader's links carry no callback winevulkan calls; every other
# structure (debug messengers, validation features) still turns it off.
guard=src/'pw_vk_disable_guard.h'
guard_text=guard.read_text()
for old,new in (
    ('static BOOL pw_vk_stream_call_unsafe(unsigned int code, const void *args)\n',
     '/* OrbisDesk 04.33: an instance chain made only of the Khronos loader\'s own links is safe. */\n'
     'static BOOL pw_vk_instance_chain_unsafe(const void *next)\n{\n'
     '    const VkBaseInStructure *s;\n'
     '    for (s = next; s; s = s->pNext)\n'
     '        if (s->sType != VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO) return TRUE;\n'
     '    return FALSE;\n}\n'
     'static BOOL pw_vk_stream_call_unsafe(unsigned int code, const void *args)\n'),
    ('            return !c || c->enabledLayerCount || c->pNext || p->pAllocator;\n',
     '            return !c || c->enabledLayerCount || pw_vk_instance_chain_unsafe(c->pNext) || p->pAllocator;\n')):
    if guard_text.count(old)!=1:raise SystemExit('Unexpected context in pw_vk_disable_guard.h: '+old[:60])
    guard_text=guard_text.replace(old,new)
guard.write_text(guard_text)
# 04.34: run-0253 and run-0275 had no line saying whether the batching was on; only the per-thread profile's Unix-call
# rate told (run-0275: Zink's thread 193,000 -> 81,000 a second in gameplay). One err line when a process starts it,
# when PW_VK_BATCH=1 was asked for and it stays off from the start, and when a call turns it off for the rest of the
# process (naming the call). Each happens at most once per process; nothing per call or per frame.
batch_pe=src/'pw_vk_batch_pe.c'
batch_text=batch_pe.read_text()
for old,new in (
    (' if(!enabled)return TRUE;\n',
     ' if(!enabled){\n'
     '  if(GetEnvironmentVariableA("PW_VK_BATCH",env,sizeof(env))==1&&env[0]==\'1\')ERR("PW_VK_BATCH off from the start: layer environment or opcode mask\\n");\n'
     '  return TRUE;\n }\n'),
    (' /* Diagnostics are independently opt-in; FPS confirmation leaves them off. */\n',
     ' ERR("PW_VK_BATCH on=%u stats=%u (OrbisDesk 04.34)\\n",enabled,stats_enabled);\n'
     ' /* Diagnostics are independently opt-in; FPS confirmation leaves them off. */\n'),
    ('  InterlockedExchange(&sticky_disabled,1);leave();',
     '  ERR("PW_VK_BATCH off for the rest of the process: unix call %u (%s)\\n",code,code<unix_count?pw_vk_function_names[code]:"?");\n'
     '  InterlockedExchange(&sticky_disabled,1);leave();'),
    # 04.84 (W303 run-0181, 04.83: Half-Life in D3D mode, started after Counter-Strike, logged only "PW_VK_BATCH fatal
    # replay/order failure" and ended; the next Half-Life waited 60 s on section 7854AA44, the gate, "blocked by" the
    # ended thread, and ended too). fatal() names its call site and status, and the gate's owner and depth (enter()
    # also calls it when the gate's recorded owner is this thread id: one ended inside it, and Wine reused its id).
    # A guest's TerminateProcess ends that guest only, in a process that goes on: the gate it holds is left first,
    # so the next guest does not block on it.
    ('static DECLSPEC_NORETURN void fatal(void){ERR("PW_VK_BATCH fatal replay/order failure\\n");TerminateProcess(GetCurrentProcess(),3);ExitProcess(3);}',
     'static DECLSPEC_NORETURN void fatal_at(int line,long status)\n'
     '{\n'
     ' ERR("PW_VK_BATCH fatal replay/order failure (OrbisDesk 04.84: pw_vk_batch_pe.c line %d, status %#lx, gate owner %04lx depth %u)\\n",\n'
     '     line,status,(unsigned long)owner,depth);\n'
     ' /* 04.84: the guest ends, the process goes on; never leave the gate held for the next guest */\n'
     ' if(owner==GetCurrentThreadId()){depth=0;owner=0;}\n'
     ' while((DWORD)(ULONG_PTR)gate.OwningThread==GetCurrentThreadId())LeaveCriticalSection(&gate);\n'
     ' TerminateProcess(GetCurrentProcess(),3);ExitProcess(3);\n'
     '}\n'
     '#define fatal() fatal_at(__LINE__,0)'),
    ('   if(status)fatal();\n','   if(status)fatal_at(__LINE__,status);\n'),
    ('status=raw_call(unix_pw_vk_batch,&p);if(status)fatal();','status=raw_call(unix_pw_vk_batch,&p);if(status)fatal_at(__LINE__,status);'),
    ('   if(appended!=PW_VK_STREAM_INVALID)fatal();','   if(appended!=PW_VK_STREAM_INVALID)fatal_at(__LINE__,appended);'),
    # 04.86 (W303 run-0188, 04.84: "fatal ... line 229, status 0xc0000005": the replay itself faulted in Half-Life's
    # first flush, right after it destroyed a swapchain of Counter-Strike's window). A guest's end kills its threads
    # where they are: their streams keep what they queued and nothing replays it until another guest flushes, after
    # kernelbase has released the ended guest's memory, Vulkan devices and heaps. kernelbase now calls
    # pw_vk_batch_guest_end() once the guest's other threads are gone and before that release: it retires the streams
    # of threads that no longer exist and replays what they published while what it refers to is still there. A thread
    # killed between taking its ticket and publishing it leaves a ticket no stream holds: once every live stream has
    # published what it reserved, such tickets (at most one per killed publisher, and only up to that moment's marker)
    # are passed over instead of waited on forever. Each end with streams of ended threads logs one line.
    ('static LONG sticky_disabled;\n',
     'static LONG sticky_disabled;\n'
     'static LONG lost_tickets;static uint64_t lost_marker; /* 04.86: pw_vk_batch_guest_end only */\n'),
    ('  if(!found){wait_tick("collect",list,n,marker,&spins,&start,&reported);SwitchToThread();}',
     '  if(!found&&lost_tickets&&next_replay<=lost_marker){lost_tickets--;next_replay++;continue;} /* 04.86 */\n'
     '  if(!found){wait_tick("collect",list,n,marker,&spins,&start,&reported);SwitchToThread();}'),
    ('NTSTATUS pw_vk_batch_call(unsigned int code,void *args)\n{',
     '/* OrbisDesk 04.86 (tools/build-winevulkan-batch.py): kernelbase calls this when a guest ends, after its other\n'
     ' * threads are gone and before it releases their memory and Vulkan devices. */\n'
     'static BOOL thread_gone(DWORD tid)\n'
     '{\n'
     ' HANDLE thread=OpenThread(THREAD_QUERY_LIMITED_INFORMATION,FALSE,tid);DWORD code=STILL_ACTIVE;\n'
     ' if(!thread)return TRUE;\n'
     ' if(!GetExitCodeThread(thread,&code))code=STILL_ACTIVE;\n'
     ' CloseHandle(thread);return code!=STILL_ACTIVE;\n'
     '}\n'
     'void CDECL pw_vk_batch_guest_end(void)\n'
     '{\n'
     ' struct producer *list[PW_VK_BATCH_SCRATCH/PW_VK_BATCH_ARENA];size_t n,i;\n'
     ' unsigned ended=0,publishing=0,waits=0;uint64_t first,marker;LONG passed;\n'
     ' if(tls==TLS_OUT_OF_INDEXES||!enabled||!negotiated||InterlockedCompareExchange(&sticky_disabled,0,0))return;\n'
     ' enter();\n'
     ' n=producers(list);\n'
     ' for(i=0;i<n;i++){\n'
     '  struct producer *p=list[i];\n'
     '  if(InterlockedCompareExchange(&p->retired,0,0)||!thread_gone(p->tid))continue;\n'
     '  ended++;\n'
     '  /* killed while publishing: it may hold a ticket it never published */\n'
     '  if(InterlockedExchange(&p->publishing,0))publishing++;\n'
     '  InterlockedIncrement(&retired_pending);InterlockedExchange(&p->retired,1);\n'
     ' }\n'
     ' if(!ended){leave();return;}\n'
     ' marker=pw_vk_spsc_marker(&stream_sequence);\n'
     ' /* every ticket up to marker that a live stream took is published once its publishing flag drops */\n'
     ' for(i=0;i<n;i++)\n'
     '  while(!InterlockedCompareExchange(&list[i]->retired,0,0)&&InterlockedCompareExchange(&list[i]->publishing,0,0)){\n'
     '   waits++;SwitchToThread();\n'
     '  }\n'
     ' first=next_replay;lost_tickets=publishing;lost_marker=marker;\n'
     ' flush_call(unix_count,NULL);\n'
     ' passed=(LONG)publishing-lost_tickets;lost_tickets=0;lost_marker=0;\n'
     ' ERR("PW_VK_BATCH guest_end streams=%u ended=%u replayed=%u passed_over=%ld publishing=%u waits=%u (OrbisDesk 04.86)\\n",\n'
     '     (unsigned)n,ended,(unsigned)(next_replay-first-passed),passed,publishing,waits);\n'
     ' leave();\n'
     '}\n'
     'NTSTATUS pw_vk_batch_call(unsigned int code,void *args)\n{')):
    if batch_text.count(old)!=1:raise SystemExit('Unexpected context in pw_vk_batch_pe.c: '+old[:60])
    batch_text=batch_text.replace(old,new)
batch_pe.write_text(patch_pe(patch_batch_hotpath(batch_text)))
# 04.86: kernelbase finds pw_vk_batch_guest_end by name (tools/build-guest-hw.py, ps4_guest_exit_process)
spec=src/'winevulkan.spec';spec_text=spec.read_text()
if 'pw_vk_batch_guest_end' not in spec_text:spec.write_text(spec_text+'@ cdecl -private pw_vk_batch_guest_end()\n')
for name in ('pw_vk_descriptor_cache.h','pw_vk_descriptor_cache_pe.inc.c'):
    shutil.copyfile(ROOT/'platform/ps4'/name,src/name)
for name,transform in (('pw_vk_batch_unix.c',patch_unix),('vulkan.c',patch_vulkan)):
    target=src/name;target.write_text(transform(target.read_text()))
present_pe=src/'pw_vk_present_pe.c'
present_pe.write_text(patch_present_logging(present_pe.read_text()))
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
          'descriptor_sources':{name:sha(ROOT/name) for name in ('tools/wine_vk_descriptor_cache.py','platform/ps4/pw_vk_descriptor_cache.h','platform/ps4/pw_vk_descriptor_cache_pe.inc.c')},
          'hotpath_patch_sha256':sha(ROOT/'tools/wine_vk_batch_hotpath.py'),
          'winevulkan':{'path':'winevulkan.dll','sha256':sha(out/'winevulkan.dll')},
          'registry':{k:{'path':str(v),'sha256':sha(v)} for k,v in xmls.items()},
          'stage_output':staged.stdout.strip().splitlines(),
          'prospero_win_sources':{p.name:sha(p) for p in sorted((UP/'wine/ps5/vulkan').glob('*.[ch]'))},
          'tree':str(tree.relative_to(ROOT)),
          'tree_sha256':{p.name:sha(p) for p in sorted(src.glob('*.[ch]'))},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'winevulkan':str((out/'winevulkan.dll').relative_to(ROOT)),'sha256':manifest['winevulkan']['sha256']}))
