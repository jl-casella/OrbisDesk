#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""alpha-1 (run-0165): free memory between guest runs in one OrbisDesk session, from a console log.

Guests share explorer's process: memory a guest does not give back stays lost until OrbisDesk ends. In
reports/pop-phase-b/physical/20261116T211401Z/run-0165.log Alan Wake's American Nightmare (32-bit, DXVK)
was started seven times; each overlay close after a device loss cost 0.63-0.75 GB, until a level load found
no memory. The cause: RADV's buffers on the console are direct memory, given back only by vkFreeMemory, and a
terminated guest never frees its Vulkan device memory (tools/build-win32u-ps4.py and tools/build-guest-hw.py
now free it when the guest has unloaded, logged as "PWGUEST vulkan module=... bytes=...").
run-0178 (2026-11-17, wined3d + OpenGL through Zink, closed from the overlay, 1.27 GB): Zink's device is the
process's; when no other guest runs, Mesa's WGL lets go of its screen ("PWGUEST gl ... result=1") and that device's
memory is freed too ("... gl_bytes=...", counted in "vk freed").
run-0185 (04.12, the same game and close, 524 MB of Zink memory freed, still 0.71 GB): "free GB" is
GlobalMemoryStatusEx's figure, the free direct memory plus the free flexible memory (platform/ps4/pw_wine_memory.c;
"free_source=summed" in the PWBOOT memory_info line, the largest free range otherwise). The logged total is the
direct memory size plus the free flexible memory, so its change is the flexible part of a loss; "split" shows both.
Builds with "PWVK guest_memory" lines also show how much of the direct part Wine's own commits (W175) kept.
run-0190 (04.13): those were 0.41 GB, the flexible part 0.29 GB, both a heap's memory; builds that destroy an ended
guest's heaps log "PWGUEST heaps ... destroyed= kept=" and the free memory just before ("why=heaps_before").
run-0212 (04.17): destroying them gave back nothing; the rest is in heaps the guest did not create. Builds that tag
large heap blocks log each heap of 1 MiB or more at a guest's start and release ("PWGUEST heap_usage") and the guest's
large blocks freed or kept ("PWGUEST heap_large"); "heap growth" and "large blocks" show them.
run-0215 (04.17): after a normal exit, the direct memory that was not Wine's commits stayed with the kept Vulkan
device and its instance's Crema device. Builds that destroy the device log "PWVK guest_teardown ..." and the free
memory after it ("why=teardown_after"), and Crema's "radv/ps4: device ... has no queues: gave back N bytes" (run-0219)
or "... ended: gave back N bytes"; "teardown" shows them, with the instances only for 04.19's build (run-0219).
04.30 (run-0252): builds that tag a guest's small blocks of the process heap log them ("PWGUEST heap_small"), and the
large blocks no guest's thread made ("PWGUEST heap_unowned"); "small blocks" and "unowned large" show them.

For each guest start (PWGUEST load_begin) this prints the free memory then, how the run ended (the overlay's
terminate, an exit status, the end of its console), whether it used Direct3D/Vulkan, the device memory
released at its end, and the loss until the next start. It only reads the log.

Usage: python3 -I tools/check-guest-memory.py <run-NNNN.log> [--app <exe name>] [--max-loss-gb <GB>]
  --app          only starts of this program (basename, case-insensitive), still measured to the next start
  --max-loss-gb  exit status 1 when a run that used the GPU and ended is followed by a larger loss
