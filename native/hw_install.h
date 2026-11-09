/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* alpha-1: the first-run installer. OrbisDesk.pkg carries the runtime as /app0/runtime (wine/, wine-prefix/,
 * wine-home/, console32.exe) and its list, /app0/runtime/install.txt (tools/build-wine-hardware.py). On the
 * first start of each build the launcher brings /data up to that list with the rules tools/upload-hardware.py
 * applies over FTP, before Wine starts:
 *   - a file is copied when it is missing or differs (size, then SHA-256); a copy goes to <path>.pwinstall,
 *     is checked against the list's SHA-256 while it is written, then renamed over the old file;
 *   - user.reg is merged, never copied: the console keeps its blocks under the console-owned keys
 *     (tools/console_state.py), and a build-only block the user deleted stays deleted (the ledger
 *     /data/orbisdesk/user-reg-delivered.json, shared with the uploader);
 *   - files earlier builds shipped and this one does not (obsolete) are deleted;
 *   - the files of the build PC's profile folder (C:\users\<host>, shipped by builds before alpha-1, whose
 *     registry pointed Documents and the rest there) move to C:\users\orbis without replacing anything;
 *   - nothing outside the list is touched: documents, saves, Steam games and /data/orbisdesk stay.
 * Only when every step succeeded is the list copied to /data/orbisdesk/runtime-installed.txt; the next start
 * of the same build does nothing, and a failed install runs again. A package without install.txt
 * (--runtime-outside-package) leaves /data as the uploader made it.
 * Included by native/wine_hardware.c after its note(), read_whole() and loading screen. */
#include <ctype.h>
#include <dirent.h>
#include <strings.h>
#include <sys/statvfs.h>

#define HW_INSTALL_ROOT "/app0/runtime"
#define HW_INSTALL_LIST HW_INSTALL_ROOT "/install.txt"
#define HW_INSTALL_RECORD "/data/orbisdesk/runtime-installed.txt"
#define HW_INSTALL_LEDGER "/data/orbisdesk/user-reg-delivered.json"
#define HW_INSTALL_USER_REG "wine-prefix/user.reg"

