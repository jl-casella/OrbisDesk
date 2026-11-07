/* SPDX-License-Identifier: GPL-3.0-or-later */
/* S1: HTTPS from a native PS4 title, with no Steam account (docs/STEAM_S1.md). Built by
 * tools/build-steam-probe.py as ORBS00001, the Steam client's title. No Wine, no screen: it
 * runs the checks, writes them to STEAM_LOG and closes after 2 s.
 *   1. the console's clock (UTC), which certificate validation depends on;
 *   2. /dev/urandom, the only entropy Mbed TLS gets here (native/steam/steam_tls.c);
 *   3. the CA bundle in the package (Mozilla's, pinned in tools/build-steam-probe.py);
 *   4. https://api.steampowered.com/IContentServerDirectoryService/GetServersForSteamPipe/v1/
 *      (public, no account): handshake, chain validated, HTTP status, content servers listed;
 *   5. untrusted-root.badssl.com and expired.badssl.com: their chains must be refused
 *      (not trusted, expired), which shows the store and the clock are used, not only that a
 *      handshake completes.
 * Each line starts with PWSTEAM. Nothing is counted as passed that was not seen: the last line
 * says pass only when every check gave its expected result, and names the ones that did not.
 * Sends no account data: there is none. Built for the host too (-DSTEAM_HOST), to try the same
 * code on a PC before the console: there DNS is getaddrinfo and the log also goes to stdout. */
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include <mbedtls/error.h>
#include <mbedtls/ssl.h>
#include <mbedtls/version.h>
#include <mbedtls/x509_crt.h>
#include <psa/crypto.h>

#include "steam_tls.h"

#ifdef STEAM_HOST
#include <netdb.h>
#define STEAM_LOG "steam-probe.txt"
#define CA_BUNDLE "cacert.pem"
#else
#include <orbis/libkernel.h>
#include "../../platform/ps4/pw_brand.h"
#include <orbis/Sysmodule.h>
#define STEAM_LOG "/data/orbisdesk/steam-probe.txt"
#define CA_BUNDLE "/app0/assets/misc/cacert.pem"
int sceNetInit(void);
int sceNetPoolCreate(const char *name,int size,int flags);
int sceNetPoolDestroy(int pool);
int sceNetResolverCreate(const char *name,int pool,int flags);
int sceNetResolverDestroy(int resolver);
int sceNetResolverStartNtoa(int resolver,const char *name,struct in_addr *address,int timeout_us,int retries,int flags);
#endif

#define PROBE "S1"
enum {IO_TIMEOUT_MS=15000,RESPONSE_MAX=1<<20};

static int log_fd=-1;
static void note(const char *format,...)
{
    char line[768];
    va_list ap;
    int n;

    va_start(ap,format);n=vsnprintf(line,sizeof(line)-1,format,ap);va_end(ap);
    if(n<0) return;
    if(n>(int)sizeof(line)-2) n=sizeof(line)-2;
    line[n++]='\n';line[n]=0;
#ifdef STEAM_HOST
    fputs(line,stdout);fflush(stdout);
#else
    sceKernelDebugOutText(0,line);
#endif
    if(log_fd>=0) {write(log_fd,line,(size_t)n);fsync(log_fd);}
}

static void tls_error_text(int rc,char *text,size_t size)
{
    mbedtls_strerror(rc,text,size);
    for(char *c=text;*c;c++) if(*c==' ') *c='_';
}