"""
import argparse,pathlib,re,sys

LOAD_BEGIN=re.compile(r'PWGUEST load_begin app=L"(?P<app>(?:[^"\\]|\\.)*)" .*?available=(?P<available>\d+) total=(?P<total>\d+)')
LOAD_END=re.compile(r'PWGUEST load_end app=L"(?P<app>(?:[^"\\]|\\.)*)" module=(?P<module>[0-9A-Fa-f]+)')
TERMINATE=re.compile(r'PWOVERLAY terminate module=(?P<module>[0-9A-Fa-f]+)')
EXITS=re.compile(r'PS4 guest module (?P<module>[0-9A-Fa-f]+) exits status (?P<status>\d+)')
CONSOLE=re.compile(r'PS4 guest module (?P<module>[0-9A-Fa-f]+) ended with the console')
VULKAN=re.compile(r'PWGUEST vulkan module=(?P<module>[0-9A-Fa-f]+) devices=(?P<devices>\d+) memories=(?P<memories>\d+) '
                  r'bytes=(?P<bytes>\d+)(?:.* gl_bytes=(?P<gl_bytes>\d+))?')
GL=re.compile(r'PWGUEST gl module=(?P<module>[0-9A-Fa-f]+) (?P<what>.*)')  # run-0178
HEAPS=re.compile(r'PWGUEST heaps module=(?P<module>[0-9A-Fa-f]+) destroyed=(?P<destroyed>\d+) kept=(?P<kept>\d+)')  # run-0190
HEAP_KEPT=re.compile(r'PWGUEST heap \S+ of module (?P<module>[0-9A-Fa-f]+) kept: (?:made|held) by L?"(?P<name>[^"]*)"')  # run-0190, run-0203
UNLOADED=re.compile(r'PWGUEST system_modules module=(?P<module>[0-9A-Fa-f]+) loaded=')  # always logged (W293)
GPU=re.compile(r'Dxvk|DXVK|wined3d|PWVK32|PWD3D|PWVK show_frame')  # Direct3D or Vulkan loaded, not that it drew
NO_MEMORY=re.compile(r'PWVM commit_backing .* no memory')
HEAP_USAGE=re.compile(r'PWGUEST heap_usage owner=(?P<owner>[0-9A-Fa-f]+) why=(?P<why>\w+) heap=(?P<heap>[0-9A-Fa-f]+) '
                      r'holder=(?P<holder>\S+) committed=(?P<committed>\d+) large=(?P<large>\d+)')  # run-0212
HEAP_LARGE=re.compile(r'PWGUEST heap_large module=(?P<module>[0-9A-Fa-f]+) heap=\S+ blocks=\d+ bytes=\d+ listed=\d+ '
                      r'freed=\d+ freed_bytes=(?P<freed>\d+)')  # run-0212
LARGE_KEPT=re.compile(r'PWGUEST heap_large module=(?P<module>[0-9A-Fa-f]+) kept bytes=(?P<bytes>\d+) blocks=\d+ from (?P<source>.+)')
SMALL=re.compile(r'PWGUEST heap_(?P<kind>small|unowned) module=(?P<module>[0-9A-Fa-f]+) (?:sites=\d+ )?blocks=\d+ '
                 r'bytes=(?P<bytes>\d+) listed=\d+ (?:missed=\d+ )?freed=\d+ freed_bytes=(?P<freed>\d+)')  # 04.30
SMALL_KEPT=re.compile(r'PWGUEST heap_(?P<kind>small|unowned) module=(?P<module>[0-9A-Fa-f]+) kept bytes=(?P<bytes>\d+) '
                      r'blocks=\d+ from (?P<source>.+)')  # 04.30
TEARDOWN=re.compile(r'PWVK guest_teardown owner=(?P<owner>0x[0-9a-fA-F]+|0) wow=\d+ swapchains=(?P<swapchains>\d+) '
                    r'devices=(?P<devices>\d+)(?: instances=(?P<instances>\d+))?')  # run-0215; instances: 04.19 only
TEARDOWN_STUCK=re.compile(r'PWVK guest_teardown owner=(?P<owner>0x[0-9a-fA-F]+|0) wow=\d+ still running')  # run-0215
CREMA_END=re.compile(r'radv/ps4: device \S+ (?:ended|has no queues): gave back (?P<bytes>\d+) bytes')  # run-0215, run-0219
MEMORY=re.compile(r'PWVK guest_memory owner=(?P<owner>0x[0-9a-fA-F]+|0) wow=\d+ why=(?P<why>\w+) direct_free=(?P<free>\d+) '
                  r'flexible=(?P<flexible>\d+) wine_direct=(?P<wine>\d+) wine_runs=(?P<runs>\d+) heaps=(?P<heaps>\d+)')  # run-0185

def basename(app):
    return app.replace('\\\\','\\').rsplit('\\',1)[-1]

def parse(path):
    runs=[];open_by_module={};current=None;released=None  # released: the run whose release_after came last
    for number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
        if (m:=LOAD_BEGIN.search(line)):
            current={'line':number,'app':basename(m['app']),'available':int(m['available']),'total':int(m['total']),
                     'module':None,'end':'running','gpu':False,'vulkan_bytes':None,'gl':None,'no_memory':0,'unloaded':False,
                     'owner':None,'memory':{},'heaps':None,'heaps_kept':[],'heap_usage':{},'large_freed':0,'large_kept':[],
                     'teardown':None,'teardown_stuck':False,'crema_freed':0,'small':{},'small_kept':{}}
            runs.append(current)
            released=None  # run-0219: Crema's lines from here on are this run's own devices
        elif (m:=MEMORY.search(line)):
            if m['why']=='start' and current and current['owner'] is None:current['owner']=m['owner'].lower()
            run=current if m['why']=='start' else next((r for r in reversed(runs) if r['owner']==m['owner'].lower()),None)
            if run:run['memory'][m['why']]={k:int(m[k]) for k in ('free','flexible','wine','runs','heaps')}
            if run and m['why']=='release_after':released=run
        elif (m:=TEARDOWN.search(line)):  # run-0215: the helper's line, after its release_after
            run=next((r for r in reversed(runs) if r['owner']==m['owner'].lower()),None)
            if run:run['teardown']=tuple(int(m[k] or 0) for k in ('swapchains','devices','instances'))
        elif (m:=TEARDOWN_STUCK.search(line)):
            run=next((r for r in reversed(runs) if r['owner']==m['owner'].lower()),None)
            if run:run['teardown_stuck']=True
        elif (m:=CREMA_END.search(line)):  # a Crema device given back after the last release, before the next start
            if released:released['crema_freed']+=int(m['bytes'])
        elif (m:=HEAP_USAGE.search(line)):  # run-0212: owner is the guest, as in the PWVK lines
            owner=int(m['owner'],16)
            run=next((r for r in reversed(runs) if r['owner'] and int(r['owner'],16)==owner),None)
            if run:
                run['heap_usage'].setdefault(m['why'],{})[m['heap'].lower()]=(m['holder'],int(m['committed'])+int(m['large']))
        elif (m:=HEAP_LARGE.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['large_freed']+=int(m['freed'])
        elif (m:=LARGE_KEPT.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['large_kept'].append((int(m['bytes']),m['source'].strip()))
        elif (m:=SMALL.search(line)) and (run:=open_by_module.get(m['module'].lower())):  # 04.30
            run['small'][m['kind']]=(int(m['bytes']),int(m['freed']))
        elif (m:=SMALL_KEPT.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['small_kept'].setdefault(m['kind'],[]).append((int(m['bytes']),m['source'].strip()))
        elif (m:=LOAD_END.search(line)):
            for run in reversed(runs):
                if run['app']==basename(m['app']) and run['module'] is None:
                    run['module']=m['module'].lower();open_by_module[run['module']]=run;break
        elif (m:=TERMINATE.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['end']='terminated'
        elif (m:=EXITS.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            if run['end']=='running':run['end']='exit %s'%m['status']
        elif (m:=CONSOLE.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            if run['end']=='running':run['end']='console'
        elif (m:=VULKAN.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['vulkan_bytes']=int(m['bytes'])+int(m['gl_bytes'] or 0)
        elif (m:=GL.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['gl']=m['what'].strip()
        elif (m:=HEAPS.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['heaps']=(int(m['destroyed']),int(m['kept']))
        elif (m:=HEAP_KEPT.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['heaps_kept'].append(m['name'])
        elif (m:=UNLOADED.search(line)) and (run:=open_by_module.get(m['module'].lower())):
            run['unloaded']=True
        else:
            # lines of the newest start that has not unloaded (one game at a time in these tests)
            live=next((run for run in reversed(runs) if not run['unloaded']),None)
            if live and GPU.search(line):live['gpu']=True
            if live and NO_MEMORY.search(line):live['no_memory']+=1
    # a module base belongs to its newest load_end; the release line follows the unload summary
    return runs

def main():
    parser=argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('log',type=pathlib.Path)
    parser.add_argument('--app')
    parser.add_argument('--max-loss-gb',type=float)
    args=parser.parse_args()
    runs=parse(args.log)
    if not runs:
        print('no PWGUEST load_begin line in',args.log);return 1
    gb=lambda value:value/1e9
    print('%4s %7s %-36s %9s %-12s %3s %10s %9s %s'%('#','line','program','free GB','end','gpu','vk freed','loss GB','notes'))
    failed=[]
    for index,run in enumerate(runs):
        following=runs[index+1] if index+1<len(runs) else None
        loss=gb(run['available']-following['available']) if following else None
        if args.app and run['app'].lower()!=args.app.lower():continue
        freed='-' if run['vulkan_bytes'] is None else '%.0f MB'%(run['vulkan_bytes']/1e6)
        notes=[]
        if run['gl']:notes.append('gl '+run['gl'])
        if run['no_memory']:notes.append('%d "no memory" commits'%run['no_memory'])
        if not run['unloaded'] and run['end']!='running':notes.append('not unloaded in this log')
        if following:  # run-0185: the total changes only with the free flexible memory
            flexible=gb(run['total']-following['total'])
            notes.append('split: flexible %.2f, direct %.2f'%(flexible,loss-flexible))
        memory=run['memory']
        if following and 'start' in memory and 'start' in following['memory']:
            a,b=memory['start'],following['memory']['start']
            # heaps: the next start can be in the other world; this guest's world at its unload (run-0190)
            heaps=memory.get('heaps_before',memory.get('release_before',b))['heaps']
            notes.append('of the direct: Wine commits %.2f, other %.2f; heaps %d->%d'%(gb(b['wine']-a['wine']),
                         gb(a['free']-b['free'])-gb(b['wine']-a['wine']),a['heaps'],heaps))
        if run['heaps']:  # run-0190
            text='heaps destroyed %d, kept %d'%run['heaps']
            if run['heaps_kept']:text+=' (%s)'%', '.join(sorted(set(run['heaps_kept'])))
            if 'heaps_before' in memory and 'release_before' in memory:
                a,b=memory['heaps_before'],memory['release_before']
                text+=', gave back direct %.0f MB, flexible %.0f MB'%((b['free']-a['free'])/1e6,(b['flexible']-a['flexible'])/1e6)
            notes.append(text)
        usage=run['heap_usage']
        if 'release' in usage:  # run-0212: growth of each heap from the start to the release
            start=usage.get('start',{});growth=[]
            for heap,(holder,size) in usage['release'].items():
                change=size-start.get(heap,(None,0))[1]
                if abs(change)>=1e6:growth.append((change,'process' if holder=='process' else holder if holder!='-' else heap))
            if growth:notes.append('heap growth: '+', '.join('%s %+.0f MB'%(name,change/1e6) for change,name in sorted(growth,reverse=True)[:4]))
        if run['large_freed'] or run['large_kept']:
            kept=sorted(run['large_kept'],reverse=True)
            notes.append('large blocks: freed %.0f MB, kept %.0f MB%s'%(run['large_freed']/1e6,sum(b for b,_ in kept)/1e6,
                         ' (%s)'%'; '.join('%s %.0f MB'%(source,b/1e6) for b,source in kept[:4]) if kept else ''))
        for kind,label in (('small','small blocks'),('unowned','unowned large')):  # 04.30
            if kind not in run['small']:continue
            total,freed_bytes=run['small'][kind];kept=sorted(run['small_kept'].get(kind,[]),reverse=True)
            notes.append('%s: %.0f MB, freed %.0f MB%s'%(label,total/1e6,freed_bytes/1e6,
                         ' (kept %s)'%'; '.join('%s %.0f MB'%(source,b/1e6) for b,source in kept[:3]) if kept else ''))
        if run['teardown'] or run['teardown_stuck'] or 'teardown_after' in memory:  # run-0215
            swapchains,devices,instances=run['teardown'] or (0,0,0)
            text='teardown: swapchains %d, devices %d'%(swapchains,devices)
            if instances:text+=', instances %d'%instances
            if run['teardown_stuck']:text+=', still running at 3 s'
            if run['crema_freed']:text+=', Crema gave back %.0f MB'%(run['crema_freed']/1e6)
            if 'release_after' in memory and 'teardown_after' in memory:
                text+=', gave back direct %.0f MB'%((memory['teardown_after']['free']-memory['release_after']['free'])/1e6)
            notes.append(text)
        if 'release_before' in memory and 'release_after' in memory:
            a,b=memory['release_before'],memory['release_after']
            notes.append('release gave back direct %.0f MB'%((b['free']-a['free'])/1e6))
        print('%4d %7d %-36s %9.2f %-12s %3s %10s %9s %s'%(index+1,run['line'],run['app'][:36],gb(run['available']),
              run['end'],'yes' if run['gpu'] else 'no',freed,'-' if loss is None else '%.2f'%loss,'; '.join(notes)))
        if (args.max_loss_gb is not None and loss is not None and run['gpu'] and run['end']!='running' and
                loss>args.max_loss_gb):
            failed.append((index+1,loss))
    if failed:
        print('FAIL: loss above %.2f GB after run(s) %s'%(args.max_loss_gb,', '.join('%d (%.2f GB)'%f for f in failed)))
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
