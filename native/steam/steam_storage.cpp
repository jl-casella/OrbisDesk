// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../platform/ps4/pw_trace.h"  // diagnostic lines only with traces
#include "steam_storage.h"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits>
#include <sys/stat.h>
#include <unistd.h>
#ifndef STEAM_HOST
#include <orbis/libkernel.h>
#endif

namespace orbisdesk {
namespace {
#ifdef STEAM_HOST
std::string internal="steam-games", state="steam-state/locations";
std::vector<std::string> usb;
#else
const std::string internal="/data/orbisdesk/steam-games", state="/data/orbisdesk/steam-locations";
#endif
constexpr char record_name[]=".orbisdesk-install.json", token_name[]=".orbisdesk-move-token";
#ifdef STEAM_STORAGE_TEST
std::function<void(const char*,const std::string&)> test_hook;
#define STORAGE_HOOK(stage,path) do {if(test_hook)test_hook(stage,path);}while(0)
#else
#define STORAGE_HOOK(stage,path) do {}while(0)
#endif
struct Info {std::uint64_t device=0, inode=0, size=0; std::int64_t sec=0,nsec=0; unsigned mode=0;};
bool InfoFd(int fd, Info* info) {
#ifdef STEAM_HOST
  struct stat s{}; if(fstat(fd,&s)) return false;
  info->device=s.st_dev;info->inode=s.st_ino;info->size=s.st_size;info->mode=s.st_mode;
  info->sec=s.st_mtim.tv_sec;info->nsec=s.st_mtim.tv_nsec;
#else
  alignas(8) unsigned char wire[256]={};
  if(sceKernelFstat(fd,reinterpret_cast<OrbisKernelStat*>(wire))) return false;
  std::uint32_t dev,ino;std::uint16_t mode;
  memcpy(&dev,wire,4);memcpy(&ino,wire+4,4);memcpy(&mode,wire+8,2);
  info->device=dev;info->inode=ino;info->mode=mode;
  memcpy(&info->size,wire+72,8);memcpy(&info->sec,wire+40,8);memcpy(&info->nsec,wire+48,8);
#endif
  return true;
}
bool Directory(const std::string& path, Info* result=nullptr) {
  int fd=open(path.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
  if(fd<0)return false;
  Info i;bool ok=InfoFd(fd,&i)&&S_ISDIR(i.mode);close(fd);if(ok&&result)*result=i;return ok;
}
bool Mounted(const std::string& mount, std::uint64_t* device) {
  Info s;if(!Directory(mount,&s))return false;
#ifndef STEAM_HOST
  Info parent;if(!Directory("/mnt",&parent)||s.device==parent.device)return false;
#endif
  *device=s.device;return true;
}
bool Parents(const std::string& path) {
  for(std::size_t at=path.find('/',1);at!=std::string::npos;at=path.find('/',at+1)) {
    auto p=path.substr(0,at);if(mkdir(p.c_str(),0777)&&errno!=EEXIST)return false;
    if(!Directory(p))return false;
  }
  return true;
}
bool Read(const std::string& path,std::string* text) {
  int fd=open(path.c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return false;
  Info info;if(!InfoFd(fd,&info)||!S_ISREG(info.mode)||info.size>65536){close(fd);return false;}
  text->clear();char b[1024];ssize_t n;bool ok=true;
  while((n=read(fd,b,sizeof(b)))>0){text->append(b,static_cast<std::size_t>(n));if(text->size()>65536){ok=false;break;}}
  if(n<0)ok=false;close(fd);return ok;
}
bool All(int fd,const char* p,std::size_t n) {
  while(n){ssize_t k=write(fd,p,n);if(k<0&&errno==EINTR)continue;if(k<=0)return false;p+=k;n-=static_cast<std::size_t>(k);}return true;
}
bool At(int fd,char* p,std::size_t n,std::uint64_t offset){
  while(n){ssize_t k=pread(fd,p,n,static_cast<off_t>(offset));if(k<0&&errno==EINTR)continue;if(k<=0)return false;p+=k;offset+=static_cast<std::size_t>(k);n-=static_cast<std::size_t>(k);}return true;
}
std::string Nonce() {
  static std::atomic<unsigned> n{0};
  return std::to_string(std::chrono::steady_clock::now().time_since_epoch().count())+"-"+std::to_string(++n);
}
bool Write(const std::string& path,const std::string& text) {
  if(!Parents(path))return false;
  auto tmp=path+".tmp-"+Nonce();int fd=open(tmp.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0644);
  if(fd<0)return false;bool ok=All(fd,text.data(),text.size())&&!fsync(fd);if(close(fd))ok=false;
  if(ok&&!rename(tmp.c_str(),path.c_str()))return true;unlink(tmp.c_str());return false;
}
std::string Index(std::uint32_t app){return state+"/"+std::to_string(app)+".location";}
std::string Journal(std::uint32_t app){return state+"/"+std::to_string(app)+".move";}
std::vector<std::string> Fields(const std::string& text) {
  std::vector<std::string> out;std::size_t p=0;
  for(auto e=text.find('\n');e!=std::string::npos;e=text.find('\n',p)){out.push_back(text.substr(p,e-p));p=e+1;}
  return out;
}
std::vector<GameStorage> Volumes() {
  std::vector<GameStorage> out;GameStorage in;in.name="INTERNAL";in.library=internal;in.mount="/data";in.id="internal";
#ifdef STEAM_HOST
  in.mount=internal;
#endif
  out.push_back(in);
  for(unsigned i=0;i<8;i++) {
#ifdef STEAM_HOST
    if(i>=usb.size())break;const auto mount=usb[i];
#else
    const auto mount=std::string("/mnt/usb")+std::to_string(i);
#endif
    GameStorage s;s.name=std::string(1,static_cast<char>('D'+i))+": USB "+std::to_string(i);
    s.mount=mount;s.library=mount+"/Steam Games";s.external=true;
    if(Mounted(mount,&s.device)){Read(s.library+"/.orbisdesk-library-id",&s.id);out.push_back(s);}
  }
  return out;
}
bool Allowed(const std::string& root,std::uint32_t app) {
  if(root==internal+"/"+std::to_string(app))return true;
#ifdef STEAM_HOST
  for(const auto& m:usb)if(root==m+"/Steam Games/"+std::to_string(app))return true;
#else
  for(unsigned i=0;i<8;i++)if(root=="/mnt/usb"+std::to_string(i)+"/Steam Games/"+std::to_string(app))return true;
#endif
  return false;
}
bool RecordMatches(const std::string& root,std::uint32_t app) {
  InstalledRecord record;return ReadInstallRecord(root,&record)&&record.app==app;
}
bool Location(std::uint32_t app,std::vector<std::string>* parts) {
  std::string text;if(!Read(Index(app),&text))return false;*parts=Fields(text);
  return parts->size()==3&&Allowed((*parts)[0],app)&&((*parts)[2]=="installed"||(*parts)[2]=="pending");
}
struct Entry {std::string path;Info info;};
bool Same(const Info& a,const Info& b){return a.device==b.device&&a.inode==b.inode&&a.size==b.size&&a.sec==b.sec&&a.nsec==b.nsec;}
bool List(const std::string& root,const std::string& relative,std::vector<Entry>* files,std::vector<std::string>* dirs,
          const std::atomic<bool>& cancel,std::uint64_t* bytes) {
  if(cancel.load()||dirs->size()+files->size()>500000||relative.size()>3000)return false;
  auto path=root+(relative.empty()?"":"/"+relative);
  int fd=open(path.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(fd<0)return false;
  DIR* dir=fdopendir(fd);if(!dir){close(fd);return false;}
  std::vector<std::string> names;int error=0;
  for(;;){errno=0;auto e=readdir(dir);if(!e){error=errno;break;}std::string n=e->d_name;if(n!="."&&n!="..")names.push_back(n);}
  closedir(dir);if(error)return false;
  std::sort(names.begin(),names.end());
  for(const auto& name:names){
    if(relative.empty()&&name==token_name)continue;
    auto rel=relative.empty()?name:relative+"/"+name;auto p=root+"/"+rel;
    if(Directory(p)){dirs->push_back(rel);if(!List(root,rel,files,dirs,cancel,bytes))return false;}
    else {int f=open(p.c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK);Info info;bool ok=f>=0&&InfoFd(f,&info)&&S_ISREG(info.mode);if(f>=0)close(f);
      if(!ok||info.size>std::numeric_limits<std::uint64_t>::max()-*bytes)return false;
      *bytes+=info.size;files->push_back({rel,info});}
  }
  return true;
}
bool Owned(const std::string& root,const std::string& token){std::string t;return Read(root+"/"+token_name,&t)&&t==token;}
bool RemoveOwned(const std::string& root,const std::string& token) {
  if(!Owned(root,token))return false;
  // Keep the ownership token and install record until all other entries are gone.
  std::function<bool(const std::string&)> remove=[&](const std::string& path){
    int fd=open(path.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(fd<0)return false;
    DIR* d=fdopendir(fd);if(!d){close(fd);return false;}
    std::vector<std::string> names;int error=0;
    for(;;){errno=0;auto e=readdir(d);if(!e){error=errno;break;}std::string n=e->d_name;if(n!="."&&n!=".."&&!(path==root&&(n==token_name||n==record_name)))names.push_back(n);}
    closedir(d);if(error)return false;
    for(const auto& n:names){auto p=path+"/"+n;if(Directory(p)){if(!remove(p)||rmdir(p.c_str()))return false;}else if(unlink(p.c_str()))return false;}
    return true;
  };
  if(!remove(root))return false;
  if(unlink((root+"/"+record_name).c_str())&&errno!=ENOENT)return false;
  if(unlink((root+"/"+token_name).c_str()))return false;
  return !rmdir(root.c_str());
}
} // namespace

std::vector<GameStorage> GameStorages(){auto out=Volumes();for(auto& s:out)s.free=MeasureFreeSpace(s.external?s.mount:s.library);return out;}
bool GameStorageAvailable(const GameStorage& s){
  if(!Directory(s.library))return false;
  if(!s.external)return true;std::uint64_t dev=0;std::string id;
  return Mounted(s.mount,&dev)&&dev==s.device&&Read(s.library+"/.orbisdesk-library-id",&id)&&id==s.id&&!id.empty();
}
bool PrepareGameStorage(GameStorage* s,std::string* error){
  if(s->external){std::uint64_t dev;if(!Mounted(s->mount,&dev)||dev!=s->device){*error="USB DRIVE DISCONNECTED OR CHANGED.";return false;}}
  if(!Parents(s->library+"/")||!Directory(s->library)){*error="COULD NOT CREATE THE GAME LIBRARY.";return false;}
  if(s->external){
    auto path=s->library+"/.orbisdesk-library-id";std::string id;
    if(!Read(path,&id)){auto token=Nonce();int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0644);
      if(fd>=0){bool ok=All(fd,token.data(),token.size())&&!fsync(fd);close(fd);if(!ok){*error="COULD NOT WRITE THE USB LIBRARY ID.";return false;}}
      if(!Read(path,&id)){*error="USB LIBRARY IS NOT WRITABLE.";return false;}}
    if(id.empty()||id.size()>128||id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")!=std::string::npos){*error="INVALID USB LIBRARY ID.";return false;}
    if(!s->id.empty()&&s->id!=id){*error="USB DRIVE CHANGED. REFRESH THE DRIVE LIST.";return false;}s->id=id;
  }
  return true;
}
std::string StorageGameRoot(const GameStorage& s,std::uint32_t app){return s.library+"/"+std::to_string(app);}
bool StorageForGame(const std::string& root,GameStorage* storage){
  for(auto& s:Volumes())if(root.size()>s.library.size()&&root.compare(0,s.library.size()+1,s.library+"/")==0){*storage=s;return !s.external||GameStorageAvailable(s);}return false;
}
bool RememberGameStorage(std::uint32_t app,const GameStorage& s,bool installed){
  auto root=StorageGameRoot(s,app);return Allowed(root,app)&&GameStorageAvailable(s)&&Write(Index(app),root+"\n"+s.id+"\n"+(installed?"installed\n":"pending\n"));
}
bool ForgetGameStorage(std::uint32_t app){return !unlink(Index(app).c_str())||errno==ENOENT;}
std::string FindGameRoot(std::uint32_t app){
  std::vector<std::string> location;bool known=Location(app,&location);
  if(known){GameStorage s;if(StorageForGame(location[0],&s)&&s.id==location[1])return location[0];
    for(const auto& v:Volumes())if(v.id==location[1]&&RecordMatches(StorageGameRoot(v,app),app))return StorageGameRoot(v,app);
    return location[0]; // offline: never silently substitute an internal install
  }
  for(const auto& s:Volumes()){auto root=StorageGameRoot(s,app);if(RecordMatches(root,app))return root;}
  return internal+"/"+std::to_string(app);
}
bool KnownInstalledGame(std::uint32_t app){std::vector<std::string> l;return (Location(app,&l)&&l[2]=="installed")||RecordMatches(FindGameRoot(app),app);}
bool GameLocationAvailable(std::uint32_t app){
  GameStorage storage;const auto root=FindGameRoot(app);if(!StorageForGame(root,&storage))return false;
  std::vector<std::string> l;return !Location(app,&l)||storage.id==l[1];
}
std::string StorageWindowsPath(const std::string& root,const std::string& relative){
  std::string path;
  if(root.compare(0,6,"/data/")==0)path="Z:"+root.substr(5);
  for(unsigned i=0;i<8&&path.empty();i++){
#ifdef STEAM_HOST
    if(i>=usb.size())break;auto mount=usb[i];
#else
    auto mount=std::string("/mnt/usb")+std::to_string(i);
#endif
    if(root.compare(0,mount.size()+1,mount+"/")==0)path=std::string(1,static_cast<char>('D'+i))+":"+root.substr(mount.size());
  }
#ifdef STEAM_HOST
  if(path.empty()&&root.compare(0,internal.size()+1,internal+"/")==0)path="Z:\\orbisdesk\\steam-games\\"+root.substr(internal.size()+1);
#endif
  if(path.empty())return {};if(!relative.empty())path+="/"+relative;for(auto& c:path)if(c=='/')c='\\';return path;
}
bool PendingGameMove(std::uint32_t app){return PathExists(Journal(app));}
bool PendingMoveRoute(std::uint32_t app,std::string* source,GameStorage* target){
  std::string text;if(!Read(Journal(app),&text))return false;auto f=Fields(text);
  if(f.size()!=5||!Allowed(f[0],app)||!Allowed(f[1],app)||!StorageForGame(f[1],target)||target->id!=f[3])return false;
  *source=f[0];return true;
}
bool FinishGameMove(std::uint32_t app,MoveProgress* progress,std::string* error,NoteFn note){
  std::string text;auto fail=[&](const char* msg){*error=msg;return false;};
  if(!Read(Journal(app),&text))return !PathExists(Journal(app));auto f=Fields(text);
  if(f.size()!=5||!Allowed(f[0],app)||!Allowed(f[1],app)||f[0]==f[1])return fail("MOVE JOURNAL IS INVALID; NOTHING WAS DELETED.");
  // Only committed moves may remove their old source. A pre-commit move keeps both paths for recovery.
  GameStorage source,target;
  if(!StorageForGame(f[0],&source)||!StorageForGame(f[1],&target)||!GameStorageAvailable(target)||!RecordMatches(f[1],app))return fail("RECONNECT BOTH DRIVES TO FINISH THE MOVE.");
  std::vector<std::string> l;if(!Location(app,&l)||l[0]!=f[1]||l[1]!=target.id)return fail("DESTINATION LOCATION DOES NOT MATCH; SOURCE WAS KEPT.");
  if(f[4]!="committed"){
    if(!Owned(f[0],f[2])||!Owned(f[1],f[2]))return fail("AN INTERRUPTED MOVE NEEDS TO BE RESUMED TO THE SAME DRIVE.");
    if(!Write(Journal(app),f[0]+"\n"+f[1]+"\n"+f[2]+"\n"+f[3]+"\ncommitted\n"))return fail("COULD NOT RECOVER THE MOVE JOURNAL.");
  }
  if(progress)progress->phase=4;
  if(PathExists(f[0])){
    // A crash between removing the token and rmdir leaves an empty reservation.
    // Without the token, only rmdir is allowed: never recurse into unowned data.
    const bool removed=Owned(f[0],f[2])?RemoveOwned(f[0],f[2]):!rmdir(f[0].c_str());
    if(!removed)return fail("GAME MOVED, BUT THE OLD COPY COULD NOT BE REMOVED. RETRY CLEANUP.");
  }
  unlink((f[1]+"/"+token_name).c_str());
  if(unlink(Journal(app).c_str()))return fail("COULD NOT CLEAR THE MOVE JOURNAL.");
  if (pw_trace_on()) note("PWSTEAM storage cleanup ok=1");return true;
}

MoveResult MoveInstalledGame(std::uint32_t app,const std::string& source,GameStorage target,
                            const std::atomic<bool>& cancel,bool unmeasured_ok,MoveProgress* p,
                            const std::function<bool(const std::string&)>& shortcuts,NoteFn note){
  MoveResult result;auto fail=[&](const std::string& msg){result.failure=msg;result.canceled=cancel.load();return result;};
  if (pw_trace_on()) note("PWSTEAM storage move phase=worker_enter");
  GameStorage from;if(!Allowed(source,app)||!Directory(source)||!StorageForGame(source,&from)||!RecordMatches(source,app))return fail("SOURCE GAME OR DRIVE IS UNAVAILABLE.");
  std::vector<std::string> location;if(Location(app,&location)&&location[0]==source&&location[1]!=from.id)return fail("SOURCE USB DRIVE CHANGED.");
  if(!PrepareGameStorage(&target,&result.failure))return result;
  const auto dest=StorageGameRoot(target,app);result.destination=dest;
  if(dest==source||!Allowed(dest,app))return fail("CHOOSE A DIFFERENT DRIVE.");
  std::string token=Nonce(),journal;auto stage=target.library+"/.orbisdesk-move-"+std::to_string(app);
  if(Read(Journal(app),&journal)){
    auto f=Fields(journal);if(f.size()!=5||f[0]!=source||f[1]!=dest||f[3]!=target.id)return fail("FINISH THE PREVIOUS MOVE FIRST.");
    token=f[2];if(f[4]=="committed"){result.ok=true;result.cleanup_pending=!FinishGameMove(app,p,&result.failure,note);return result;}
  }else{
    if(PathExists(dest)||PathExists(stage)||PathExists(source+"/"+token_name))return fail("DESTINATION OR MOVE MARKER ALREADY EXISTS. NOTHING WAS OVERWRITTEN.");
    if(!Write(Journal(app),source+"\n"+dest+"\n"+token+"\n"+target.id+"\ncopying\n"))return fail("COULD NOT SAVE THE MOVE JOURNAL.");
  }
  if(!PathExists(dest)&&PathExists(stage)&&!RemoveOwned(stage,token))return fail("COULD NOT RESET THE PREVIOUS PARTIAL COPY.");
  std::vector<Entry> files;std::vector<std::string> dirs;std::uint64_t total=0;
  if(!List(source,"",&files,&dirs,cancel,&total))return fail(cancel.load()?"MOVE CANCELED; SOURCE KEPT.":"COULD NOT SCAN THE GAME. LINKS AND SPECIAL FILES ARE NOT MOVED.");
  p->total=total;p->files=files.size();target.free=MeasureFreeSpace(target.mount);
  if (pw_trace_on()) note("PWSTEAM storage move phase=scanned files=%llu bytes=%llu",static_cast<unsigned long long>(files.size()),static_cast<unsigned long long>(total));
  STORAGE_HOOK("scanned",source);
  if(target.free.ok&&!PathExists(dest)&&(total>target.free.bytes||target.free.bytes-total<(512ull<<20)))return fail("NOT ENOUGH FREE SPACE ON THE DESTINATION.");
  if(!target.free.ok&&!unmeasured_ok)return fail("COULD NOT MEASURE THE DESTINATION FREE SPACE.");
  const bool existing=PathExists(dest);
  if(existing&&!Owned(dest,token))return fail("DESTINATION IS NOT THIS MOVE'S COPY.");
  if(!existing){
    if(PathExists(stage)&&!RemoveOwned(stage,token))return fail("COULD NOT RESET THE PREVIOUS PARTIAL COPY.");
    if(mkdir(stage.c_str(),0777))return fail("COULD NOT CREATE THE MOVE FOLDER.");
    if(!Write(stage+"/"+token_name,token)){rmdir(stage.c_str());return fail("COULD NOT CREATE THE MOVE FOLDER.");}
    for(const auto& rel:dirs)if(!GameStorageAvailable(target)||mkdir((stage+"/"+rel).c_str(),0777))return fail("DESTINATION DRIVE DISCONNECTED OR FOLDER CREATION FAILED.");
    // Native worker stacks are smaller than host defaults. Keep bulk I/O on the heap.
    p->phase=1;std::vector<char> buffer(262144);
    if (pw_trace_on()) note("PWSTEAM storage move phase=copy");
    for(const auto& e:files){
      if(cancel.load()||!GameStorageAvailable(from)||!GameStorageAvailable(target))return fail("MOVE STOPPED; SOURCE KEPT. RECONNECT THE DRIVES AND RESUME.");
      int in=open((source+"/"+e.path).c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK);Info before;
      if(in<0||!InfoFd(in,&before)||!Same(before,e.info)){if(in>=0)close(in);return fail("SOURCE CHANGED DURING THE MOVE.");}
      int out=open((stage+"/"+e.path).c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0644);bool ok=out>=0;std::uint64_t copied=0;
      while(ok&&copied<e.info.size){if(cancel.load()||!GameStorageAvailable(from)||!GameStorageAvailable(target)){ok=false;break;}
        auto want=static_cast<std::size_t>(std::min<std::uint64_t>(buffer.size(),e.info.size-copied));ssize_t n=read(in,buffer.data(),want);
        if(n<0&&errno==EINTR)continue;if(n<=0||!All(out,buffer.data(),static_cast<std::size_t>(n))){ok=false;break;}copied+=n;p->copied.fetch_add(n);STORAGE_HOOK("copied_chunk",stage+"/"+e.path);}
      if(out>=0){if(fsync(out))ok=false;if(close(out))ok=false;}
      Info after;if(!InfoFd(in,&after)||!Same(before,after))ok=false;close(in);if(!ok)return fail("COPY STOPPED OR SOURCE CHANGED; ORIGINAL FILES KEPT.");
    }
  }else p->copied=total;
  p->phase=2;std::vector<char> a(262144),b(262144);const auto copied_root=existing?dest:stage;
  if (pw_trace_on()) note("PWSTEAM storage move phase=verify");
  STORAGE_HOOK("verify",copied_root);
  for(const auto& e:files){
    if(cancel.load()||!GameStorageAvailable(from)||!GameStorageAvailable(target))return fail("VERIFY STOPPED; SOURCE KEPT.");
    int in=open((source+"/"+e.path).c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK),out=open((copied_root+"/"+e.path).c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
    Info si,di;bool ok=in>=0&&out>=0&&InfoFd(in,&si)&&Same(si,e.info)&&InfoFd(out,&di)&&di.size==e.info.size&&S_ISREG(di.mode);
    std::uint64_t done=0;
    while(ok&&done<e.info.size){auto n=static_cast<std::size_t>(std::min<std::uint64_t>(a.size(),e.info.size-done));
      if(cancel.load()||!GameStorageAvailable(from)||!GameStorageAvailable(target)){ok=false;break;}
      if(!At(in,a.data(),n,done)||!At(out,b.data(),n,done)||memcmp(a.data(),b.data(),n)){ok=false;break;}done+=n;p->verified.fetch_add(n);}
    if(in>=0)close(in);if(out>=0)close(out);if(!ok)return fail("VERIFICATION FAILED; SOURCE KEPT.");++p->files_done;
  }
  // Verify the tree did not grow or change while earlier files were copied.
  std::vector<Entry> check;std::vector<std::string> checkdirs;std::uint64_t checkbytes=0;
  if(!List(source,"",&check,&checkdirs,cancel,&checkbytes)||check.size()!=files.size()||checkdirs!=dirs||checkbytes!=total)return fail("SOURCE CHANGED; SOURCE KEPT.");
  for(std::size_t i=0;i<files.size();i++)if(check[i].path!=files[i].path||!Same(check[i].info,files[i].info))return fail("SOURCE CHANGED; SOURCE KEPT.");
  if(!GameStorageAvailable(from)||!GameStorageAvailable(target)||cancel.load())return fail("MOVE STOPPED BEFORE COMMIT; SOURCE KEPT.");
  p->phase=3;
  if (pw_trace_on()) note("PWSTEAM storage move phase=commit");
  if(!existing){
    if(mkdir(dest.c_str(),0777))return fail("DESTINATION ALREADY EXISTS; SOURCE KEPT.");
    if(rename(stage.c_str(),dest.c_str())){rmdir(dest.c_str());return fail("COULD NOT PUBLISH THE VERIFIED COPY; SOURCE KEPT.");}
  }
  STORAGE_HOOK("destination_published",dest);
  if(!RecordMatches(dest,app)||!shortcuts(dest))return fail("COULD NOT UPDATE THE GAME SHORTCUTS; SOURCE KEPT. RESUME THE MOVE.");
  if(!Write(source+"/"+token_name,token)||!RememberGameStorage(app,target,true))return fail("COULD NOT COMMIT THE LOCATION; SOURCE KEPT.");
  STORAGE_HOOK("location_saved",dest);
  if(!Write(Journal(app),source+"\n"+dest+"\n"+token+"\n"+target.id+"\ncommitted\n"))return fail("LOCATION SAVED; SOURCE KEPT. MOVE JOURNAL NEEDS RECOVERY.");
  result.ok=true;result.cleanup_pending=!FinishGameMove(app,p,&result.failure,note);
  note("PWSTEAM storage move ok=1 bytes=%llu cleanup_pending=%d",static_cast<unsigned long long>(total),result.cleanup_pending);
  return result;
}
#ifdef STEAM_HOST
void StorageTestPaths(const std::string& in,const std::string& st,const std::vector<std::string>& volumes){internal=in;state=st;usb=volumes;}
#ifdef STEAM_STORAGE_TEST
void StorageTestHook(std::function<void(const char*,const std::string&)> hook){test_hook=std::move(hook);}
#endif
#endif
} // namespace orbisdesk