/* IPv4 only, as Playden's client (ENABLE_IPV6=OFF) */
static int resolve(const char *host,struct in_addr *address)
{
#ifdef STEAM_HOST
    struct addrinfo hints,*list=NULL;
    int rc;

    memset(&hints,0,sizeof(hints));hints.ai_family=AF_INET;hints.ai_socktype=SOCK_STREAM;
    rc=getaddrinfo(host,NULL,&hints,&list);
    if(rc || !list) {note("PWSTEAM dns host=%s rc=%d found=0",host,rc);return -1;}
    *address=((struct sockaddr_in *)list->ai_addr)->sin_addr;
    freeaddrinfo(list);
#else
    int pool,resolver,rc;

    if((pool=sceNetPoolCreate("orbis-steam-dns",0x4000,0))<0) {
        note("PWSTEAM dns host=%s pool_create rc=0x%08x",host,(unsigned)pool);return -1;
    }
    if((resolver=sceNetResolverCreate("orbis-steam-dns",pool,0))<0) {
        note("PWSTEAM dns host=%s resolver_create rc=0x%08x",host,(unsigned)resolver);
        sceNetPoolDestroy(pool);return -1;
    }
    rc=sceNetResolverStartNtoa(resolver,host,address,5000000,2,0);
    sceNetResolverDestroy(resolver);sceNetPoolDestroy(pool);
    if(rc<0) {note("PWSTEAM dns host=%s rc=0x%08x found=0",host,(unsigned)rc);return -1;}
#endif
    {
        const unsigned char *b=(const unsigned char *)address;
        note("PWSTEAM dns host=%s found=1 address=%u.%u.%u.%u",host,b[0],b[1],b[2],b[3]);
    }
    return 0;
}

/* a blocking socket; reads wait at most IO_TIMEOUT_MS through poll (net_recv) */
static int tcp_connect(const char *host,const struct in_addr *address,int port)
{
    struct sockaddr_in to;
    int fd,rc;

    errno=0;fd=socket(AF_INET,SOCK_STREAM,0);
    if(fd<0) {note("PWSTEAM tcp host=%s socket=-1 errno=%d",host,errno);return -1;}
    memset(&to,0,sizeof(to));to.sin_family=AF_INET;to.sin_port=htons((uint16_t)port);to.sin_addr=*address;
    errno=0;rc=connect(fd,(struct sockaddr *)&to,sizeof(to));
    if(rc) {note("PWSTEAM tcp host=%s port=%d connect=-1 errno=%d",host,port,errno);close(fd);return -1;}
    note("PWSTEAM tcp host=%s port=%d connect=0",host,port);
    return fd;
}

static int net_send(void *context,const unsigned char *buffer,size_t len)
{
    int fd=*(int *)context;
    ssize_t sent;

    errno=0;sent=send(fd,buffer,len,0);
    if(sent<0) return errno==EINTR?MBEDTLS_ERR_SSL_WANT_WRITE:MBEDTLS_ERR_SSL_INTERNAL_ERROR;
    return (int)sent;
}

static int net_recv(void *context,unsigned char *buffer,size_t len,uint32_t timeout_ms)
{
    struct pollfd wait={.fd=*(int *)context,.events=POLLIN};
    ssize_t got;
    int ready;

    errno=0;ready=poll(&wait,1,timeout_ms?(int)timeout_ms:IO_TIMEOUT_MS);
    if(ready==0) return MBEDTLS_ERR_SSL_TIMEOUT;
    if(ready<0) return errno==EINTR?MBEDTLS_ERR_SSL_WANT_READ:MBEDTLS_ERR_SSL_INTERNAL_ERROR;
    errno=0;got=recv(wait.fd,buffer,len,0);
    if(got<0) return errno==EINTR?MBEDTLS_ERR_SSL_WANT_READ:MBEDTLS_ERR_SSL_INTERNAL_ERROR;
    return (int)got;  /* 0: the peer closed the connection */
}

struct tls
{
    mbedtls_entropy_context entropy;
    mbedtls_ctr_drbg_context drbg;
    mbedtls_x509_crt roots;
    int ready;
};

struct exchange
{
    int resolved,connected,handshake;      /* each step reached */
    int handshake_rc;
    uint32_t verify_flags;
    int status;                            /* HTTP status, 0 when none was read */
    unsigned char *body;size_t body_len;
};

