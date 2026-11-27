#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the actual storage menu (Big Picture's install location picker and move modal) with simulated pad
events and real host I/O. Each frame's text (steam_bp.h's summary) is checked; the frames are drawn by the
real painter into a host canvas."""
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
code=r'''
#define main storage_fault_suite_main
#include "steam_storage_host.cpp"
#undef main
#include "steam_ui.h"
#include "steam_bp.h"
#include "steam_draw.h"
#include <deque>
#include <thread>
#include <chrono>
struct Game {std::uint32_t app;std::string name;};
static std::string GameRoot(std::uint32_t app){return FindGameRoot(app);}
static std::string Size(std::uint64_t n){return std::to_string(n)+" B";}
static std::string Upper(std::string s){for(auto& c:s)if(c>='a'&&c<='z')c=static_cast<char>(c-32);return s;}
#define PAGE_FOOTER "\n\x02"
static std::deque<unsigned> buttons;
static std::vector<std::string> pages;
static bool live;
static std::vector<uint32_t> frame(1280*720);
extern "C" int pw_hw_steam_exe_running(const char*){return live;}
extern "C" int steam_ui_show(const char* text,const char*){pages.push_back(text);assert(pages.back().size()<4096);return 0;}
extern "C" void steam_ui_begin(sd_canvas* c){sd_begin(c,frame.data(),1280,720,1280);}
extern "C" void steam_ui_end(const char* summary){pages.push_back(summary);}
extern "C" unsigned steam_ui_wait(unsigned mask){assert(!buttons.empty());auto n=buttons.front();buttons.pop_front();assert(n&mask);return n;}
extern "C" unsigned steam_ui_take(){return 0;}
static int launch_plans=0;
static void RefreshLaunchPlan(std::uint32_t){++launch_plans;}
static bool ColdClientOn(const std::string&){return false;}
#define trace_note(...) note(__VA_ARGS__)  // steam_client.cpp: traces on in this check
#include "steam_storage_ui.inc.cpp"
static bool seen(const char* what){for(const auto& p:pages)if(p.find(what)!=std::string::npos)return true;return false;}
int main(int argc,char**argv){
 assert(argc==2);home=argv[1];setup();fixture();
 buttons={STEAM_UI_DOWN,STEAM_UI_DOWN,STEAM_UI_SQUARE,STEAM_UI_CROSS};GameStorage selected;bool make_default=false;
 assert(ChooseStorage("INSTALL\nTest Game","",&selected,1000,true,&make_default)&&selected.library==usb1+"/Steam Games"&&make_default);
 if(pages.front().find("Internal storage")==std::string::npos)std::cerr<<pages.front()<<std::endl;
 assert(pages.front().find("Internal storage")!=std::string::npos&&pages.front().find("USB 1")!=std::string::npos);
 assert(pages.front().find(" free")!=std::string::npos&&pages.front().find("AFTER INSTALL")!=std::string::npos);
 assert(pages.front().find("Test Game")!=std::string::npos&&pages.back().find("Install here every time")!=std::string::npos);
 assert(buttons.empty());
 pages.clear();live=true;buttons={STEAM_UI_CIRCLE};MoveGame({70,"Test Game"});
 assert(pages.back().find("CLOSE THIS GAME")!=std::string::npos&&fs::exists(in+"/70/game.exe")&&!PendingGameMove(70));
 live=false;buttons={STEAM_UI_DOWN,STEAM_UI_DOWN,STEAM_UI_CROSS,STEAM_UI_CROSS,STEAM_UI_CIRCLE};pages.clear();
 assert(!MoveGame({70,"Test Game"}));
 assert(buttons.empty()&&!fs::exists(in+"/70")&&KnownInstalledGame(70));
 assert(seen("CURRENT LOCATION")&&seen("MOVE GAME")&&seen("FREE ON E: AFTER THE MOVE"));
 assert(pages.back().find("Game moved")!=std::string::npos&&pages.back().find("E:\\Steam Games\\70")!=std::string::npos);
 fs::current_path("/");fs::remove_all(home);std::cout<<"PASS actual storage picker, space labels, default toggle, running-game refusal and move flow"<<std::endl;
}
'''
def patched_playden(work):
    # the Playden copy the builders compile: upstream plus native/steam/patches, in order
    import shutil
    shutil.copytree(r/'upstream/playden-ps5/src',work/'playden/src')
    for patch in sorted((r/'native/steam/patches').glob('*.patch')):
        subprocess.run(['patch','--fuzz=0','-s','-p1','-i',str(patch)],cwd=work/'playden',check=True)
    return work/'playden/src'
with tempfile.TemporaryDirectory(prefix='orbisdesk-storage-ui-') as temp:
    work=pathlib.Path(temp);(work/'ui.cpp').write_text(code)
    playden=patched_playden(work)
    sources=['native/steam/steam_storage.cpp','native/steam/steam_install.cpp','native/steam/steam_shortcut.cpp',
             'native/steam/steam_bp.cpp',
             str(playden/'steam/backend/json.cpp'),str(playden/'steam/backend/game_path.cpp')]
    stb=['-I'+str(r/'.deps/sdk/OpenOrbis/PS4Toolchain/include/stb')]
    subprocess.run(['clang','-c','-DSTEAM_HOST','-g','-O1',*stb,str(r/'native/steam/steam_draw.c'),'-o',str(work/'draw.o')],check=True)
    subprocess.run(['clang++','-std=c++17','-DSTEAM_HOST','-DSTEAM_STORAGE_TEST','-g','-O1',
        '-fsanitize=address,undefined','-fno-sanitize=vptr','-mllvm','-asan-globals=0',
        '-no-pie','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-pthread',
        '-I'+str(r/'native/steam'),'-I'+str(r/'tests'),'-I'+str(playden),
        '-I'+str(r/'build/steam-deps-ps4/prefix/include'),str(work/'ui.cpp'),
        *[s if s.startswith('/') else str(r/s) for s in sources],str(work/'draw.o'),'-o',str(work/'ui')],check=True)
    subprocess.run([str(work/'ui'),str(work/'sandbox')],check=True,timeout=60)
