#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual ColdClient state/menu/plan code with simulated pad and temporary game files."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
text = (root/'native/steam/steam_bigpicture.inc.cpp').read_text()
def part(start, end):
    begin = text.index(start)
    return text[begin:text.index(end, begin)]

code = r'''
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdarg>
#include <cstdlib>
#include <deque>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <unistd.h>
#include "steam_ui.h"
#include "steam_bp.h"
#include "pw_steamstub_profile.h"
namespace fs=std::filesystem;
static std::string game_root;
static std::string failure;
static std::deque<unsigned> pad;
static unsigned refreshed;
struct Game {uint32_t app;std::string name;};
static std::string GameRoot(uint32_t) {return game_root;}
static void note(const char*,...) {}
static void trace_note(const char*,...) {}
static bool ReadAll(const std::string& p,std::string* out,int* error) {
    std::ifstream f(p);if(!f){*error=ENOENT;return false;}
    *out=std::string(std::istreambuf_iterator<char>(f),{});return true;
}
static bool WriteText(const std::string& p,const std::string& s,int) {
    if(!failure.empty()&&p.find(failure)!=std::string::npos){failure.clear();return false;}
    std::ofstream f(p);f<<s;return bool(f);
}
namespace orbisdesk {
struct Check {bool present=true,pe=true,steamstub=true;std::string arch="x86";};
struct InstalledRecord {bool steamstub=true,steam_api=true;int format=2;std::vector<std::string> steam_api_paths={"steam_api.dll"};
 std::vector<Check> checks={{}};std::vector<int> launches;std::string language="english",arch="x86";};
struct LaunchEntry {bool ok=true;size_t index=0;std::string image,directory,arguments,skipped;};
struct InstallResult {bool ok;std::vector<int> launches;std::vector<Check> checks;};
struct Shortcuts {bool launcher;};
static bool emulated;
static bool PathExists(const std::string& p){return fs::exists(p);}
static std::string WindowsToUnix(const std::string& p){return p;}
static bool EmulatorEnabled(const std::string&){return emulated;}
static bool RestoreEmulator(const std::string&,void(*)(const char*,...),std::string*){emulated=false;return true;}
static bool ForgetEmulator(const std::string&){emulated=false;return true;}
static bool EnableEmulator(const std::string&,uint32_t,const std::vector<std::string>&,const std::string&,
                           void(*)(const char*,...),std::string*){emulated=true;return true;}
static LaunchEntry ChooseLaunchEntry(const std::vector<int>&,const std::vector<Check>&,const std::string& p,
                                    const std::string&,bool){LaunchEntry e;e.image=p+"/game.exe";e.directory=p;return e;}
static Shortcuts WriteGameShortcuts(uint32_t,const std::string&,const InstallResult&,const std::string&,
                                    const std::string&,const std::string&,bool cold){return {cold};}
}
constexpr const char* kColdClientFile=".orbisdesk-coldclient.txt";
static std::string cold_dir;
#define kColdClientDir cold_dir
constexpr const char* kColdClientWindows="C:\\orbis\\steam\\coldclient";
static void StorageMessage(const std::string&){}
static std::string SecondLauncher(const std::string&){return "";}
static bool Confirm(const std::string&,const std::string&,const std::string&,const std::string&,
                    const std::string&,bool,int){return true;}
static void ToggleEmulator(const Game&,const std::string&,const orbisdesk::InstalledRecord&){orbisdesk::emulated=true;}
template<class F>static void Present(F){} // rendering has its own gallery; exercise the actual menu's state transitions
extern "C" unsigned steam_ui_wait(unsigned mask){assert(!pad.empty());unsigned b=pad.front();pad.pop_front();assert(mask&b);return b;}
extern "C" int steam_ui_show(const char*,const char*){return 0;}
static void RefreshLaunchPlan(uint32_t){++refreshed;}
''' + part('struct ColdClientState {','// a second launcher') + part('bool ColdClientFilesReady(',"// The loader's ini")
code += part("// The loader's ini",'// ---- each installed game')
code += part('struct LaunchPlan {','void RefreshLaunchPlan(')
code += part('enum LaunchMode {','// for steam_client.cpp')
code += part('std::string LaunchModeText(', '// Triangle on an installed')
code += part('bool LaunchModeMenu(const Game& game, const bp::GameView& page, const orbisdesk::InstalledRecord& record) {',
             'std::string ArchName(')