/* One HTTPS GET with Connection: close. Fills *out with how far it got; the body is
 * de-chunked when the response is chunked. */
static void https_get(struct tls *tls,const char *host,const char *path,struct exchange *out)
{
    static unsigned char raw[RESPONSE_MAX+1];  /* +1: a NUL after the bytes read, for sscanf and strstr */
    mbedtls_ssl_context ssl;
    mbedtls_ssl_config conf;
    struct in_addr address;
    char request[512],text[160];
    size_t used=0;
    int fd=-1,rc,n;

    memset(out,0,sizeof(*out));
    mbedtls_ssl_init(&ssl);mbedtls_ssl_config_init(&conf);
    if(resolve(host,&address)) goto done;
    out->resolved=1;
    if((fd=tcp_connect(host,&address,443))<0) goto done;
    out->connected=1;

    if((rc=mbedtls_ssl_config_defaults(&conf,MBEDTLS_SSL_IS_CLIENT,MBEDTLS_SSL_TRANSPORT_STREAM,MBEDTLS_SSL_PRESET_DEFAULT))) {
        tls_error_text(rc,text,sizeof(text));note("PWSTEAM tls host=%s config rc=-0x%04x %s",host,-rc,text);goto done;
    }
    mbedtls_ssl_conf_authmode(&conf,MBEDTLS_SSL_VERIFY_REQUIRED);
    mbedtls_ssl_conf_ca_chain(&conf,&tls->roots,NULL);
    mbedtls_ssl_conf_rng(&conf,mbedtls_ctr_drbg_random,&tls->drbg);
    mbedtls_ssl_conf_read_timeout(&conf,IO_TIMEOUT_MS);
    if((rc=mbedtls_ssl_setup(&ssl,&conf)) || (rc=mbedtls_ssl_set_hostname(&ssl,host))) {
        tls_error_text(rc,text,sizeof(text));note("PWSTEAM tls host=%s setup rc=-0x%04x %s",host,-rc,text);goto done;
    }
    mbedtls_ssl_set_bio(&ssl,&fd,net_send,NULL,net_recv);
    do rc=mbedtls_ssl_handshake(&ssl);
    while(rc==MBEDTLS_ERR_SSL_WANT_READ || rc==MBEDTLS_ERR_SSL_WANT_WRITE);
    out->handshake_rc=rc;
    out->verify_flags=mbedtls_ssl_get_verify_result(&ssl);
    if(rc) {
        char flags[256]="";
        if(out->verify_flags && out->verify_flags!=(uint32_t)-1)
            mbedtls_x509_crt_verify_info(flags,sizeof(flags),"",out->verify_flags);
        for(char *c=flags;*c;c++) if(*c=='\n') *c=';';
        tls_error_text(rc,text,sizeof(text));
        note("PWSTEAM tls host=%s handshake rc=-0x%04x %s verify_flags=0x%08x %s",host,-rc,text,out->verify_flags,flags);
        goto done;
    }
    out->handshake=1;
    note("PWSTEAM tls host=%s handshake=ok version=%s suite=%s verify_flags=0x%08x",host,
         mbedtls_ssl_get_version(&ssl),mbedtls_ssl_get_ciphersuite(&ssl),out->verify_flags);

    n=snprintf(request,sizeof(request),"GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: OrbisDesk-SteamProbe/" PROBE
               "\r\nAccept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n",path,host);
    for(int sent=0;sent<n;) {
        rc=mbedtls_ssl_write(&ssl,(const unsigned char *)request+sent,(size_t)(n-sent));
        if(rc==MBEDTLS_ERR_SSL_WANT_READ || rc==MBEDTLS_ERR_SSL_WANT_WRITE) continue;
        if(rc<0) {tls_error_text(rc,text,sizeof(text));note("PWSTEAM http host=%s write rc=-0x%04x %s",host,-rc,text);goto done;}
        sent+=rc;
    }
    for(;;) {
        if(used==RESPONSE_MAX) {note("PWSTEAM http host=%s response over %d bytes, cut",host,RESPONSE_MAX);break;}
        rc=mbedtls_ssl_read(&ssl,raw+used,RESPONSE_MAX-used);
        if(rc==MBEDTLS_ERR_SSL_WANT_READ || rc==MBEDTLS_ERR_SSL_WANT_WRITE) continue;
#ifdef MBEDTLS_ERR_SSL_RECEIVED_NEW_SESSION_TICKET
        if(rc==MBEDTLS_ERR_SSL_RECEIVED_NEW_SESSION_TICKET) continue;  /* TLS 1.3 */
#endif
        if(rc==0 || rc==MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY) break;
        if(rc<0) {tls_error_text(rc,text,sizeof(text));note("PWSTEAM http host=%s read rc=-0x%04x %s after=%zu",host,-rc,text,used);break;}
        used+=(size_t)rc;
    }
    mbedtls_ssl_close_notify(&ssl);
    raw[used]=0;

    /* status line and headers */
    {
        unsigned char *end=NULL;
        int chunked=0;

        for(size_t i=0;i+3<used;i++) if(!memcmp(raw+i,"\r\n\r\n",4)) {end=raw+i;break;}
        if(!end || sscanf((const char *)raw,"HTTP/%*s %d",&out->status)!=1) {
            note("PWSTEAM http host=%s bytes=%zu no status line",host,used);out->status=0;goto done;
        }
        for(unsigned char *line=raw;line<end;) {
            unsigned char *next=line;
            while(next<end && *next!='\r') next++;
            if(next-line>=26 && !strncasecmp((const char *)line,"transfer-encoding:",18)) {
                for(unsigned char *c=line+18;c+7<=next;c++) if(!strncasecmp((const char *)c,"chunked",7)) chunked=1;
            }
            line=next+2;
        }
        out->body=end+4;out->body_len=used-(size_t)(out->body-raw);
        if(chunked) {
            unsigned char *read=out->body,*write=out->body,*limit=out->body+out->body_len;
            for(;;) {
                char *after;
                unsigned long size;
                if(read>=limit) {note("PWSTEAM http host=%s chunked body cut",host);break;}
                size=strtoul((const char *)read,&after,16);
                read=(unsigned char *)strstr(after,"\r\n");
                if(!read || read+2+size>limit) {note("PWSTEAM http host=%s chunked body cut",host);break;}
                read+=2;
                if(!size) break;
                memmove(write,read,size);write+=size;read+=size+2;
            }
            out->body_len=(size_t)(write-out->body);
        }
        note("PWSTEAM http host=%s status=%d bytes=%zu body=%zu chunked=%d",host,out->status,used,out->body_len,chunked);
    }
done:
    mbedtls_ssl_free(&ssl);mbedtls_ssl_config_free(&conf);
    if(fd>=0) close(fd);
}

