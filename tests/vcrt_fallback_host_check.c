/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* VC++ runtime fallback host check (docs/VCRUNTIME_FALLBACK.md): native/hw_install.h's installer against a
 * simulated package (HW_INSTALL_ROOT) and console (HW_INSTALL_DATA), both temporary folders given by
 * tests/test_vcrt_fallback_host.py. The package carries the prefix's VC++ DLLs, their second copies in
 * wine/lib/wine/vcrt-fallback and its list.txt, as tools/build-wine-hardware.py writes them. Starts:
 *   1. a new build over a console where vc_redist replaced syswow64/vcruntime140.dll with Microsoft's: that copy
 *      stays, a missing VC++ DLL and an older Wine copy are installed, a non-VC++ file is replaced as before;
 *   2. the same build after the redistributable's uninstall deleted that copy: Wine's comes back from
 *      vcrt-fallback, while a Microsoft copy of another VC++ DLL is not touched;
 *   3. after a failed install whose rollback deleted the copies it had put in place (Wine's MSI keeps no
 *      backup): both come back as Wine's;
 *   4. a runtime uploaded over FTP (--runtime-outside-package: no install.txt in the package): still restored;
 *   5. a damaged fallback copy: refused by its SHA-256, nothing half-written is left;
 *   6. a good copy again, then nothing missing.
 * Host model only: no PS4 file system, no Wine, no MSI. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define HW_BUILD "VCRTCHECK"
static void note(const char *format,...) __attribute__((format(printf,1,2)));
static void note(const char *format,...){va_list a;va_start(a,format);vfprintf(stderr,format,a);va_end(a);}
static int pw_trace_on(void){return 1;}  /* platform/ps4/pw_trace.h: traces on, every line */
static char *read_whole(const char *path,size_t *size)
{
    FILE *f=fopen(path,"rb");if(!f)return NULL;
    size_t cap=1<<16,got=0;char *data=malloc(cap+1);
    for(size_t n;data&&(n=fread(data+got,1,cap-got,f))>0;){
        got+=n;
        if(got==cap){char *g=realloc(data,cap*2+1);if(!g){free(data);data=NULL;}else{data=g;cap*=2;}}
    }
    fclose(f);if(!data)return NULL;
    data[got]=0;*size=got;return data;
}
static pthread_mutex_t screen_lock=PTHREAD_MUTEX_INITIALIZER;
static void draw_screen(int percent,const char *state,const char *detail){(void)percent;(void)state;(void)detail;}
static int pw_wine_stat(const char *path,struct stat *st){return stat(path,st);}
static int sceKernelRename(const char *from,const char *to){return rename(from,to);}
static uint64_t sceKernelGetProcessTime(void){return 0;}
#include "hw_install.h"

static int failures;
#define CHECK(c,...) do{if(!(c)){failures++;fprintf(stderr,"FAIL %s:%d: ",__FILE__,__LINE__);fprintf(stderr,__VA_ARGS__);fputc('\n',stderr);}}while(0)

/* a 0x200-byte PE-like file: a Wine builtin carries the signature after the DOS header, Microsoft's the DOS stub */
static size_t make_dll(char *out,int wine,char tag)
{
    static const char stub[]="\x0e\x1f\xba\x0e\x00\xb4\x09\xcd\x21\xb8\x01\x4c\xcd\x21This program cannot";
    memset(out,tag,0x200);memcpy(out,"MZ",2);
    if(wine){memset(out+0x40,0,32);memcpy(out+0x40,"Wine builtin DLL",16);}
    else memcpy(out+0x40,stub,sizeof(stub)-1);
    return 0x200;
}
static void put(const char *root,const char *path,const char *data,size_t size)
{
    char full[PATH_MAX];snprintf(full,sizeof(full),"%s/%s",root,path);
    char *slash=strrchr(full,'/');*slash=0;hw_install_mkdirs(full,0777);*slash='/';
    FILE *f=fopen(full,"wb");if(!f||fwrite(data,1,size,f)!=size){perror(full);exit(2);}
    fclose(f);
}
static int same(const char *root,const char *path,const char *data,size_t size)
{
    char full[PATH_MAX];size_t got=0;snprintf(full,sizeof(full),"%s/%s",root,path);
    char *text=read_whole(full,&got);
    int r=text&&got==size&&!memcmp(text,data,size);free(text);return r;
}
static int exists(const char *root,const char *path)
{char full[PATH_MAX];struct stat st;snprintf(full,sizeof(full),"%s/%s",root,path);return !stat(full,&st);}
static void sha_of(const char *data,size_t size,char out[65]){hw_sha256 s;hw_sha_init(&s);hw_sha_update(&s,data,size);hw_sha_hex(&s,out);}

