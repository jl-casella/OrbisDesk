/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* J001 probe: what the app sees under /mnt (USB disks at /mnt/usb0..7) from its sandbox, and
 * whether GoldHEN's SDK jailbreak changes that. No Wine. Built by tools/build-mnt-probe.py.
 * W179/W181: from OrbisDesk, /mnt does not exist (PWUSB path=/mnt stat=-1 errno=2).
 * Steps, each written with its result and errno to MNT_LOG (and sceKernelDebugOutText):
 *   1. GoldHEN SDK version (sys_sdk_cmd 0);
 *   2. list the paths below from the sandbox;
 *   3. jailbreak (sys_sdk_cmd 2), uid before and after;
 *   4. list again, and read the first bytes of the first file on each disk found;
 *   5. unjailbreak (sys_sdk_cmd 3) with the backup from step 3, uid after;
 *   6. list /mnt once more (it should be gone again).
 * Read only: nothing is written outside MNT_LOG. A step that fails is written as failed; the
 * next steps still run, except that 4 and 5 need step 3. */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <orbis/libkernel.h>

#define MNT_LOG "/data/orbisdesk/probe-mnt.txt"

/* GoldHEN Plugins SDK (MIT, github.com/GoldHEN/GoldHEN_Plugins_SDK, include/GoldHEN.h and
 * source/GoldHEN.c): sys_sdk_cmd(cmd, data) is syscall(500, cmd, data), made through the
 * indirect syscall 0 as source/Syscall.c does. */
struct jailbreak_backup
{
    uint32_t cr_uid;
    uint32_t cr_ruid;
    uint32_t cr_rgid;
    uint32_t cr_groups;
    uint64_t cr_paid;
    uint64_t cr_caps[2];
    void *cr_prison;
    void *fd_cdir;
    void *fd_jdir;
    void *fd_rdir;
};
enum {GOLDHEN_SDK_CMD_VERSION=0,GOLDHEN_SDK_CMD_JAILBREAK=2,GOLDHEN_SDK_CMD_UNJAILBREAK=3};

/* returns the kernel's rax; *error is its errno when the carry flag is set, else 0 */
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

static int log_fd=-1;

static void note(const char *format,...)
{
    char line[512];
    va_list ap;
    int n;

    va_start(ap,format);n=vsnprintf(line,sizeof(line)-1,format,ap);va_end(ap);
    if(n<0) return;
    if(n>(int)sizeof(line)-2) n=sizeof(line)-2;
    line[n++]='\n';line[n]=0;
    sceKernelDebugOutText(0,line);
    if(log_fd>=0) {write(log_fd,line,(size_t)n);fsync(log_fd);}
}

static const char *const paths[]={"/","/mnt","/mnt/usb0","/mnt/usb1","/mnt/usb2","/mnt/usb3",
                                  "/mnt/usb4","/mnt/usb5","/mnt/usb6","/mnt/usb7","/mnt/ext0","/user","/data"};
enum {PATH_COUNT=sizeof(paths)/sizeof(paths[0])};

/* one line per path: stat, then up to 12 entry names. Directories are read with
 * sceKernelGetdents as platform/ps4/pw_wine_fs.c reads them (libc's getdents is not imported by
 * any running eboot); a record is {u32 inode, u16 length, u8 type, u8 namelen, name}. */