static size_t count(const unsigned char *data,size_t len,const char *needle)
{
    size_t found=0,n=strlen(needle);
    for(size_t i=0;i+n<=len;i++) if(!memcmp(data+i,needle,n)) {found++;i+=n-1;}
    return found;
}

/* a chain the store must refuse with this flag: rejected=1 only for that reason */
static int refused_for(struct tls *tls,const char *host,uint32_t flag,const char *name)
{
    struct exchange result;
    int rejected;

    https_get(tls,host,"/",&result);
    if(!result.connected) {note("PWSTEAM tls %s rejected=- (no connection)",host);return 0;}
    rejected=result.handshake_rc==MBEDTLS_ERR_X509_CERT_VERIFY_FAILED && (result.verify_flags&flag);
    note("PWSTEAM tls %s rejected=%d expected=%s verify_flags=0x%08x",host,rejected,name,result.verify_flags);
    return rejected;
}

/* The whole bundle, read here (MBEDTLS_FS_IO is off: native/steam/mbedtls_user_config.h) up to
 * end of file, with the NUL that PEM parsing needs. Not sized by fstat: S1's first console run
 * (2026-11-07) parsed 0 roots with "format invalid", the DER path, which a buffer without the
 * PEM header or its final NUL takes; the SDK's struct stat is musl's, and its st_size need not
 * be where the console's kernel puts it (W180/W218 found that for statfs). The log line gives
 * what was read, fstat's st_size beside it, and the first bytes. Returns mbedtls_x509_crt_parse's
 * result (>0: certificates not parsed), or MBEDTLS_ERR_X509_FILE_IO_ERROR with *error the errno
 * of open or read. */