#define W32 "wine-prefix/drive_c/windows/syswow64/"
#define W64 "wine-prefix/drive_c/windows/system32/"
#define FB "wine/lib/wine/vcrt-fallback/"
int main(void)
{
    static char vcrt[0x200],concrt[0x200],msvcp[0x200],other[0x200],ms_vcrt[0x200],ms_concrt[0x200],old_msvcp[0x200],ms_other[0x200];
    size_t n=make_dll(vcrt,1,'a');make_dll(concrt,1,'b');make_dll(msvcp,1,'c');make_dll(other,1,'d');
    make_dll(ms_vcrt,0,'A');make_dll(ms_concrt,0,'B');make_dll(old_msvcp,1,'C');make_dll(ms_other,0,'D');
    const struct {const char *path,*fallback,*data;} pkg[]={
        {W32 "vcruntime140.dll","syswow64/vcruntime140.dll",vcrt},{W32 "concrt140.dll","syswow64/concrt140.dll",concrt},
        {W64 "msvcp140.dll","system32/msvcp140.dll",msvcp},{W64 "other.dll",NULL,other}};
    enum {N=sizeof(pkg)/sizeof(*pkg)};
    /* the fallback list (ORBISDESK-VCRT 1) and the package's install.txt (tools/build-wine-hardware.py's formats) */
    char fallback[4096],list[16384];size_t fused=0,used=0;
    fused+=(size_t)snprintf(fallback+fused,sizeof(fallback)-fused,"ORBISDESK-VCRT 1\n");
    used+=(size_t)snprintf(list+used,sizeof(list)-used,"ORBISDESK-INSTALL 1\nB VCRTCHECK\nH orbis\nT 0\nW wine-prefix\n");
    for(unsigned i=0;i<N;i++)if(pkg[i].fallback)used+=(size_t)snprintf(list+used,sizeof(list)-used,"V %s\n",pkg[i].path);
    used+=(size_t)snprintf(list+used,sizeof(list)-used,"D " W32 "\nD " W64 "\nD " FB "syswow64\nD " FB "system32\n");
    for(unsigned i=0;i<N;i++){
        char sha[65],copy[PATH_MAX];sha_of(pkg[i].data,n,sha);
        put(HW_INSTALL_ROOT,pkg[i].path,pkg[i].data,n);
        used+=(size_t)snprintf(list+used,sizeof(list)-used,"F %s %zu %s\n",sha,n,pkg[i].path);
        if(!pkg[i].fallback)continue;
        snprintf(copy,sizeof(copy),FB "%s",pkg[i].fallback);
        put(HW_INSTALL_ROOT,copy,pkg[i].data,n);
        used+=(size_t)snprintf(list+used,sizeof(list)-used,"F %s %zu %s\n",sha,n,copy);
        fused+=(size_t)snprintf(fallback+fused,sizeof(fallback)-fused,"%s %zu %s\n",sha,n,pkg[i].fallback);
    }
    {char sha[65];sha_of(fallback,fused,sha);put(HW_INSTALL_ROOT,FB "list.txt",fallback,fused);
     used+=(size_t)snprintf(list+used,sizeof(list)-used,"F %s %zu " FB "list.txt\n",sha,fused);}
    put(HW_INSTALL_ROOT,"install.txt",list,used);
    /* the console: vc_redist's vcruntime140, no concrt140, an older Wine msvcp140, a non-VC++ file to replace */
    put(HW_INSTALL_DATA,W32 "vcruntime140.dll",ms_vcrt,n);
    put(HW_INSTALL_DATA,W64 "msvcp140.dll",old_msvcp,n);
    put(HW_INSTALL_DATA,W64 "other.dll",ms_other,n);
    hw_install_mkdirs(HW_INSTALL_DATA "/orbisdesk",0777);

    CHECK(hw_install_wine_builtin(HW_INSTALL_ROOT "/" W32 "vcruntime140.dll")==1,"package copy is a Wine builtin");
    CHECK(hw_install_wine_builtin(HW_INSTALL_DATA "/" W32 "vcruntime140.dll")==0,"Microsoft copy is not");
    CHECK(hw_install_wine_builtin(HW_INSTALL_DATA "/" W32 "concrt140.dll")==-1,"absent file");

    char detail[128]="";
    fprintf(stderr,"-- start 1: new build\n");
    CHECK(!hw_install_runtime(detail,sizeof(detail)),"install 1 failed: %s",detail);
    CHECK(same(HW_INSTALL_DATA,W32 "vcruntime140.dll",ms_vcrt,n),"Microsoft's vcruntime140 must stay");
    CHECK(same(HW_INSTALL_DATA,W32 "concrt140.dll",concrt,n),"missing concrt140 must be installed");
    CHECK(same(HW_INSTALL_DATA,W64 "msvcp140.dll",msvcp,n),"an older Wine msvcp140 must be updated");
    CHECK(same(HW_INSTALL_DATA,W64 "other.dll",other,n),"a non-VC++ file is replaced as before");
    CHECK(same(HW_INSTALL_DATA,FB "syswow64/vcruntime140.dll",vcrt,n),"the fallback copy is installed");

    fprintf(stderr,"-- start 2: after the redistributable's uninstall\n");
    CHECK(!unlink(HW_INSTALL_DATA "/" W32 "vcruntime140.dll"),"simulated uninstall");
    put(HW_INSTALL_DATA,W32 "concrt140.dll",ms_concrt,n);   /* another redistributable's copy, still installed */
    CHECK(!hw_install_runtime(detail,sizeof(detail)),"start 2 failed: %s",detail);
    CHECK(same(HW_INSTALL_DATA,W32 "vcruntime140.dll",vcrt,n),"deleted vcruntime140 must come back as Wine's");
    CHECK(same(HW_INSTALL_DATA,W32 "concrt140.dll",ms_concrt,n),"a present Microsoft copy is never touched");

    fprintf(stderr,"-- start 3: after a failed install rolled back\n");
    /* the rollback's RemoveFiles deletes what InstallFiles put over Wine's copies, Microsoft's or Wine's */
    put(HW_INSTALL_DATA,W32 "vcruntime140.dll",ms_vcrt,n);
    CHECK(!unlink(HW_INSTALL_DATA "/" W32 "vcruntime140.dll")&&!unlink(HW_INSTALL_DATA "/" W32 "concrt140.dll"),"simulated rollback");
    CHECK(!hw_install_runtime(detail,sizeof(detail)),"start 3 failed: %s",detail);
    CHECK(same(HW_INSTALL_DATA,W32 "vcruntime140.dll",vcrt,n),"rolled-back vcruntime140 must come back as Wine's");
    CHECK(same(HW_INSTALL_DATA,W32 "concrt140.dll",concrt,n),"rolled-back concrt140 must come back as Wine's");

    fprintf(stderr,"-- start 4: runtime uploaded over FTP (no install.txt in the package)\n");
    CHECK(!unlink(HW_INSTALL_ROOT "/install.txt"),"simulated --runtime-outside-package");
    CHECK(!unlink(HW_INSTALL_DATA "/" W64 "msvcp140.dll"),"simulated uninstall of the x64 copy");
    CHECK(!hw_install_runtime(detail,sizeof(detail)),"start 4 failed: %s",detail);
    CHECK(same(HW_INSTALL_DATA,W64 "msvcp140.dll",msvcp,n),"restored without the package's runtime");

    fprintf(stderr,"-- start 5: damaged fallback copy\n");
    put(HW_INSTALL_DATA,FB "syswow64/concrt140.dll",ms_concrt,n);
    CHECK(!unlink(HW_INSTALL_DATA "/" W32 "concrt140.dll"),"simulated uninstall");
    CHECK(hw_install_vcrt_repair()==1,"a copy that does not match list.txt is refused");
    CHECK(!exists(HW_INSTALL_DATA,W32 "concrt140.dll")&&!exists(HW_INSTALL_DATA,W32 "concrt140.dll.pwinstall"),
          "nothing written for a damaged copy");

    fprintf(stderr,"-- start 6: a good copy again, then nothing missing\n");
    put(HW_INSTALL_DATA,FB "syswow64/concrt140.dll",concrt,n);
    CHECK(hw_install_vcrt_repair()==0,"repaired");
    CHECK(same(HW_INSTALL_DATA,W32 "concrt140.dll",concrt,n),"concrt140 back");
    CHECK(hw_install_vcrt_repair()==0,"nothing to do");

    if(failures){fprintf(stderr,"vcrt fallback host check: %d failure(s)\n",failures);return 1;}
    printf("vcrt fallback host check: ok\n");
    return 0;
}
