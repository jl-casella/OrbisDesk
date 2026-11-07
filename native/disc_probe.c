/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* J002 probe: what the app sees of the optical drive, with a disc inserted. No Wine. Built by
 * tools/build-disc-probe.py as the probe title ORBB00001 (it replaces J001, native/mnt_probe.c).
 * W180: from the sandbox, /mnt/disc gives ENOENT; J001/W228: GoldHEN's SDK jailbreak shows /mnt.
 * The same checks run in three stages, each line with its result and errno to DISC_LOG:
 *   sandbox  the app as it starts (OrbisDesk in NORMAL);
 *   root0    after the jailbreak (sys_sdk_cmd 2), uid 0;
 *   root1    jailbroken and back to the app's own uid, as OrbisDesk's ROOT runs Wine
 *            (native/wine_hardware.c, W228); then unjailbreak (sys_sdk_cmd 3).
 * Checks: /mnt/disc (stat, the kernel's fstatfs, listing), the kind of disc from its folders,
 * the first sectors of a DVD-Video title VOB (read error, or scrambled packs = CSS), /dev (the
 * whole listing once per stage) and, for each node that may be the drive, open, sector size,
 * media size and raw 2048-byte reads of sectors 16-18 (ISO9660 / UDF volume recognition) and
 * 256 (UDF anchor). Read only: nothing is written outside DISC_LOG. Nothing is guessed: a value
 * the system did not give is written as -, with the errno of the call that failed. */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>

#define DISC_LOG "/data/orbisdesk/probe-disc.txt"
#define DISC "/mnt/disc"
enum {SECTOR=2048,MAX_NODES=8};

/* GoldHEN Plugins SDK (MIT, github.com/GoldHEN/GoldHEN_Plugins_SDK), as in native/mnt_probe.c */
struct jailbreak_backup
{
    uint32_t cr_uid,cr_ruid,cr_rgid,cr_groups;
    uint64_t cr_paid,cr_caps[2];
    void *cr_prison,*fd_cdir,*fd_jdir,*fd_rdir;
};
static long sdk_cmd(uint64_t cmd,void *data,int *error)
{
    long ret;
    unsigned char failed;

    __asm__ volatile("syscall\n\tsetc %1"
                     :"=a"(ret),"=q"(failed)
                     :"a"(0L),"D"(500L),"S"(cmd),"d"(data)
                     :"rcx","r8","r9","r10","r11","memory","cc");
    *error=failed?(int)ret:0;
    return failed?-1:ret;
}

/* the kernel's struct statfs is FreeBSD 9's (W180, W218): f_flags 0x08, f_bsize 0x10,
 * f_blocks 0x20, f_fstypename 0x118 (16), f_mntfromname 0x128 (88), f_mntonname 0x180 (88) */
extern int kernel_fstatfs(int,void *) __asm__("_fstatfs");
/* FreeBSD <sys/disk.h>: DIOCGSECTORSIZE _IOR('d',128,u_int), DIOCGMEDIASIZE _IOR('d',129,off_t) */
#define DIOCGSECTORSIZE 0x40046480UL
#define DIOCGMEDIASIZE 0x40086481UL

static int log_fd=-1;
static void note(const char *format,...)
{
    char line[640];
    va_list ap;
    int n;

    va_start(ap,format);n=vsnprintf(line,sizeof(line)-1,format,ap);va_end(ap);
    if(n<0) return;
    if(n>(int)sizeof(line)-2) n=sizeof(line)-2;
    line[n++]='\n';line[n]=0;
    sceKernelDebugOutText(0,line);
    if(log_fd>=0) {write(log_fd,line,(size_t)n);fsync(log_fd);}
}

static unsigned char sector[4*SECTOR] __attribute__((aligned(4096)));

/* Calls back for each entry of a directory, read with sceKernelGetdents as native/mnt_probe.c
 * does. Returns the entry count, or -1 with *error (errno of open, or the Orbis error code). */
typedef void (*entry_fn)(const char *name,unsigned type,void *context);
static int each_entry(const char *path,entry_fn fn,void *context,int *error)
{
    static unsigned char buffer[8192];
    int fd,got,count=0;

    *error=0;errno=0;fd=open(path,O_RDONLY|O_DIRECTORY);
    if(fd<0) {*error=errno;return -1;}
    while((got=sceKernelGetdents(fd,(char *)buffer,sizeof(buffer)))>0)
    {
        int position=0;

        while(position+8<=got)
        {
            const unsigned char *record=buffer+position;
            unsigned length=record[4]|record[5]<<8,type=record[6],namelen=record[7];
            char name[256];

            if(length<8 || position+(int)length>got || 8+namelen>length) {got=-1;break;}
            memcpy(name,record+8,namelen);name[namelen]=0;
            position+=(int)length;
            if(!(record[0]|record[1]|record[2]|record[3])) continue;
            if(!strcmp(name,".") || !strcmp(name,"..")) continue;
            fn(name,type,context);count++;
        }
        if(got<0) break;
    }
    close(fd);
    if(got<0) {*error=got;return -1;}
    return count;
}

/* names joined with commas; written as one or more lines when full */
struct name_list {const char *stage,*label;char text[440];size_t used;int part;};
static void flush_names(struct name_list *list)
{
    if(!list->used) return;
    note("PWDISC %s %s part=%d names=%s",list->stage,list->label,list->part++,list->text);
    list->used=0;list->text[0]=0;
}
static void add_name(const char *name,unsigned type,void *context)
{
    struct name_list *list=context;
    size_t n=strlen(name);

    (void)type;
    if(list->used+n+2>=sizeof(list->text)) flush_names(list);
    list->used+=(size_t)snprintf(list->text+list->used,sizeof(list->text)-list->used,"%s%s",list->used?",":"",name);
}
static void list_all(const char *stage,const char *label,const char *path)
{
    struct name_list list={stage,label,"",0,0};
    int error,count=each_entry(path,add_name,&list,&error);

    flush_names(&list);
    note("PWDISC %s %s path=%s entries=%d error=%#x",stage,label,path,count,(unsigned)error);
}

/* stat, fstatfs and a listing of one path; the type and source of the file system are kept */
struct fs_info {int ok;char type[17],from[89];};
static void fs_line(const char *stage,const char *path,struct fs_info *out)
{
    unsigned char fs[0x400];
    struct stat st;
    int rc,stat_errno,fd,fs_rc=-1,fs_errno=0;
    uint64_t flags=0,bsize=0,blocks=0;
    char type[17]="-",from[89]="-",on[89]="-";

    errno=0;rc=stat(path,&st);stat_errno=rc?errno:0;
    memset(fs,0,sizeof(fs));
    errno=0;fd=rc?-1:open(path,O_RDONLY);
    if(!rc && fd<0) fs_errno=errno;
    if(fd>=0) {errno=0;fs_rc=kernel_fstatfs(fd,fs);if(fs_rc) fs_errno=errno;close(fd);}
    if(!fs_rc)
    {
        memcpy(&flags,fs+0x08,8);memcpy(&bsize,fs+0x10,8);memcpy(&blocks,fs+0x20,8);
        memcpy(type,fs+0x118,16);type[16]=0;memcpy(from,fs+0x128,88);from[88]=0;memcpy(on,fs+0x180,88);on[88]=0;
    }
    note("PWDISC %s fs path=%s stat=%d errno=%d mode=%o dev=%#llx statfs=%d errno=%d type=%s rdonly=%d bsize=%llu blocks=%llu from=%s on=%s",
         stage,path,rc,stat_errno,rc?0:(unsigned)st.st_mode,rc?0ULL:(unsigned long long)st.st_dev,fs_rc,fs_errno,
         type,fs_rc?-1:(int)(flags&1),(unsigned long long)bsize,(unsigned long long)blocks,from,on);
    if(out) {out->ok=!fs_rc;strcpy(out->type,type);strcpy(out->from,from);}
}

/* the kind of disc from the folders at its root; "unknown" when none of them is there */
struct root_marks {int video_ts,audio_ts,bdmv,certificate,sce_sys,app,entries;char video_ts_name[16];};
static void mark_root(const char *name,unsigned type,void *context)
{
    struct root_marks *marks=context;

    (void)type;marks->entries++;
    if(!strcasecmp(name,"VIDEO_TS")) {marks->video_ts=1;snprintf(marks->video_ts_name,sizeof(marks->video_ts_name),"%s",name);}
    else if(!strcasecmp(name,"AUDIO_TS")) marks->audio_ts=1;
    else if(!strcasecmp(name,"BDMV")) marks->bdmv=1;
    else if(!strcasecmp(name,"CERTIFICATE")) marks->certificate=1;
    else if(!strcasecmp(name,"sce_sys")) marks->sce_sys=1;
    else if(!strncasecmp(name,"app",3)) marks->app=1;
}

/* the first title VOB (VTS_nn_1.VOB, the lowest nn) */
struct vob_pick {char name[32];};
static void pick_vob(const char *name,unsigned type,void *context)
{
    struct vob_pick *pick=context;
    size_t n=strlen(name);

    (void)type;
    if(n!=12 || strncasecmp(name,"VTS_",4) || strcasecmp(name+6,"_1.VOB")) return;
    if(!pick->name[0] || strcasecmp(name,pick->name)<0) snprintf(pick->name,sizeof(pick->name),"%s",name);
}

/* DVD-Video: the IFO signature, and 64 sectors of the first title VOB from 1 MiB in. A pack
 * starts 00 00 01 BA; its first PES header follows at 0x0e, and PES_scrambling_control is
 * byte 0x14 & 0x30 (CSS sets it). Navigation packs (stream BB/BF) are never scrambled. */
static void dvd_video(const char *stage,const char *video_ts)
{
    char path[160];
    struct vob_pick pick={""};
    int fd,got,error,count,read_errno=0,packs=0,scrambled=0,clear=0,other=0;
    long long size=-1;
    struct stat st;

    snprintf(path,sizeof(path),"%s/%s/VIDEO_TS.IFO",DISC,video_ts);
    errno=0;fd=open(path,O_RDONLY);
    if(fd<0) note("PWDISC %s ifo path=%s open=0 errno=%d",stage,path,errno);
    else
    {
        errno=0;got=(int)pread(fd,sector,SECTOR,0);
        note("PWDISC %s ifo path=%s read=%d errno=%d id=%.12s",stage,path,got,got<0?errno:0,got>=12?(char *)sector:"-");
        close(fd);
    }
    snprintf(path,sizeof(path),"%s/%s",DISC,video_ts);
    count=each_entry(path,pick_vob,&pick,&error);
    if(!pick.name[0]) {note("PWDISC %s vob none entries=%d error=%#x",stage,count,(unsigned)error);return;}
    snprintf(path,sizeof(path),"%s/%s/%s",DISC,video_ts,pick.name);
    errno=0;fd=open(path,O_RDONLY);
    if(fd<0) {note("PWDISC %s vob path=%s open=0 errno=%d",stage,path,errno);return;}
    if(!fstat(fd,&st)) size=(long long)st.st_size;
    for(int i=0;i<64;i+=4)
    {
        off_t at=(size>(1<<20)+64*SECTOR?(1<<20):0)+(off_t)i*SECTOR;

        errno=0;got=(int)pread(fd,sector,4*SECTOR,at);
        if(got<0) {read_errno=errno;break;}
        for(int s=0;s+SECTOR<=got;s+=SECTOR)
        {
            const unsigned char *p=sector+s;

            if(p[0]||p[1]||p[2]!=1||p[3]!=0xba) {other++;continue;}
            packs++;
            if(p[0x0e]||p[0x0f]||p[0x10]!=1||p[0x11]==0xbb||p[0x11]==0xbf) {clear++;continue;}
            if(p[0x14]&0x30) scrambled++;
            else clear++;
        }
        if(got<4*SECTOR) break;
    }
    close(fd);
    note("PWDISC %s vob path=%s size=%lld read_errno=%d packs=%d scrambled=%d clear=%d other=%d css=%s",stage,path,size,
         read_errno,packs,scrambled,clear,other,read_errno?"unreadable":!packs?"-":scrambled?"yes":"no");
}

/* the nodes of /dev that may be the drive: by name, and the source of /mnt/disc's file system */
struct node_pick {char name[MAX_NODES][64];int count;};
static void add_node(struct node_pick *pick,const char *name)
{
    for(int i=0;i<pick->count;i++) if(!strcmp(pick->name[i],name)) return;
    if(pick->count<MAX_NODES) snprintf(pick->name[pick->count++],64,"%s",name);
}
static void pick_node(const char *name,unsigned type,void *context)
{
    static const char *const prefixes[]={"cd","acd","bd","dvd","disc","odd","sr","pass"};

    (void)type;
    for(unsigned i=0;i<sizeof(prefixes)/sizeof(prefixes[0]);i++)
        if(!strncmp(name,prefixes[i],strlen(prefixes[i]))) {add_node(context,name);return;}
}

/* one node: stat, open, sector and media size, the ids of sectors 16-18 and the tag of 256 */
static void raw_node(const char *stage,const char *name)
{
    char path[80],ids[3][6];
    struct stat st;
    unsigned sector_size=0;
    long long media=0;
    int rc,stat_errno,fd,open_errno=0,ss_rc,ss_errno,ms_rc,ms_errno,got16,errno16=0,got256,errno256=0;
    unsigned tag=0;

    snprintf(path,sizeof(path),"/dev/%s",name);
    errno=0;rc=stat(path,&st);stat_errno=rc?errno:0;
    errno=0;fd=open(path,O_RDONLY);
    if(fd<0)
    {
        open_errno=errno;
        note("PWDISC %s raw path=%s stat=%d errno=%d mode=%o rdev=%#llx open=0 errno=%d",stage,path,rc,stat_errno,
             rc?0:(unsigned)st.st_mode,rc?0ULL:(unsigned long long)st.st_rdev,open_errno);
        return;
    }
    errno=0;ss_rc=ioctl(fd,DIOCGSECTORSIZE,&sector_size);ss_errno=ss_rc?errno:0;
    errno=0;ms_rc=ioctl(fd,DIOCGMEDIASIZE,&media);ms_errno=ms_rc?errno:0;
    memset(sector,0,3*SECTOR);
    errno=0;got16=(int)pread(fd,sector,3*SECTOR,16*SECTOR);if(got16<0) errno16=errno;
    for(int i=0;i<3;i++)
    {
        const unsigned char *p=sector+i*SECTOR+1;

        if(got16>=(i+1)*SECTOR) {for(int c=0;c<5;c++) ids[i][c]=p[c]>=0x20&&p[c]<0x7f?(char)p[c]:'.';ids[i][5]=0;}
        else strcpy(ids[i],"-");
    }
    errno=0;got256=(int)pread(fd,sector,SECTOR,256*SECTOR);
    if(got256<0) errno256=errno;
    else if(got256>=2) tag=sector[0]|sector[1]<<8;
    close(fd);
    note("PWDISC %s raw path=%s stat=%d mode=%o rdev=%#llx open=1 sector_size=%u ioctl=%d errno=%d media=%lld ioctl=%d errno=%d "
         "read16=%d errno=%d id16=%s id17=%s id18=%s read256=%d errno=%d tag256=%u",stage,path,rc,rc?0:(unsigned)st.st_mode,
         rc?0ULL:(unsigned long long)st.st_rdev,sector_size,ss_rc,ss_errno,media,ms_rc,ms_errno,got16,errno16,ids[0],ids[1],ids[2],
         got256,errno256,tag);
}

static void stage_checks(const char *stage)
{
    struct fs_info fs={0,"-","-"};
    struct root_marks marks;
    struct node_pick nodes;
    int error,count;
    const char *kind;

    note("PWDISC %s begin uid=%d euid=%d",stage,getuid(),geteuid());
    fs_line(stage,"/mnt",NULL);
    fs_line(stage,DISC,&fs);
    memset(&marks,0,sizeof(marks));
    count=each_entry(DISC,mark_root,&marks,&error);
    if(count>=0) list_all(stage,"disc_root",DISC);
    kind=count<0?"none":marks.video_ts?"dvd-video":marks.bdmv?"bd-video":marks.sce_sys||marks.app?"ps4-game":
         count==0?"empty":"data";
    note("PWDISC %s kind=%s entries=%d error=%#x video_ts=%d audio_ts=%d bdmv=%d certificate=%d sce_sys=%d app=%d basis=listing",
         stage,kind,count,(unsigned)error,marks.video_ts,marks.audio_ts,marks.bdmv,marks.certificate,marks.sce_sys,marks.app);
    if(marks.video_ts)
    {
        char path[80];

        snprintf(path,sizeof(path),"%s/%s",DISC,marks.video_ts_name);
        list_all(stage,"video_ts",path);
        dvd_video(stage,marks.video_ts_name);
    }
    list_all(stage,"mnt","/mnt");
    list_all(stage,"dev","/dev");
    memset(&nodes,0,sizeof(nodes));
    each_entry("/dev",pick_node,&nodes,&error);
    if(fs.ok && !strncmp(fs.from,"/dev/",5)) add_node(&nodes,fs.from+5);
    note("PWDISC %s raw candidates=%d",stage,nodes.count);
    for(int i=0;i<nodes.count;i++) raw_node(stage,nodes.name[i]);
    note("PWDISC %s end",stage);
}

int main(void)
{
    struct jailbreak_backup backup;
    struct sigaction ignore;
    long version,rc;
    int error;

    mkdir("/data/orbisdesk",0777);
    log_fd=open(DISC_LOG,O_WRONLY|O_CREAT|O_TRUNC,0666);
    note("PWDISC J002 start log=%s log_fd=%d pid=%d uid=%d",DISC_LOG,log_fd,getpid(),getuid());

    /* without GoldHEN, syscall 500 raises SIGSYS; ignored, it fails with ENOSYS */
    memset(&ignore,0,sizeof(ignore));ignore.sa_handler=SIG_IGN;
    note("PWDISC sigsys_ignore rc=%d errno=%d",sigaction(SIGSYS,&ignore,NULL),errno);
    version=sdk_cmd(0,NULL,&error);
    note("PWDISC goldhen_version rc=%ld (%#lx) errno=%d",version,(unsigned long)version,error);

    stage_checks("sandbox");

    memset(&backup,0,sizeof(backup));
    rc=sdk_cmd(2,&backup,&error);
    note("PWDISC jailbreak rc=%ld errno=%d uid=%d backup_uid=%u",rc,error,getuid(),backup.cr_uid);
    if(rc || error) {note("PWDISC root stages skipped: the jailbreak failed");goto end;}
    stage_checks("root0");

    errno=0;rc=setuid((uid_t)backup.cr_uid);
    note("PWDISC setuid=%u rc=%ld errno=%d uid=%d",backup.cr_uid,rc,rc?errno:0,getuid());
    if(!rc) stage_checks("root1");
    else note("PWDISC root1 skipped: setuid failed");

    rc=sdk_cmd(3,&backup,&error);
    note("PWDISC unjailbreak rc=%ld errno=%d uid=%d",rc,error,getuid());
    fs_line("after",DISC,NULL);

end:
    note("PWDISC J002 end");
    if(log_fd>=0) close(log_fd);
    sceKernelUsleep(2000000);
    return 0;
}