static int load_roots(mbedtls_x509_crt *roots,const char *path,int *error)
{
    struct stat info;
    unsigned char *data=NULL;
    size_t done=0,size=0;
    char head[33];
    int fd,rc;

    errno=0;fd=open(path,O_RDONLY);
    if(fd<0) {*error=errno;return MBEDTLS_ERR_X509_FILE_IO_ERROR;}
    memset(&info,0,sizeof(info));
    rc=fstat(fd,&info);
    for(;;) {
        ssize_t got;
        if(done+1>=size) {
            unsigned char *grown=realloc(data,size=size?size*2:262144);
            if(!grown) {*error=ENOMEM;free(data);close(fd);return MBEDTLS_ERR_X509_FILE_IO_ERROR;}
            data=grown;
        }
        got=read(fd,data+done,size-1-done);
        if(got<0 && errno==EINTR) continue;
        if(got<0) {*error=errno;free(data);close(fd);return MBEDTLS_ERR_X509_FILE_IO_ERROR;}
        if(got==0) break;
        done+=(size_t)got;
    }
    close(fd);data[done]=0;
    for(size_t i=0;i<sizeof(head)-1;i++) head[i]=i<done && data[i]>=0x20 && data[i]<0x7f?(char)data[i]:'.';
    head[sizeof(head)-1]=0;
    note("PWSTEAM ca read bytes=%zu fstat_rc=%d st_size=%lld head=%s",done,rc,(long long)info.st_size,head);
    rc=mbedtls_x509_crt_parse(roots,data,done+1);
    free(data);
    return rc;
}

int main(void)
{
    struct tls tls;
    struct sigaction ignore;
    char text[160],failed[256]="";
    time_t now;
    struct tm utc;
    int rc,error,zero,same,ok_entropy=0,ok_roots=0,ok_steam=0,ok_untrusted=0,ok_expired=0;

#ifndef STEAM_HOST
    pw_brand_prepare_state();
    mkdir("/data/orbisdesk",0777);
#endif
    log_fd=open(STEAM_LOG,O_WRONLY|O_CREAT|O_TRUNC,0666);
    note("PWSTEAM " PROBE " start log=%s log_fd=%d pid=%d uid=%d mbedtls=%s",STEAM_LOG,log_fd,getpid(),getuid(),MBEDTLS_VERSION_STRING);
    /* a peer that closes while we write must not end the title */
    memset(&ignore,0,sizeof(ignore));ignore.sa_handler=SIG_IGN;sigaction(SIGPIPE,&ignore,NULL);
#ifndef STEAM_HOST
    rc=(int)sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_NET);
    note("PWSTEAM sysmodule_net rc=0x%08x",(unsigned)rc);
    rc=sceNetInit();
    note("PWSTEAM net_init rc=0x%08x",(unsigned)rc);