code += r'''
int main(int argc,char** argv){
 assert(argc==2);game_root=std::string(argv[1])+"/one";cold_dir=std::string(argv[1])+"/cold";
 fs::create_directories(game_root);fs::create_directories(cold_dir);
 for(auto n:{"steamclient.dll","steamclient64.dll","steamclient_loader_x86.exe","steamclient_loader_x64.exe",
              "orbisdesk_steamstub_x86.dll","orbisdesk_steamstub_x64.dll"})std::ofstream(cold_dir+"/"+n)<<"fixture";
 std::ofstream(game_root+"/game.exe")<<"EXE unchanged";
 Game game{19680,"fixture"};orbisdesk::InstalledRecord record;bp::GameView page;
 assert(CurrentLaunchMode(game_root)==kModeDirect);
 assert(WriteText(game_root+"/"+kColdClientFile,"on\n",0644));
 assert(CurrentLaunchMode(game_root)==kModeCold&&!ReadColdClient(game_root).compatibility);
 pad={STEAM_UI_DOWN,STEAM_UI_CROSS};assert(LaunchModeMenu(game,page,record));
 assert(CurrentLaunchMode(game_root)==kModeCompat&&ReadColdClient(game_root).compatibility);
 auto marker=game_root+"/game.exe"+PW_STEAMSTUB_SUFFIX;
 std::string contents;int error=0;assert(ReadAll(marker,&contents,&error)&&contents==PW_STEAMSTUB_MAGIC);
 auto plan=PlanLaunch(game.app,record,game_root);assert(plan.ok&&plan.start.image.find("loader_x86.exe")!=std::string::npos);
 fs::remove(marker);orbisdesk::LaunchEntry loader,entry;entry.image=game_root+"/game.exe";
 assert(SetUpColdClient(game,record,entry,&loader)&&fs::exists(marker)); // Play restores the same per-EXE marker
 pad={STEAM_UI_UP,STEAM_UI_CROSS};assert(LaunchModeMenu(game,page,record));
 assert(CurrentLaunchMode(game_root)==kModeCold&&!fs::exists(marker));
 failure=kColdClientFile;unsigned before=refreshed;
 pad={STEAM_UI_DOWN,STEAM_UI_CROSS};assert(!LaunchModeMenu(game,page,record));
 assert(CurrentLaunchMode(game_root)==kModeCold&&!fs::exists(marker)&&refreshed==before);
 failure=PW_STEAMSTUB_SUFFIX;pad={STEAM_UI_DOWN,STEAM_UI_CROSS};assert(!LaunchModeMenu(game,page,record));
 assert(CurrentLaunchMode(game_root)==kModeCold&&refreshed==before);
 pad={STEAM_UI_DOWN,STEAM_UI_CROSS};assert(LaunchModeMenu(game,page,record));
 pad={STEAM_UI_DOWN,STEAM_UI_CROSS};assert(LaunchModeMenu(game,page,record));
 assert(CurrentLaunchMode(game_root)==kModeDirect&&!fs::exists(marker));
 record.steamstub=false;for(auto& check:record.checks)check.steamstub=false;
 assert(!LaunchModeUnavailable(kModeCompat,game_root,record).empty());
 record.steamstub=true;fs::remove(cold_dir+"/orbisdesk_steamstub_x86.dll");
 assert(!LaunchModeUnavailable(kModeCompat,game_root,record).empty());
 assert(ColdClientFilesReady()&&!ColdClientFilesReady(true));
 assert(ReadAll(game_root+"/game.exe",&contents,&error)&&contents=="EXE unchanged");
 assert(!fs::exists(std::string(argv[1])+"/two/game.exe"+PW_STEAMSTUB_SUFFIX));
 puts("PASS actual launch modes: old ColdClient unchanged, opt-in, Play and plan, disable, failures/rollback, missing payload, EXE unchanged");
}
'''
with tempfile.TemporaryDirectory(prefix='orbisdesk-compat-menu-') as temporary:
    path=Path(temporary)
    (path/'check.cpp').write_text(code)
    subprocess.run(['clang++-19','-fuse-ld=lld','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                    '-Wno-unused-function','-fsanitize=address,undefined','-no-pie',
                    '-I'+str(root/'native/steam'),'-I'+str(root/'platform/ps4'),
                    str(path/'check.cpp'),'-o',str(path/'check')],check=True)
    subprocess.run([str(path/'check'),str(path)],check=True,timeout=20)
