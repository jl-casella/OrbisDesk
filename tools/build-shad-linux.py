#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the Linux fork and bind its binary to the exact source diff."""
import argparse,hashlib,json,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--jobs',type=int,default=4)
parser.add_argument('--reuse-configure',action='store_true')
parser.add_argument('--source-cache',action='store_true');args=parser.parse_args()
source=ROOT/'.deps/shadPS4-fork';build=ROOT/'build/shadPS4-linux';build.mkdir(parents=True,exist_ok=True)
cmake=ROOT/'.deps/linux-tools/cmake/data/bin/cmake'
def git(*args):return subprocess.check_output(['git','-c','core.autocrlf=true','-c','diff.ignoreSubmodules=all','-C',str(source),*args])
commit=git('rev-parse','HEAD').decode().strip();patch=git('diff','HEAD','--binary')
if args.source_cache:
    cached=json.loads((ROOT/'build/shad-source-cache.json').read_text())
    if cached.get('source_commit')!=commit or cached.get('source_patch_sha256')!=hashlib.sha256(patch).hexdigest():
        raise SystemExit('Read cache is not bound to this source revision/diff; refresh it before enabling')
(build/'source.patch').write_bytes(patch)
configure=[str(cmake),'-S',str(source),'-B',str(build),'-G','Ninja',
           '-DCMAKE_C_COMPILER=clang-19','-DCMAKE_CXX_COMPILER=clang++-19','-DCMAKE_CXX_FLAGS=-stdlib=libc++',
           '-DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld-19','-DCMAKE_BUILD_TYPE=Release',
           '-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES='+str(ROOT/'tools/shad-linux-toolchain.cmake'),
           '-DORBIS_USE_SOURCE_CACHE='+('ON' if args.source_cache else 'OFF'),
           '-DENABLE_DISCORD_RPC=OFF','-DENABLE_UPDATER=OFF','-DENABLE_TESTS=OFF']
start=time.monotonic()
if args.reuse_configure:
    cache=(build/'CMakeCache.txt').read_text()
    if not (build/'build.ninja').is_file() or 'CMAKE_HOME_DIRECTORY:INTERNAL='+str(source) not in cache:
        raise SystemExit('No matching existing CMake configuration')
else:
    with (build/'configure.log').open('w') as log:subprocess.run(configure,stdout=log,stderr=subprocess.STDOUT,check=True)
command=[str(cmake),'--build',str(build),'--target','shadps4','--parallel',str(args.jobs)]
with (build/'build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
if patch!=git('diff','HEAD','--binary') or commit!=git('rev-parse','HEAD').decode().strip():
    raise SystemExit('Source changed while building; no manifest issued')
binary=build/'shadps4'
manifest={'schema_version':1,'commit':commit,'source_dirty':bool(patch),
          'source_patch_sha256':hashlib.sha256(patch).hexdigest(),
          'executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
          'configure_command':configure,'configure_reused':args.reuse_configure,'build_command':command,'duration_seconds':round(time.monotonic()-start,3),
          'compiler':subprocess.check_output(['clang++-19','--version'],text=True).splitlines()[0],
          'submodules':git('submodule','status','--recursive').decode().splitlines()}
(build/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))