#endif

    now=time(NULL);gmtime_r(&now,&utc);
    note("PWSTEAM clock utc=%04d-%02d-%02dT%02d:%02d:%02dZ unix=%lld",utc.tm_year+1900,utc.tm_mon+1,utc.tm_mday,
         utc.tm_hour,utc.tm_min,utc.tm_sec,(long long)now);

    error=0;rc=steam_entropy_check(&error,&zero,&same);
    ok_entropy=!rc;
    note("PWSTEAM entropy source=/dev/urandom ok=%d errno=%d all_zero=%d repeated=%d",ok_entropy,error,zero,same);

    memset(&tls,0,sizeof(tls));
    mbedtls_entropy_init(&tls.entropy);mbedtls_ctr_drbg_init(&tls.drbg);mbedtls_x509_crt_init(&tls.roots);
    if(ok_entropy) {
        psa_status_t status=psa_crypto_init();
        rc=mbedtls_ctr_drbg_seed(&tls.drbg,mbedtls_entropy_func,&tls.entropy,(const unsigned char *)"orbis-steam-" PROBE,15);
        if(rc) tls_error_text(rc,text,sizeof(text)); else text[0]=0;
        note("PWSTEAM rng psa_init=%d drbg_seed rc=-0x%04x %s",(int)status,-rc,text);
        tls.ready=status==PSA_SUCCESS && !rc;
    }
    else note("PWSTEAM rng skipped: no entropy, so no TLS");

    error=0;rc=load_roots(&tls.roots,CA_BUNDLE,&error);
    {
        int roots=0;
        if(error) note("PWSTEAM ca bundle=%s read failed errno=%d",CA_BUNDLE,error);
        for(const mbedtls_x509_crt *c=&tls.roots;c && c->raw.len;c=c->next) roots++;
        ok_roots=rc>=0 && roots>0;
        if(rc<0) tls_error_text(rc,text,sizeof(text)); else text[0]=0;
        note("PWSTEAM ca bundle=%s roots=%d not_parsed=%d %s",CA_BUNDLE,roots,rc>0?rc:0,text);
    }

    if(tls.ready && ok_roots) {
        struct exchange steam;
        size_t servers=0;

        https_get(&tls,"api.steampowered.com","/IContentServerDirectoryService/GetServersForSteamPipe/v1/?cell_id=0",&steam);
        if(steam.status==200) servers=count(steam.body,steam.body_len,"\"vhost\"");
        ok_steam=steam.handshake && !steam.verify_flags && steam.status==200 && servers>0;
        note("PWSTEAM https api.steampowered.com status=%d servers=%zu ok=%d",steam.status,servers,ok_steam);
        if(steam.body && steam.body_len) {
            char sample[161];
            size_t n=steam.body_len<160?steam.body_len:160;
            memcpy(sample,steam.body,n);sample[n]=0;
            for(char *c=sample;*c;c++) if(*c=='\n' || *c=='\r') *c=' ';
            note("PWSTEAM https body_start=%s",sample);
        }
        ok_untrusted=refused_for(&tls,"untrusted-root.badssl.com",MBEDTLS_X509_BADCERT_NOT_TRUSTED,"not_trusted");
        ok_expired=refused_for(&tls,"expired.badssl.com",MBEDTLS_X509_BADCERT_EXPIRED,"expired");
    }
    else note("PWSTEAM https skipped: rng_ready=%d roots=%d",tls.ready,ok_roots);

    if(!ok_entropy) strcat(failed," entropy");
    if(!ok_roots) strcat(failed," ca_bundle");
    if(!ok_steam) strcat(failed," steam_api");
    if(!ok_untrusted) strcat(failed," untrusted_root");
    if(!ok_expired) strcat(failed," expired");
    note("PWSTEAM " PROBE " result=%s%s%s",failed[0]?"fail":"pass",failed[0]?" failed=":"",failed[0]?failed+1:"");

    mbedtls_x509_crt_free(&tls.roots);mbedtls_ctr_drbg_free(&tls.drbg);mbedtls_entropy_free(&tls.entropy);
    mbedtls_psa_crypto_free();
    note("PWSTEAM " PROBE " end");
    if(log_fd>=0) close(log_fd);
#ifndef STEAM_HOST
    sceKernelUsleep(2000000);
#endif
    return failed[0]?1:0;
}
