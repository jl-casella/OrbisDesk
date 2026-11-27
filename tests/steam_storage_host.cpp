// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the production storage, install-record and shortcut implementations.
#include "steam_storage.h"
#include "steam_shortcut.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <exception>
#include <pthread.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
namespace fs=std::filesystem;
using namespace orbisdesk;
static void note(const char*,...) {}
static void put(const std::string& p,const std::string& b){fs::create_directories(fs::path(p).parent_path());std::ofstream f(p,std::ios::binary);f<<b;assert(f.good());}
static std::string get(const std::string& p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
static std::string home,in,usb0,usb1,state;
static unsigned cases;
static void setup(){
  StorageTestHook({});fs::remove_all(home);fs::create_directories(home);fs::current_path(home);
  in=home+"/internal";state=home+"/state";usb0=home+"/usb0";usb1=home+"/usb1";
  for(auto p:{in,usb0,usb1,home+"/wine-prefix/drive_c"})fs::create_directories(p);
  StorageTestPaths(in,state,{usb0,usb1});
}
static GameStorage volume(unsigned n){auto s=GameStorages().at(n);std::string e;assert(PrepareGameStorage(&s,&e));return s;}
static std::string fixture(unsigned app=70){
  auto root=in+"/"+std::to_string(app);
  put(root+"/game.exe",std::string(1100000,'A'));put(root+"/empty","");
  put(root+"/sub/settings.ini","saved preferences");put(root+"/sub/.orbisdesk-move-token","ordinary nested file");
  put(root+"/steam_settings/configs.user.ini","emulator settings");fs::create_directories(root+"/empty-directory");
  put(root+"/.orbisdesk-install.json","{\"format\":2,\"app\":"+std::to_string(app)+",\"language\":\"spanish\",\"bytes\":1100000,\"launches\":[{\"executable\":\"game.exe\",\"arguments\":\"-test 42\",\"working_dir\":\"sub\",\"present\":true,\"pe\":true,\"arch\":\"x86\"}]}");
  assert(RememberGameStorage(app,volume(0),true));return root;
}
static bool links(unsigned app,const std::string& source,const std::string& dest){
  // No source deletion is permitted before the shortcut transaction.
  assert(fs::exists(source+"/game.exe"));assert(get(dest+"/game.exe")==get(source+"/game.exe"));
  InstalledRecord r;assert(ReadInstallRecord(dest,&r));assert(r.app==app&&r.format==2&&r.launches.size()==1&&r.checks.at(0).pe);
  InstallResult result;result.ok=true;result.launches=r.launches;result.checks=r.checks;
  auto s=WriteGameShortcuts(app,"Test Game",result,dest,r.language,source);return s.prefix&&!s.failed;
}
static MoveResult move(const std::string& source,GameStorage target,std::atomic<bool>& cancel,MoveProgress& p){
  // Console workers must not depend on the host's multi-megabyte default stack.
  struct Work {const std::string& source;GameStorage target;std::atomic<bool>& cancel;MoveProgress& progress;MoveResult result;std::exception_ptr error;};
  Work work{source,target,cancel,p,{},nullptr};pthread_attr_t attr;assert(!pthread_attr_init(&attr));assert(!pthread_attr_setstacksize(&attr,128*1024));
  pthread_t thread;assert(!pthread_create(&thread,&attr,[](void* value)->void*{auto& w=*static_cast<Work*>(value);
    try{w.result=MoveInstalledGame(70,w.source,w.target,w.cancel,true,&w.progress,[&](const std::string& dest){return links(70,w.source,dest);},note);}catch(...){w.error=std::current_exception();}return nullptr;},&work));
  pthread_attr_destroy(&attr);assert(!pthread_join(thread,nullptr));if(work.error)std::rethrow_exception(work.error);return work.result;
}
static void pass(const char* name){++cases;std::cout<<"PASS "<<name<<std::endl;}
int main(int argc,char**argv){
  assert(argc==2);home=argv[1];
  setup();auto src=fixture();auto target=volume(2);std::atomic<bool> cancel{false};MoveProgress p;
  auto r=move(src,target,cancel,p);assert(r.ok&&!r.cleanup_pending&&!fs::exists(src));auto dest=StorageGameRoot(target,70);
  assert(FindGameRoot(70)==dest&&KnownInstalledGame(70)&&GameLocationAvailable(70)&&!PendingGameMove(70));
  assert(p.total==p.copied&&p.total==p.verified&&p.files==p.files_done&&p.total>1100000);
  assert(get(dest+"/sub/.orbisdesk-move-token")=="ordinary nested file"&&fs::is_directory(dest+"/empty-directory"));
  auto link=home+"/wine-prefix/drive_c/users/orbis/Desktop/Test Game.lnk";
  assert(get(link).find("E:\\Steam Games\\70\\game.exe")!=std::string::npos);
  MoveProgress back;r=move(dest,volume(0),cancel,back);assert(r.ok&&!r.cleanup_pending&&FindGameRoot(70)==src&&!fs::exists(dest));
  assert(get(link).find("Z:\\orbisdesk\\steam-games\\70\\game.exe")!=std::string::npos);pass("round trip, exact internal root, bytes, metadata, shortcuts and progress");

  setup();src=fixture();target=volume(2);MoveProgress partial;
  StorageTestHook([&](const char* stage,const std::string&){if(std::string(stage)=="copied_chunk")cancel=true;});
  r=move(src,target,cancel,partial);assert(!r.ok&&r.canceled&&fs::exists(src+"/game.exe")&&PendingGameMove(70));
  StorageTestHook({});cancel=false;MoveProgress resume;r=move(src,target,cancel,resume);assert(r.ok&&!PendingGameMove(70));pass("cancel preserves source and resumes owned partial copy");

  setup();src=fixture();target=volume(2);MoveProgress unplug;bool once=false;
  StorageTestHook([&](const char* stage,const std::string&){if(!once&&std::string(stage)=="copied_chunk"){once=true;fs::rename(usb1,usb1+"-unplugged");}});
  r=move(src,target,cancel,unplug);assert(!r.ok&&fs::exists(src+"/game.exe")&&!fs::exists(usb1));
  StorageTestHook({});fs::rename(usb1+"-unplugged",usb1);MoveProgress replug;r=move(src,target,cancel,replug);assert(r.ok);pass("USB unplug does not recreate mount; reconnect resumes");
  fs::rename(usb1,usb1+"-unplugged");assert(KnownInstalledGame(70)&&!GameLocationAvailable(70)&&FindGameRoot(70)==StorageGameRoot(target,70));
  fs::create_directories(usb1);auto replacement=volume(2);assert(replacement.id!=target.id);put(StorageGameRoot(replacement,70)+"/.orbisdesk-install.json","{\"app\":70}");
  assert(!GameLocationAvailable(70));std::string error;assert(!PrepareGameStorage(&target,&error));pass("offline installs retained and wrong USB identity rejected");

  setup();src=fixture();target=volume(2);MoveProgress corrupt;
  StorageTestHook([](const char* stage,const std::string& path){if(std::string(stage)=="verify"){std::fstream f(path+"/game.exe",std::ios::binary|std::ios::in|std::ios::out);f.put('B');}});
  r=move(src,target,cancel,corrupt);assert(!r.ok&&fs::exists(src+"/game.exe"));StorageTestHook({});MoveProgress retry;r=move(src,target,cancel,retry);assert(r.ok);pass("byte verification detects corruption before source deletion");

  for(const auto* crash:{"destination_published","location_saved"}){
    setup();src=fixture();target=volume(2);MoveProgress crashp;
    StorageTestHook([&](const char* stage,const std::string&){if(std::string(stage)==crash)throw std::runtime_error("simulated process interruption");});
    bool caught=false;try{move(src,target,cancel,crashp);}catch(const std::runtime_error&){caught=true;}assert(caught&&fs::exists(src+"/game.exe"));StorageTestHook({});
    MoveProgress recovered;
    if(std::string(crash)=="location_saved"){assert(FinishGameMove(70,&recovered,&error,note));assert(!fs::exists(src));}
    else {r=move(src,target,cancel,recovered);assert(r.ok&&!r.cleanup_pending);}
    assert(!PendingGameMove(70));pass(crash);
  }

  setup();src=fixture();target=volume(2);put(StorageGameRoot(target,70)+"/user-file","do not touch");MoveProgress occupied;r=move(src,target,cancel,occupied);assert(!r.ok&&get(StorageGameRoot(target,70)+"/user-file")=="do not touch"&&fs::exists(src+"/game.exe"));pass("existing destination never overwritten");
  for(bool fifo:{false,true}){
    setup();src=fixture();target=volume(2);put(home+"/outside","outside");
    if(fifo)assert(!mkfifo((src+"/special").c_str(),0600));else fs::create_symlink(home+"/outside",src+"/special");
    MoveProgress special;r=move(src,target,cancel,special);assert(!r.ok&&get(home+"/outside")=="outside"&&fs::exists(src+"/game.exe"));pass(fifo?"FIFO rejected without blocking":"symlink rejected without following");
  }
  setup();src=fixture();target=volume(2);int fd=open((src+"/large").c_str(),O_WRONLY|O_CREAT,0644);assert(fd>=0&&!ftruncate(fd,5ull<<30));close(fd);
  StorageTestHook([&](const char* stage,const std::string&){if(std::string(stage)=="scanned")cancel=true;});MoveProgress large;r=move(src,target,cancel,large);assert(!r.ok&&large.total>(5ull<<30)&&fs::exists(src+"/large"));cancel=false;pass("64-bit sizes above 4 GiB");
  setup();src=fixture();target=volume(2);auto free=MeasureFreeSpace(target.mount);assert(free.ok&&free.total_bytes>=free.bytes);
  fd=open((src+"/too-large").c_str(),O_WRONLY|O_CREAT,0644);assert(fd>=0&&!ftruncate(fd,free.bytes+1));close(fd);MoveProgress full;r=move(src,target,cancel,full);assert(!r.ok&&r.failure.find("NOT ENOUGH")!=std::string::npos&&fs::exists(src+"/game.exe"));pass("insufficient space stops before copying");
  setup();src=fixture();target=volume(2);put(home+"/wine-prefix/drive_c/users/orbis/Desktop/Test Game.lnk","custom shortcut");MoveProgress custom;r=move(src,target,cancel,custom);assert(r.ok&&get(home+"/wine-prefix/drive_c/users/orbis/Desktop/Test Game.lnk")=="custom shortcut");pass("custom shortcut preserved");
  {
    // Counter-Strike's appinfo shape: Half-Life's engine/content as depotfromapp 70 with sharedinstall "2" (no
    // manifest of its own), a sharedinstall "1" redistributable, a low-violence depot and its own content
    using playden::steam::AppInfo;using playden::steam::DepotInfo;
    auto depot=[](std::uint32_t id,std::optional<std::uint32_t> from,bool shared,std::uint64_t gid,const char* lang,bool lv){
      DepotInfo d;d.id=id;d.depot_from_app=from;d.shared_install=shared;if(gid)d.manifest_gid=gid;d.language=lang;d.low_violence=lv;return d;};
    AppInfo cs;cs.app_id=10;
    cs.depots={depot(1,70,false,0,"",false),depot(6,70,false,0,"",true),depot(75,70,false,0,"spanish",false),
               depot(228988,228980,true,0,"",false),depot(11,std::nullopt,false,111,"",false),depot(5,70,false,0,"",false)};
    AppInfo hl;hl.app_id=70;hl.depots={depot(1,std::nullopt,false,1001,"",false),depot(6,std::nullopt,false,1006,"",true),
                                       depot(75,std::nullopt,false,1075,"spanish",false)};
    AppInfo redist;redist.app_id=228980;redist.depots={depot(228988,std::nullopt,false,2288,"english",false)};
    auto sources=SharedDepotSources(cs);assert((sources==std::vector<std::uint32_t>{70,228980}));
    auto adopted=AdoptSharedDepots(&cs,{{70,hl},{228980,redist}},note);
    assert((adopted==std::set<std::uint32_t>{1,75,228988}));
    auto find=[&](std::uint32_t id)->const DepotInfo&{for(auto& d:cs.depots)if(d.id==id)return d;throw std::runtime_error("depot");};
    assert(find(1).manifest_gid==1001u&&!find(1).shared_install&&find(75).language=="spanish"&&find(75).manifest_gid==1075u);
    assert(find(228988).manifest_gid==2288u&&find(228988).language.empty()&&!find(228988).shared_install);
    assert(!find(6).manifest_gid&&!find(5).manifest_gid&&find(11).manifest_gid==111u);
    pass("depotfromapp engine depots adopted with their language, low violence and unlisted left out");
  }
  {
    // a SteamStub game: its shortcut is the launcher's (steam-open.exe --play <app>) with the game's icon, an
    // uninstall knows it as this game's, and a same-named link of another game's --play stays
    setup();auto root=fixture(71);InstalledRecord r;assert(ReadInstallRecord(root,&r));
    InstallResult result;result.ok=true;result.launches=r.launches;result.checks=r.checks;result.checks.at(0).steamstub=true;
    auto s=WriteGameShortcuts(71,"Stub Game",result,root,r.language);
    assert(s.prefix&&s.launcher&&!s.desktop.empty()&&!s.start.empty()&&s.skipped.empty());
    const auto desktop=home+"/wine-prefix/drive_c/users/orbis/Desktop/Stub Game.lnk";
    const auto bytes=get(desktop);
    assert(bytes.find(std::string(kLauncherImage)+'\0')!=std::string::npos);
    auto utf16=[](const std::string& a){std::string o;for(char c:a){o+=c;o+='\0';}return o;};
    assert(bytes.find(utf16("--play 71"))!=std::string::npos&&bytes.find(utf16("game.exe"))!=std::string::npos);
    auto removed=RemoveGameShortcuts(71,"Stub Game");assert(removed.desktop=="removed"&&removed.start=="removed");
    put(desktop,ShortcutBytes(kLauncherImage,"Stub Game",LauncherArguments(72),kLauncherFolder));
    removed=RemoveGameShortcuts(71,"Stub Game");assert(removed.desktop=="not_ours"&&fs::exists(desktop));
    pass("SteamStub game shortcut through the launcher, removed as its own");
  }
  {
    // a game without SteamStub whose launch mode is ColdClient: the launcher's shortcut too; back to Direct, the exe's
    setup();auto root=fixture(73);InstalledRecord r;assert(ReadInstallRecord(root,&r));
    InstallResult result;result.ok=true;result.launches=r.launches;result.checks=r.checks;
    auto s=WriteGameShortcuts(73,"Cold Game",result,root,r.language,"",true);
    assert(s.prefix&&s.launcher&&!s.desktop.empty());
    const auto desktop=home+"/wine-prefix/drive_c/users/orbis/Desktop/Cold Game.lnk";
    assert(get(desktop).find(std::string(kLauncherImage)+'\0')!=std::string::npos);
    s=WriteGameShortcuts(73,"Cold Game",result,root,r.language);
    assert(s.prefix&&!s.launcher&&!s.desktop.empty()&&get(desktop).find(std::string(kLauncherImage)+'\0')==std::string::npos);
    pass("ColdClient launch mode shortcut through the launcher, Direct back to the exe");
  }
  StorageTestHook({});fs::current_path("/");fs::remove_all(home);std::cout<<"Storage cases passed: "<<cases<<std::endl;
}
