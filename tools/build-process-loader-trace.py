#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the external loader (P006 stage tracing; P010: an app SELF run inside a sandbox root) from pinned
sources; no deployment."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import argparse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def bundle_sources(out,deps,patchdir):
    bundle=out/'source-bundle.tar.gz'
    with tarfile.open(bundle,'w:gz') as tar:
        for path in [deps/'elfldr-source.tar.gz',deps/'sdk-v0.9-source.tar.gz',ROOT/'native/process_loader_stage.h',
                     ROOT/'native/process_loader_protocol.h',ROOT/'native/process_loader_self_check.h',Path(__file__).resolve(),ROOT/'tools/process-loader.lock.json',*patchdir.glob('*.patch')]:
            tar.add(path,arcname=str(path.relative_to(ROOT)))
    return bundle
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--bundle-only',action='store_true',help='Add the source bundle without rebuilding or replacing deployed binaries');args=parser.parse_args()
    pins=json.loads((ROOT/'tools/process-loader.lock.json').read_text());deps=ROOT/'.deps/process-loader'
    if args.bundle_only:
        out=ROOT/'out/process-loader-p006';manifest=json.loads((out/'manifest.json').read_text())
        for name,item in manifest['artifacts'].items():
            if sha(out/name)!=item['sha256']:raise RuntimeError('Existing artifact differs: '+name)
        bundle=bundle_sources(out,deps,ROOT/'patches/process-loader');manifest['source_bundle_sha256']=sha(bundle)
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Source bundle added; deployed binary hashes unchanged');return
    sdk=deps/'sdk/ps4-payload-sdk'
    if sha(deps/'sdk-v0.9.zip')!=pins['sdk']['sha256']:raise RuntimeError('SDK archive differs')
    work=Path(tempfile.mkdtemp(prefix='orbisdesk-loader-trace-',dir='/var/tmp'))
    source={};patches=[]
    for name,archive,prefix in [('elfldr','elfldr-source.tar.gz','elfldr-'),('sdk_source','sdk-v0.9-source.tar.gz','sdk-')]:
        path=deps/archive
        if not path.exists() and args.fetch:
            with urllib.request.urlopen(urllib.request.Request(pins[name]['url'],headers={'User-Agent':'OrbisDesk-process-research'}),timeout=90) as remote:
                path.with_suffix('.part').write_bytes(remote.read())
            if sha(path.with_suffix('.part'))!=pins[name]['sha256']:raise RuntimeError('Downloaded source differs: '+name)
            path.with_suffix('.part').replace(path)
        if sha(path)!=pins[name]['sha256']:raise RuntimeError('Source archive differs: '+name)
        with tarfile.open(path) as tar:
            members=[entry for entry in tar if name!='sdk_source' or len(Path(entry.name).parts)<2 or Path(entry.name).parts[1]=='crt']
            for entry in members:
                if entry.issym() or entry.islnk() or not (work/entry.name).resolve().is_relative_to(work.resolve()):raise RuntimeError('Unsafe archive')
            tar.extractall(work,members=members)
        source[name]=work/(prefix+pins[name]['commit'])
    def edit(name,relative,changes,patch='bootstrap-trace'):
        path=source[name]/relative;before=path.read_text();after=before
        for old,new in changes:
            if after.count(old)!=1:raise RuntimeError('Patch context changed: '+relative+' '+old[:55])
            after=after.replace(old,new)
        path.write_text(after)
        patches.append((name,relative,patch,''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))))
    edit('sdk_source','crt/crt.c',[
        ('payload_terminate(int status) {','payload_terminate(int status) {\n  pw_loader_stage("crt_terminate", status);'),
        ('  // clear .bss section','  pw_loader_stage("crt_entered", 0);\n  // clear .bss section'),
        *[(f'  if((err={fn}())) {{\n    return err;\n  }}',
           f'  pw_loader_stage("{tag}_enter", 0);\n  err={fn}();\n  pw_loader_stage("{tag}_return", err);\n  if(err) return err;')
          for fn,tag in [('__klog_init','crt_klog'),('__kernel_init','crt_kernel'),('__rtld_init','crt_rtld'),('__patch_init','crt_patch')]],
        ('  err = main(argc, argv, envp);','  pw_loader_stage("crt_main_enter", 0);\n  err = main(argc, argv, envp);\n  pw_loader_stage("crt_main_return", err);')])
    edit('elfldr','bootstrap-bin.c',[
        ('  // Reserve an address space of sufficient size.','  pw_loader_stage("bin_map_enter", img_size);\n  // Reserve an address space of sufficient size.'),
        ('    return;\n  }\n\n  // Parse program headers.','    pw_loader_stage("bin_map_failed", (long)img);\n    return;\n  }\n  pw_loader_stage("bin_map_return", (long)img);\n\n  // Parse program headers.'),
        ('  entry();','  pw_loader_stage("bin_elf_enter", (long)entry);\n  entry();\n  pw_loader_stage("bin_elf_return", 0);'),
        ('  elfldr_exec(elfldr_elf);','  pw_loader_stage("bin_entered", 0);\n  elfldr_exec(elfldr_elf);\n  pw_loader_stage("bin_return", 0);')])
    edit('elfldr','bootstrap-elf.c',[
        ('  LOG_PUTS("Bootstrapping elfldr.elf...");','  pw_loader_stage("bootstrap_main", fw);\n  LOG_PUTS("Bootstrapping elfldr.elf...");'),
        ('  if(kernel_get_qaflags(qaflags)) {','  pw_loader_stage("bootstrap_qa_enter", 0);\n  if(kernel_get_qaflags(qaflags)) {'),
        ('  if(pt_patch) {','  pw_loader_stage("bootstrap_ptrace_patch", pt_patch);\n  if(pt_patch) {'),
        ('    err = elfldr_spawn(-1, argv, socksrv_elf, socksrv_elf_len);','    pw_loader_stage("bootstrap_spawn_enter", 0);\n    err = elfldr_spawn(-1, argv, socksrv_elf, socksrv_elf_len);\n    pw_loader_stage("bootstrap_spawn_return", err);')])
    edit('elfldr','elfldr.c',[
        ('  if(syscall(0x23b, 0)) {','  pw_loader_stage("rfork_child_enter", getpid());\n  if(syscall(0x23b, 0)) {'),
        ('  if((pid = rfork_thread(', '  pw_loader_stage("rfork_enter", getpid());\n  if((pid = rfork_thread('),
        ('  EV_SET(&evt, pid, EVFILT_PROC, EV_ADD, NOTE_EXEC | NOTE_EXIT, 0, 0);','  pw_loader_stage("rfork_return", pid);\n  EV_SET(&evt, pid, EVFILT_PROC, EV_ADD, NOTE_EXEC | NOTE_EXIT, 0, 0);'),
        ('  while(pt_attach(pid) == -1) {','  pw_loader_stage("attach_enter", pid);\n  while(pt_attach(pid) == -1) {'),
        ('  if(pt_dynlib_process_needed_and_relocate(pid)) {','  pw_loader_stage("attach_return", pid);\n  if(pt_dynlib_process_needed_and_relocate(pid)) {'),
        ('  // Execute the ELF','  pw_loader_stage("elf_exec_enter", pid);\n  // Execute the ELF'),
        # P013: the rfork child stalled before execve, size-correlated, for a bigger payload. It set itself to
        # SCHED_RR MINIMUM priority just before execve; a busier parent (larger payload) could starve it so it
        # never execs and kevent blocks forever. Use MAX, and trace reaching execve.
        ('  sp.sched_priority = sched_get_priority_min(SCHED_RR);','  sp.sched_priority = sched_get_priority_max(SCHED_RR);'),
        ('  execve(SceSpZeroConf, argv, 0);','  pw_loader_stage("child_pre_execve", getpid());\n  execve(SceSpZeroConf, argv, 0);')])
    edit('elfldr','socksrv.c',[
        ('  if(listen(srvfd, 5) != 0) {','  pw_loader_stage("service_listen_enter", port);\n  if(listen(srvfd, 5) != 0) {'),
        ('  while(1) {\n    socklen = sizeof(cliaddr);','  pw_loader_stage("service_listening", port);\n  while(1) {\n    socklen = sizeof(cliaddr);'),
        ('  syscall(SYS_thr_set_name, -1, "elfldr.elf");','  pw_loader_stage("service_main", getpid());\n  syscall(SYS_thr_set_name, -1, "elfldr.elf");')])
    # P010 (P009 on the console: a "fake" (app) SELF stopped in Sysmodule loading /app0/sce_module/libSceFios2.prx,
    # which the loader's SELF child, jailed in SceSpZeroConf's sandbox, does not have; system_exec/npdrm_exec SELFs
    # got ENOEXEC; chroot out of that jail returned EBADF even after the child was escaped to the real root, so
    # syscall 61 is not a usable chroot here). Instead, with --orbisdesk-pid=<pid> --orbisdesk-self=<path> first,
    # the PARENT copies that process's own sandbox to the SELF child through the kernel primitives: rootdir,
    # jaildir and prison of the title (an installed app whose /app0 holds sce_module), plus uid 0, caps and the
    # system authid. No chroot. The child, now rooted in the title's sandbox, execs <path> as seen from it.
    # Without the options the loader behaves as upstream.
    edit('elfldr','selfldr.c',[
        ('#include "selfldr.h"','#include <ps4/kernel.h>\n#include "selfldr.h"'),
        ('''  char *const *argv;
} self_spawn_args_t;''','''  char *const *argv;
  volatile int escape;  // P010: parent sets 1 once the child has adopted the title sandbox, -1 on failure
} self_spawn_args_t;'''),
        ('  self_spawn_args_t args = { stdio, self, self_size, argv };',
         '  self_spawn_args_t args = { stdio, self, self_size, argv, 0 };'),
        ('''  EV_SET(&evt, pid, EVFILT_PROC, EV_ADD, NOTE_EXEC | NOTE_EXIT, 0, 0);''',
         '''  if(argv[1] && argv[2] && !strncmp(argv[1], "--orbisdesk-pid=", 16)
     && !strncmp(argv[2], "--orbisdesk-self=", 17)) {
    int ok = orbisdesk_adopt_child(pid,argv);
    args.escape = ok ? 1 : -1;
  }
  EV_SET(&evt, pid, EVFILT_PROC, EV_ADD, NOTE_EXEC | NOTE_EXIT, 0, 0);'''),
        ('''  close(fd);

  execve(path, args->argv, envp);''','''  close(fd);

  if(args->argv[1] && args->argv[2] && !strncmp(args->argv[1], "--orbisdesk-pid=", 16)
     && !strncmp(args->argv[2], "--orbisdesk-self=", 17)) {
    char *shifted[256 + 2] = { 0 };
    shifted[0] = args->argv[0];
    for(int i = 3, j = 1; args->argv[i] && j < 257; i++, j++) {
      shifted[j] = args->argv[i];
    }
    unlink(path);
    // the parent copies the title's sandbox (rootdir/jaildir/prison) onto this child before it execs
    long ts[2] = { 0, 1000000 };  // 1 ms
    for(int i = 0; i < 5000 && !args->escape; i++) {
      syscall(240, ts, 0);  // SYS_nanosleep
    }
    { char m[80]; int n = sprintf(m, "orbisdesk-p010 escape=%d\\n", args->escape); if(n > 0) write(2, m, n); }
    if(args->escape != 1) {
      klog_puts("orbisdesk: sandbox child not adopted");
      return 0;
    }
    chdir("/");
    execve(args->argv[2] + 17, shifted, envp);
    perror("orbisdesk execve");
    return 0;
  }
  execve(path, args->argv, envp);''')],patch='orbisdesk-sandbox-root')
    edit('elfldr','selfldr.c',[
        ('} self_spawn_args_t;', '} self_spawn_args_t;\n#include "process_loader_self_check.h"'),
        ('  if(!(stack = malloc(PAGE_SIZE))) {','  pw_loader_stage("self_spawn_enter", getpid());\n  if(!(stack = malloc(2 * 1024 * 1024))) {'),
        ('stack + PAGE_SIZE - 8,','stack + 2 * 1024 * 1024 - 8,'),
        ('  self_spawn_args_t *args = (self_spawn_args_t *)ctx;', '  self_spawn_args_t *args = (self_spawn_args_t *)ctx;\n  pw_loader_stage("self_child_entry", getpid());'),
        ('    chdir("/");\n    execve(args->argv[2] + 17, shifted, envp);',
         '    chdir("/");\n    if(!orbisdesk_self_files(args->argv[2] + 17)) return 0;\n    pw_loader_stage("self_exec_enter", getpid());\n    execve(args->argv[2] + 17, shifted, envp);\n    pw_loader_stage("self_exec_errno", errno);'),
        ('  if(kevent(kq, &evt, 1, &evt, 1, 0) < 0) {',
         '  pw_loader_stage("self_wait_exec_enter", pid);\n  if(kevent(kq, &evt, 1, &evt, 1, 0) < 0) {'),
        ('  free(stack);\n  close(kq);\n\n  return pid;',
         '  pw_loader_stage("self_wait_exec_return", pid);\n  free(stack);\n  close(kq);\n\n  return pid;')],patch='self-startup-checks')
    edit('elfldr','socksrv.c',[
        ('  if(magic == PAYLOAD_MAGIC_FILE || magic == PAYLOAD_MAGIC_HTTP) {',
         '  if(magic == 0x3f49444f) {\n    char identity[320];\n    int n=snprintf(identity,sizeof(identity),"{\\"service\\":\\"orbisdesk-loader\\",\\"protocol\\":1,\\"build\\":\\"P011\\",\\"recipe\\":\\"%s\\",\\"pid\\":%d}\\n",ORBISDESK_LOADER_RECIPE,getpid());\n    if(n>0 && n<(int)sizeof(identity)) write(fd,identity,n);\n    return;\n  }\n  if(magic == PAYLOAD_MAGIC_FILE || magic == PAYLOAD_MAGIC_HTTP) {')],patch='self-startup-checks')
    patchdir=ROOT/'patches/process-loader';patchdir.mkdir(parents=True,exist_ok=True)
    for number,tag in (('0001','bootstrap-trace'),('0002','orbisdesk-sandbox-root'),('0003','self-startup-checks')):
        for name in ('sdk_source','elfldr'):
            text=''.join(diff for project,_,kind,diff in patches if project==name and kind==tag)
            if text:(patchdir/(number+'-'+name+'-'+tag+'.patch')).write_text(text)
    shutil.copyfile(ROOT/'native/process_loader_self_check.h',source['elfldr']/'process_loader_self_check.h')
    recipe=hashlib.sha256((''.join(diff for _,_,_,diff in patches)+sha(ROOT/'native/process_loader_stage.h')+sha(ROOT/'native/process_loader_self_check.h')+json.dumps(pins,sort_keys=True)).encode()).hexdigest()
    identity=work/'loader_identity.h';identity.write_text('#define ORBISDESK_LOADER_RECIPE \"'+recipe+'\"\n')
    header=ROOT/'native/process_loader_stage.h';env=dict(os.environ,LLVM_CONFIG='/usr/bin/llvm-config-19')
    includes='-include '+shlex.quote(str(identity))+' -include '+shlex.quote(str(header))+' -isystem '+shlex.quote(str(sdk/'target/include'))
    logdir=ROOT/'build/process-loader-p011';logdir.mkdir(parents=True,exist_ok=True)
    commands=[]
    def run(command):
        commands.append(list(map(str,command)))
        with (logdir/'build.log').open('a') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    crt_flags='-ffreestanding -fno-builtin -nostdlib -fPIC -target x86_64-scei-ps4 -fno-plt -fno-stack-protector -fvisibility-nodllstorageclass=default -Wall -Werror -O1 '
    run(['make','-C',str(source['sdk_source']/'crt'),'-j2','CFLAGS='+crt_flags+includes])
    crt=source['sdk_source']/'crt/crt1.o'
    wrapper=work/'trace-cc.sh';compiler=sdk/'bin/orbis-clang'
    wrapper.write_text('#!/bin/bash\nfor arg in "$@"; do\n if [ "$arg" = -c ]; then exec '+shlex.quote(str(compiler))+' "$@"; fi\ndone\nexec '+shlex.quote(str(compiler))+' -nostartfiles -Wno-unused-command-line-argument "$@" '+shlex.quote(str(crt))+'\n');wrapper.chmod(0o755)
    env['PS4_PAYLOAD_SDK']=str(sdk)
    run(['make','-C',str(source['elfldr']),'-j2','CC='+str(wrapper),'CFLAGS=-fPIC -Wall -Werror -g -mstackrealign '+includes])
    out=ROOT/'out/process-loader-p011';out.mkdir(parents=True,exist_ok=True)
    artifacts={}
    for name in ('elfldr.bin','elfldr.elf','socksrv.elf'):
        target=out/name;shutil.copy2(source['elfldr']/name,target);artifacts[name]={'sha256':sha(target),'bytes':target.stat().st_size}
    bundle=bundle_sources(out,deps,patchdir)
    manifest={'classification':'external_loader_trace','build':'P011','recipe_sha256':recipe,'sandbox_root_option':True,'pins':pins,'work':str(work),'commands':commands,
              'artifacts':artifacts,'trace_file':'/data/orbisdesk/process-loader-p006.jsonl',
              'traced_crt_sha256':sha(crt),'patches':{str(p.relative_to(ROOT)):sha(p) for p in patchdir.glob('*.patch')},
              'trace_header_sha256':sha(header),'source_bundle_sha256':sha(bundle),
              'bootstrap_changes_kernel_state':True,'console_execution':'not_performed'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'out':str(out),'artifacts':artifacts}))
if __name__=='__main__':main()