/* ---- SHA-256 (FIPS 180-4) ---- */
typedef struct {uint32_t h[8];uint64_t bytes;uint8_t block[64];size_t used;} hw_sha256;
static const uint32_t hw_sha_k[64]={
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define HW_ROR(x,n) (((x)>>(n))|((x)<<(32-(n))))
static void hw_sha_compress(hw_sha256 *s,const uint8_t *p)
{
    uint32_t w[64],a,b,c,d,e,f,g,h;
    for(int i=0;i<16;i++)w[i]=(uint32_t)p[4*i]<<24|(uint32_t)p[4*i+1]<<16|(uint32_t)p[4*i+2]<<8|p[4*i+3];
    for(int i=16;i<64;i++){
        uint32_t s0=HW_ROR(w[i-15],7)^HW_ROR(w[i-15],18)^(w[i-15]>>3),s1=HW_ROR(w[i-2],17)^HW_ROR(w[i-2],19)^(w[i-2]>>10);
        w[i]=w[i-16]+s0+w[i-7]+s1;
    }
    a=s->h[0];b=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
    for(int i=0;i<64;i++){
        uint32_t t1=h+(HW_ROR(e,6)^HW_ROR(e,11)^HW_ROR(e,25))+((e&f)^(~e&g))+hw_sha_k[i]+w[i];
        uint32_t t2=(HW_ROR(a,2)^HW_ROR(a,13)^HW_ROR(a,22))+((a&b)^(a&c)^(b&c));
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void hw_sha_init(hw_sha256 *s)
{
    static const uint32_t iv[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    memcpy(s->h,iv,sizeof(iv));s->bytes=0;s->used=0;
}
static void hw_sha_update(hw_sha256 *s,const void *data,size_t n)
{
    const uint8_t *p=data;s->bytes+=n;
    while(n){
        size_t take=64-s->used;if(take>n)take=n;
        memcpy(s->block+s->used,p,take);s->used+=take;p+=take;n-=take;
        if(s->used==64){hw_sha_compress(s,s->block);s->used=0;}
    }
}
static void hw_sha_hex(hw_sha256 *s,char out[65])
{
    uint64_t bits=s->bytes*8;uint8_t pad=0x80,zero=0,len[8];
    hw_sha_update(s,&pad,1);
    while(s->used!=56)hw_sha_update(s,&zero,1);
    for(int i=0;i<8;i++)len[i]=(uint8_t)(bits>>(56-8*i));
    hw_sha_update(s,len,8);
    for(int i=0;i<8;i++)snprintf(out+8*i,9,"%08x",s->h[i]);
}

/* ---- the list ---- */
enum {HW_INSTALL_MAX_ROOTS=16};
struct hw_install_file {const char *sha,*path;uint64_t bytes;int action;};
struct hw_install_list {
    char *text;size_t size;const char *build,*host;uint64_t total;
    const char *writable[HW_INSTALL_MAX_ROOTS],*owned[HW_INSTALL_MAX_ROOTS],*reset[HW_INSTALL_MAX_ROOTS];
    unsigned writables,owneds,resets,dirs,files,obsoletes;
    const char **dir,**obsolete;struct hw_install_file *file;
};
static void hw_install_free(struct hw_install_list *l){free(l->text);free(l->dir);free(l->obsolete);free(l->file);memset(l,0,sizeof(*l));}
/* "ORBISDESK-INSTALL 1" then one record per line: B build, H host profile, T total bytes, W writable root,
 * K console-owned key, R reset key, D directory, F sha256 bytes path, O obsolete path (paths last: spaces) */
static int hw_install_parse(struct hw_install_list *l,char *text,size_t size)
{
    memset(l,0,sizeof(*l));l->text=text;l->size=size;
    unsigned lines=0;for(size_t i=0;i<size;i++)if(text[i]=='\n')lines++;
    l->dir=calloc(lines+1,sizeof(*l->dir));l->obsolete=calloc(lines+1,sizeof(*l->obsolete));l->file=calloc(lines+1,sizeof(*l->file));
    if(!l->dir||!l->obsolete||!l->file)return -1;
    if(size<20||memcmp(text,"ORBISDESK-INSTALL 1\n",20))return -1;
    for(char *line=text+20;line<text+size&&*line;){
        char *end=memchr(line,'\n',(size_t)(text+size-line));
        if(!end)return -1;
        *end=0;
        char kind=line[0];const char *value=line+2;
        if(line[1]!=' ')return -1;
        switch(kind){
        case 'B':l->build=value;break;
        case 'H':l->host=value;break;
        case 'T':l->total=strtoull(value,NULL,10);break;
        case 'W':if(l->writables<HW_INSTALL_MAX_ROOTS)l->writable[l->writables++]=value;break;
        case 'K':if(l->owneds<HW_INSTALL_MAX_ROOTS)l->owned[l->owneds++]=value;break;
        case 'R':if(l->resets<HW_INSTALL_MAX_ROOTS)l->reset[l->resets++]=value;break;
        case 'D':l->dir[l->dirs++]=value;break;
        case 'O':l->obsolete[l->obsoletes++]=value;break;
        case 'F':{
            char *size_end;
            if(strlen(value)<67||value[64]!=' ')return -1;
            line[2+64]=0;
            uint64_t bytes=strtoull(value+65,&size_end,10);
            if(*size_end!=' ')return -1;
            l->file[l->files++]=(struct hw_install_file){value,size_end+1,bytes,0};
            break;}
        default:return -1;
        }
        line=end+1;
    }
    return l->build&&l->files?0:-1;
}

/* ---- file helpers ---- */
static int hw_install_writable(const struct hw_install_list *l,const char *path)
{
    for(unsigned i=0;i<l->writables;i++){
        size_t n=strlen(l->writable[i]);
        if(!strncmp(path,l->writable[i],n)&&(path[n]=='/'||!path[n]))return 1;
    }
    return 0;
}
static int hw_install_mkdirs(const char *path,mode_t mode)
{
    char buffer[PATH_MAX];
    if(snprintf(buffer,sizeof(buffer),"%s",path)>=(int)sizeof(buffer))return -1;
    for(char *p=buffer+1;;p++){
        if(*p=='/'||!*p){
            char c=*p;*p=0;
            if(mkdir(buffer,mode)&&errno!=EEXIST)return -1;
            if(!c)break;
            *p=c;
        }
    }
    return 0;
}
static int hw_install_hash(const char *path,char out[65])
{
    static uint8_t buffer[1<<20];
    int fd=open(path,O_RDONLY);if(fd<0)return -1;
    hw_sha256 s;hw_sha_init(&s);
    for(;;){ssize_t n=read(fd,buffer,sizeof(buffer));if(n<0){close(fd);return -1;}if(!n)break;hw_sha_update(&s,buffer,(size_t)n);}
    close(fd);hw_sha_hex(&s,out);return 0;
}
/* write data (a buffer) or the file at source to target through <target>.pwinstall, checking sha */
static int hw_install_write(const char *source,const void *data,size_t size,const char *target,const char *sha,mode_t mode)
{
    static uint8_t buffer[1<<20];
    char temp[PATH_MAX];
    if(snprintf(temp,sizeof(temp),"%s.pwinstall",target)>=(int)sizeof(temp)){errno=ENAMETOOLONG;return -1;}
    int in=source?open(source,O_RDONLY):-1;
    if(source&&in<0)return -1;
    int out=open(temp,O_CREAT|O_TRUNC|O_WRONLY,mode);
    if(out<0){int e=errno;if(in>=0)close(in);errno=e;return -1;}
    hw_sha256 s;hw_sha_init(&s);int failed=0;
    for(size_t done=0;!failed;){
        const uint8_t *chunk;ssize_t n;
        if(source){n=read(in,buffer,sizeof(buffer));chunk=buffer;}
        else{n=(ssize_t)(size-done>sizeof(buffer)?sizeof(buffer):size-done);chunk=(const uint8_t *)data+done;}
        if(n<0){failed=1;break;}
        if(!n)break;
        hw_sha_update(&s,chunk,(size_t)n);done+=(size_t)n;
        for(ssize_t off=0;off<n;){ssize_t w=write(out,chunk+off,(size_t)(n-off));if(w<=0){failed=1;break;}off+=w;}
    }
    int e=errno;
    if(in>=0)close(in);
    if(!failed&&fsync(out))failed=1,e=errno;
    if(close(out)&&!failed)failed=1,e=errno;
    if(!failed&&sha){char got[65];hw_sha_hex(&s,got);if(strcmp(got,sha))failed=1,e=EILSEQ;}
    if(!failed){chmod(temp,mode);if(sceKernelRename(temp,target))failed=1,e=errno?errno:EIO;}
    if(failed){unlink(temp);errno=e;return -1;}
    chmod(target,mode);
    return 0;
}

/* ---- user.reg (tools/upload-hardware.py merge_user_reg) ---- */
struct hw_reg_block {const char *key;size_t key_len;const char *start;size_t len;};
/* a key line: [name] or [name] <digits> */
static int hw_reg_key_line(const char *line,size_t len,const char **key,size_t *key_len)
{
    if(!len||line[0]!='[')return 0;
    size_t close_at=len;
    while(close_at>0&&line[close_at-1]!=']')close_at--;
    if(!close_at)return 0;
    size_t i=close_at;
    if(i<len){if(line[i]!=' '||i+1==len)return 0;for(i++;i<len;i++)if(line[i]<'0'||line[i]>'9')return 0;}
    *key=line+1;*key_len=close_at-2;return 1;
}
/* head length and blocks; blocks run to the next key line (each ends with its newline) */
static struct hw_reg_block *hw_reg_blocks(const char *text,size_t size,size_t *head,unsigned *count)
{
    unsigned lines=1;for(size_t i=0;i<size;i++)if(text[i]=='\n')lines++;
    struct hw_reg_block *b=calloc(lines,sizeof(*b));if(!b)return NULL;
    *count=0;*head=size;
    for(size_t pos=0;pos<size;){
        const char *nl=memchr(text+pos,'\n',size-pos);size_t len=nl?(size_t)(nl-(text+pos)):size-pos;
        const char *key;size_t key_len;
        if(hw_reg_key_line(text+pos,len,&key,&key_len)){
            if(!*count)*head=pos;
            if(*count)b[*count-1].len=(size_t)(text+pos-b[*count-1].start);
            b[(*count)++]=(struct hw_reg_block){key,key_len,text+pos,0};
        }
        pos+=len+(nl?1:0);
    }
    if(*count)b[*count-1].len=(size_t)(text+size-b[*count-1].start);
    return b;
}
static int hw_reg_ieq(const char *a,size_t an,const char *b,size_t bn)
{
    if(an!=bn)return 0;
    for(size_t i=0;i<an;i++)if(tolower((unsigned char)a[i])!=tolower((unsigned char)b[i]))return 0;
    return 1;
}
/* the console-owned root (single backslashes) a .reg key (double backslashes) is or lies under, else -1 */
static int hw_reg_owner(const char *key,size_t key_len,const char *const *roots,unsigned count)
{
    for(unsigned r=0;r<count;r++){
        char stored[256];size_t n=0;
        for(const char *p=roots[r];*p&&n+2<sizeof(stored);p++){stored[n++]=*p;if(*p=='\\')stored[n++]='\\';}
        if(key_len<n||!hw_reg_ieq(key,n,stored,n))continue;
        if(key_len==n||(key_len>=n+2&&key[n]=='\\'&&key[n+1]=='\\'))return (int)r;
    }
    return -1;
}
/* the ledger's "keys" (lower case .reg spelling); absent: none */
static char **hw_ledger_keys(unsigned *count)
{
    size_t size=0;char *text=read_whole(HW_INSTALL_LEDGER,&size);*count=0;
    if(!text)return NULL;
    char *p=strstr(text,"\"keys\"");
    char **keys=calloc(size/4+1,sizeof(*keys));
    if(!p||!keys||!(p=strchr(p,'['))){free(text);free(keys);return NULL;}
    for(p++;*p&&*p!=']';p++){
        if(*p!='"')continue;
        char *out=p+1,*key=out;
        for(p++;*p&&*p!='"';p++){if(*p=='\\'&&p[1])p++;*out++=*p;}
        *out=0;keys[(*count)++]=strdup(key);
        if(!*p)break;
    }
    free(text);return keys;
}
static int hw_ledger_has(char **keys,unsigned count,const char *key,size_t len)
{
    for(unsigned i=0;i<count;i++)if(hw_reg_ieq(keys[i],strlen(keys[i]),key,len))return 1;
    return 0;
}
static int hw_install_user_reg(const struct hw_install_list *l,const char *build_sha)
{
    static const char build_path[]=HW_INSTALL_ROOT "/" HW_INSTALL_USER_REG,live_path[]="/data/" HW_INSTALL_USER_REG;
    size_t build_size=0,live_size=0;
    char *build=read_whole(build_path,&build_size),*live=read_whole(live_path,&live_size);
    if(!build){free(live);note(HW_BUILD " PWINSTALL failed user_reg read_build errno=%d\n",errno);return -1;}
    const char *roots[HW_INSTALL_MAX_ROOTS];unsigned nroots=0;
    for(unsigned i=0;i<l->owneds;i++){
        int reset=0;for(unsigned j=0;j<l->resets;j++)if(!strcasecmp(l->owned[i],l->reset[j]))reset=1;
        if(!reset)roots[nroots++]=l->owned[i];
    }
    char *merged=NULL;size_t merged_size=0;const char *source="merged";
    unsigned kept=0,added=0,left_deleted=0,ledger_count=0;
    char **ledger=hw_ledger_keys(&ledger_count);
    if(!live||live_size<23||memcmp(live,"WINE REGISTRY Version 2",23)){
        source=live?"build (console copy not a registry file)":"build (console copy absent)";
        merged=build;merged_size=build_size;build=NULL;
    } else {
        size_t bh,lh;unsigned bn,ln;
        struct hw_reg_block *bb=hw_reg_blocks(build,build_size,&bh,&bn),*lb=hw_reg_blocks(live,live_size,&lh,&ln);
        merged=bb&&lb?malloc(build_size+live_size+1):NULL;
        if(!merged){free(bb);free(lb);free(build);free(live);note(HW_BUILD " PWINSTALL failed user_reg no_memory\n");return -1;}
        int inserted[HW_INSTALL_MAX_ROOTS]={0};
        #define HW_EMIT(p,n) do{memcpy(merged+merged_size,(p),(n));merged_size+=(n);}while(0)
        HW_EMIT(build,bh);
        for(unsigned i=0;i<bn;i++){
            int root=hw_reg_owner(bb[i].key,bb[i].key_len,roots,nroots);
            if(root<0){HW_EMIT(bb[i].start,bb[i].len);continue;}
            if(!inserted[root]){
                for(unsigned j=0;j<ln;j++)if(hw_reg_owner(lb[j].key,lb[j].key_len,roots,nroots)==root){HW_EMIT(lb[j].start,lb[j].len);kept++;}
                inserted[root]=1;
            }
            int on_console=0;
            for(unsigned j=0;j<ln&&!on_console;j++)on_console=hw_reg_ieq(lb[j].key,lb[j].key_len,bb[i].key,bb[i].key_len);
            if(on_console)continue;
            if(hw_ledger_has(ledger,ledger_count,bb[i].key,bb[i].key_len)){left_deleted++;continue;}
            HW_EMIT(bb[i].start,bb[i].len);added++;
        }
        for(unsigned r=0;r<nroots;r++)if(!inserted[r])
            for(unsigned j=0;j<ln;j++)if(hw_reg_owner(lb[j].key,lb[j].key_len,roots,nroots)==(int)r){HW_EMIT(lb[j].start,lb[j].len);kept++;}
        #undef HW_EMIT
        free(bb);free(lb);
    }
    for(unsigned i=0;i<ledger_count;i++)free(ledger[i]);
    free(ledger);
    int rc=hw_install_write(NULL,merged,merged_size,live_path,NULL,0666);
    int e=errno;
    note(HW_BUILD " PWINSTALL user_reg source=%s kept=%u added=%u left_deleted=%u build_sha=%.16s rc=%d errno=%d\n",
         source,kept,added,left_deleted,build_sha,rc,rc?e:0);
    free(merged);free(live);
    if(rc){free(build);return -1;}
    /* the ledger: the build's blocks under every console-owned key, lower case (tools/upload-hardware.py W207) */
    if(!build)build=read_whole(build_path,&build_size);
    size_t bh;unsigned bn=0;
    struct hw_reg_block *bb=build?hw_reg_blocks(build,build_size,&bh,&bn):NULL;
    size_t cap=256+build_size*2;char *json=bb?malloc(cap):NULL;size_t n=0;
    if(!json){free(bb);free(build);note(HW_BUILD " PWINSTALL failed ledger no_memory\n");return -1;}
    n+=(size_t)snprintf(json+n,cap-n,"{\n \"schema_version\": 1,\n \"build\": \"%s\",\n \"keys\": [",l->build);
    unsigned written=0;
    for(unsigned i=0;i<bn;i++){
        if(hw_reg_owner(bb[i].key,bb[i].key_len,l->owned,l->owneds)<0)continue;
        int dup=0;
        for(unsigned j=0;j<i&&!dup;j++)dup=hw_reg_owner(bb[j].key,bb[j].key_len,l->owned,l->owneds)>=0&&hw_reg_ieq(bb[j].key,bb[j].key_len,bb[i].key,bb[i].key_len);
        if(dup)continue;
        n+=(size_t)snprintf(json+n,cap-n,"%s\n  \"",written++?",":"");
        for(size_t k=0;k<bb[i].key_len;k++){
            char c=(char)tolower((unsigned char)bb[i].key[k]);
            if(c=='\\'||c=='"')json[n++]='\\';
            json[n++]=c;
        }
        json[n++]='"';
    }
    n+=(size_t)snprintf(json+n,cap-n,"\n ]\n}\n");
    rc=hw_install_write(NULL,json,n,HW_INSTALL_LEDGER,NULL,0644);
    note(HW_BUILD " PWINSTALL ledger keys=%u rc=%d errno=%d\n",written,rc,rc?errno:0);
    free(json);free(bb);free(build);
    return rc;
}

/* ---- the build PC's profile (builds before alpha-1) ---- */
static void hw_install_migrate_profile(const char *host)
{
    static const char *const folders[]={"Desktop","Documents","Downloads","Favorites","Music","Pictures","Videos"};
    if(!host||!*host||!strcmp(host,"orbis")||strchr(host,'/'))return;
    unsigned moved=0,kept=0;
    for(unsigned f=0;f<sizeof(folders)/sizeof(*folders);f++){
        char from[PATH_MAX],to[PATH_MAX];
        snprintf(from,sizeof(from),"/data/wine-prefix/drive_c/users/%s/%s",host,folders[f]);
        DIR *dir=opendir(from);if(!dir)continue;
        snprintf(to,sizeof(to),"/data/wine-prefix/drive_c/users/orbis/%s",folders[f]);
        hw_install_mkdirs(to,0777);
        for(struct dirent *e;(e=readdir(dir));){
            if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;
            char a[PATH_MAX],b[PATH_MAX];struct stat st;
            snprintf(a,sizeof(a),"%s/%s",from,e->d_name);snprintf(b,sizeof(b),"%s/%s",to,e->d_name);
            if(!stat(b,&st)){kept++;note(HW_BUILD " PWINSTALL migrate kept users/%s/%s/%.80s (orbis has one)\n",host,folders[f],e->d_name);continue;}
            if(sceKernelRename(a,b)){kept++;note(HW_BUILD " PWINSTALL migrate failed users/%s/%s/%.80s errno=%d\n",host,folders[f],e->d_name,errno);}
            else moved++;
        }
        closedir(dir);
    }
    if(moved||kept)note(HW_BUILD " PWINSTALL migrate profile=%s moved=%u kept=%u\n",host,moved,kept);
}

/* ---- the installer ---- */
static void hw_install_screen(int percent,const char *state)
{
    pthread_mutex_lock(&screen_lock);
    draw_screen(percent,state,NULL);
    pthread_mutex_unlock(&screen_lock);
}
/* 0: /data matches the package (or the package has no runtime); -1: failed, detail says why */
static int hw_install_runtime(char *detail,size_t detail_size)
{
    size_t size=0;char *text=read_whole(HW_INSTALL_LIST,&size);
    if(!text){note(HW_BUILD " PWINSTALL no_embedded_runtime errno=%d (the uploaded /data runtime is used)\n",errno);return 0;}
    size_t record_size=0;char *record=read_whole(HW_INSTALL_RECORD,&record_size);
    if(record&&record_size==size&&!memcmp(record,text,size)){free(record);free(text);note(HW_BUILD " PWINSTALL up_to_date\n");return 0;}
    struct hw_install_list list,previous;memset(&previous,0,sizeof(previous));
    char *copy=malloc(size+1);
    if(!copy||(memcpy(copy,text,size),copy[size]=0,hw_install_parse(&list,copy,size))){
        free(text);free(record);snprintf(detail,detail_size,"INSTALL LIST UNREADABLE");
        note(HW_BUILD " PWINSTALL failed list_unreadable\n");return -1;
    }
    if(record&&hw_install_parse(&previous,record,record_size))hw_install_free(&previous),record=NULL;
    note(HW_BUILD " PWINSTALL begin build=%s files=%u bytes=%llu previous=%s\n",list.build,list.files,
         (unsigned long long)list.total,previous.build?previous.build:"none");
    hw_install_screen(0,"INSTALLING ORBISDESK");
    uint64_t start=sceKernelGetProcessTime();
    /* pass 1: what must be copied (missing, other size), what is trusted (same size and the same sha the
     * last successful install wrote), what must be hashed */
    enum {HW_SKIP,HW_HASH,HW_COPY,HW_USER_REG};
    uint64_t copy_bytes=0,hash_bytes=0;unsigned to_copy=0,to_hash=0,trusted=0;
    for(unsigned i=0;i<list.files;i++){
        struct hw_install_file *f=&list.file[i];char target[PATH_MAX];struct stat st;
        snprintf(target,sizeof(target),"/data/%s",f->path);
        if(!strcmp(f->path,HW_INSTALL_USER_REG)){f->action=HW_USER_REG;continue;}
        if(stat(target,&st)||(uint64_t)st.st_size!=f->bytes){f->action=HW_COPY;copy_bytes+=f->bytes;to_copy++;continue;}
        int same=0;
        for(unsigned j=0;j<previous.files&&!same;j++)
            same=!strcmp(previous.file[j].path,f->path)&&!strcmp(previous.file[j].sha,f->sha)&&previous.file[j].bytes==f->bytes;
        if(same){f->action=HW_SKIP;trusted++;}else{f->action=HW_HASH;hash_bytes+=f->bytes;to_hash++;}
    }
    struct statvfs vfs;
    if(!statvfs("/data",&vfs)){
        uint64_t free_bytes=(uint64_t)vfs.f_bavail*vfs.f_frsize,needed=copy_bytes+hash_bytes+(256ull<<20);
        note(HW_BUILD " PWINSTALL space free_mb=%llu needed_mb=%llu\n",(unsigned long long)(free_bytes>>20),(unsigned long long)(needed>>20));
        if(free_bytes<needed){
            snprintf(detail,detail_size,"NOT ENOUGH SPACE: FREE %llu MB MORE",(unsigned long long)((needed-free_bytes+(1<<20)-1)>>20));
            hw_install_free(&list);hw_install_free(&previous);free(text);return -1;
        }
    } else note(HW_BUILD " PWINSTALL space unknown errno=%d\n",errno);
    note(HW_BUILD " PWINSTALL plan copy=%u copy_mb=%llu hash=%u hash_mb=%llu trusted=%u\n",to_copy,
         (unsigned long long)(copy_bytes>>20),to_hash,(unsigned long long)(hash_bytes>>20),trusted);
    int failed=0;
    for(unsigned i=0;i<list.dirs&&!failed;i++){
        char target[PATH_MAX];snprintf(target,sizeof(target),"/data/%s",list.dir[i]);
        int writable=hw_install_writable(&list,list.dir[i]);
        if(hw_install_mkdirs(target,writable?0777:0755)){failed=1;snprintf(detail,detail_size,"CANNOT CREATE A FOLDER (%d)",errno);
            note(HW_BUILD " PWINSTALL failed mkdir %s errno=%d\n",list.dir[i],errno);}
        else if(writable)chmod(target,0777);
    }
    /* pass 2 */
    uint64_t work=copy_bytes+hash_bytes+1,done=0;unsigned copied=0,present=0;int last_percent=-1;
    for(unsigned i=0;i<list.files&&!failed;i++){
        struct hw_install_file *f=&list.file[i];
        if(f->action==HW_SKIP||f->action==HW_USER_REG){present+=f->action==HW_SKIP;continue;}
        char source[PATH_MAX],target[PATH_MAX];
        snprintf(source,sizeof(source),HW_INSTALL_ROOT "/%s",f->path);snprintf(target,sizeof(target),"/data/%s",f->path);
        if(f->action==HW_HASH){
            char got[65];
            if(!hw_install_hash(target,got)&&!strcmp(got,f->sha)){present++;done+=f->bytes;goto progress;}
            f->action=HW_COPY;
        }
        {char *slash=strrchr(target,'/');if(slash){*slash=0;hw_install_mkdirs(target,hw_install_writable(&list,f->path)?0777:0755);*slash='/';}}
        if(hw_install_write(source,NULL,0,target,f->sha,hw_install_writable(&list,f->path)?0666:0644)){
            int e=errno;failed=1;
            if(e==ENOSPC)snprintf(detail,detail_size,"NOT ENOUGH SPACE");
            else if(e==EILSEQ)snprintf(detail,detail_size,"PACKAGE FILE DAMAGED - REINSTALL");
            else if(e==EACCES||e==EPERM)snprintf(detail,detail_size,"PERMISSION DENIED - START ONCE IN ROOT MODE");
            else snprintf(detail,detail_size,"COPY FAILED (%d)",e);
            errno=e;
            note(HW_BUILD " PWINSTALL failed copy %s errno=%d\n",f->path,errno);break;
        }
        copied++;done+=f->bytes;
    progress:{
        int percent=(int)(done*95/work);
        if(percent!=last_percent){
            char state[64];snprintf(state,sizeof(state),"INSTALLING ORBISDESK %u/%u",i+1,list.files);
            hw_install_screen(percent,state);last_percent=percent;
        }}
    }
    for(unsigned i=0;i<list.files&&!failed;i++)
        if(list.file[i].action==HW_USER_REG&&hw_install_user_reg(&list,list.file[i].sha)){failed=1;snprintf(detail,detail_size,"USER REGISTRY MERGE FAILED");}
    unsigned deleted=0;
    for(unsigned i=0;i<list.obsoletes&&!failed;i++){
        const char *p=list.obsolete[i];char target[PATH_MAX];
        if(strncmp(p,"wine-prefix/",12)||strstr(p,".."))continue;  /* the builder checks this too */
        snprintf(target,sizeof(target),"/data/%s",p);
        if(!unlink(target))deleted++;
        else if(errno!=ENOENT)note(HW_BUILD " PWINSTALL obsolete %s errno=%d\n",p,errno);
    }
    if(!failed)hw_install_migrate_profile(list.host);
    if(!failed&&hw_install_write(NULL,text,size,HW_INSTALL_RECORD,NULL,0644)){
        failed=1;snprintf(detail,detail_size,"CANNOT WRITE /DATA/ORBISDESK (%d)",errno);
        note(HW_BUILD " PWINSTALL failed record errno=%d\n",errno);
    }
    note(HW_BUILD " PWINSTALL %s copied=%u present=%u obsolete_deleted=%u copied_mb=%llu ms=%llu\n",failed?"failed":"done",
         copied,present,deleted,(unsigned long long)(copy_bytes>>20),(unsigned long long)((sceKernelGetProcessTime()-start)/1000));
    if(!failed)hw_install_screen(100,"ORBISDESK INSTALLED");
    hw_install_free(&list);hw_install_free(&previous);free(text);
    return failed?-1:0;
}