static void list_path(const char *stage,const char *path,int read_first)
{
    struct stat st;
    char names[300]="";
    char first[64]="";
    size_t used=0;
    int st_rc,st_errno,dir_errno=0,count=0,fd,got=0;

    errno=0;st_rc=stat(path,&st);st_errno=st_rc?errno:0;
    errno=0;fd=open(path,O_RDONLY|O_DIRECTORY);
    if(fd<0) dir_errno=errno;
    else
    {
        static unsigned char buffer[8192];

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
                if(!(record[0]|record[1]|record[2]|record[3])) continue;  /* unused record */
                if(!strcmp(name,".") || !strcmp(name,"..")) continue;
                if(count<12 && used+namelen+2<sizeof(names))
                    used+=(size_t)snprintf(names+used,sizeof(names)-used,"%s%s",count?",":"",name);
                if(!first[0] && type==8 /* DT_REG */) snprintf(first,sizeof(first),"%s",name);
                count++;
            }
            if(got<0) break;
        }
        if(got<0) dir_errno=got;  /* an Orbis error code (0x8002xxxx), or -1 for a bad record */
        close(fd);
    }
    note("PWMNT %s path=%s stat=%d errno=%d mode=%o dir=%d error=%#x entries=%d names=%s",stage,path,
         st_rc,st_errno,st_rc?0:(unsigned)st.st_mode,fd>=0,(unsigned)dir_errno,fd>=0?count:-1,used?names:"-");
    if(read_first && first[0])
    {
        char file[200];
        unsigned char bytes[16];
        int fd,got=-1,read_errno=0,open_errno=0;

        snprintf(file,sizeof(file),"%s/%s",path,first);
        errno=0;fd=open(file,O_RDONLY);
        if(fd<0) open_errno=errno;
        else {errno=0;got=(int)read(fd,bytes,sizeof(bytes));if(got<0) read_errno=errno;close(fd);}
        note("PWMNT %s read=%s open=%d errno=%d read=%d errno=%d first=%02x%02x%02x%02x",stage,file,fd>=0,
             open_errno,got,read_errno,got>0?bytes[0]:0,got>1?bytes[1]:0,got>2?bytes[2]:0,got>3?bytes[3]:0);
    }
}

int main(void)
{
    struct jailbreak_backup backup;
    struct sigaction ignore;
    long version,rc;
    int error,i,jailbroken=0;

    mkdir("/data/orbisdesk",0777);
    log_fd=open(MNT_LOG,O_WRONLY|O_CREAT|O_TRUNC,0666);
    note("PWMNT J001 start log=%s log_fd=%d pid=%d uid=%d",MNT_LOG,log_fd,getpid(),getuid());

    /* without GoldHEN, syscall 500 is not there: SIGSYS would end the probe; ignored, it fails
     * with ENOSYS and the steps that need it are written as failed */
    memset(&ignore,0,sizeof(ignore));ignore.sa_handler=SIG_IGN;
    note("PWMNT sigsys_ignore rc=%d errno=%d",sigaction(SIGSYS,&ignore,NULL),errno);

    version=sdk_cmd(GOLDHEN_SDK_CMD_VERSION,NULL,&error);
    note("PWMNT goldhen_version rc=%ld (%#lx) errno=%d",version,(unsigned long)version,error);

    for(i=0;i<PATH_COUNT;i++) list_path("sandbox",paths[i],0);

    memset(&backup,0,sizeof(backup));
    rc=sdk_cmd(GOLDHEN_SDK_CMD_JAILBREAK,&backup,&error);
    jailbroken=!rc && !error;
    note("PWMNT jailbreak rc=%ld errno=%d uid=%d backup_uid=%u prison=%p rdir=%p",rc,error,getuid(),
         backup.cr_uid,backup.cr_prison,backup.fd_rdir);

    if(jailbroken)
    {
        for(i=0;i<PATH_COUNT;i++) list_path("jailbroken",paths[i],!strncmp(paths[i],"/mnt/usb",8));
        rc=sdk_cmd(GOLDHEN_SDK_CMD_UNJAILBREAK,&backup,&error);
        note("PWMNT unjailbreak rc=%ld errno=%d uid=%d",rc,error,getuid());
        list_path("after",paths[1],0);
    }
    else note("PWMNT jailbroken listing skipped: the jailbreak failed");

    note("PWMNT J001 end");
    if(log_fd>=0) close(log_fd);
    sceKernelUsleep(2000000);
    return 0;
}
