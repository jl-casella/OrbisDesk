/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P007 helper: freestanding payload started by the resident loader (no SDK CRT, imports, spawn, graphics
 * or audio). It inventories its own address space, takes 0x400000 as a fixed base when that span is free
 * (or freed: P007_FLAG_UNMAP_HOST, never its own code, stack or state), then joins the title's AF_UNIX
 * socket and exchanges a file descriptor with it in each direction. */
#include "process_p007_protocol.h"
enum {SYS_EXIT=1,SYS_READ=3,SYS_WRITE=4,SYS_OPEN=5,SYS_CLOSE=6,SYS_GETPID=20,SYS_RECVMSG=27,SYS_SENDMSG=28,
      SYS_GETPPID=39,SYS_MUNMAP=73,SYS_FSYNC=95,SYS_SOCKET=97,SYS_CONNECT=98,SYS_MMAP=477,SYS_LSEEK=478,
      SYS_VIRTUAL_QUERY=572};
static long logfile=-1;
static unsigned put(char *line,unsigned n,const char *text){while(*text && n<220)line[n++]=*text++;return n;}
static unsigned put_number(char *line,unsigned n,uint64_t number,int hex)
{
    char digits[24];unsigned d=0;
    if(hex){n=put(line,n,"\"0x");do{digits[d++]="0123456789abcdef"[number&15];number>>=4;}while(number && d<24);}
    else do{digits[d++]=(char)('0'+number%10);number/=10;}while(number && d<24);
    while(d)line[n++]=digits[--d];if(hex)line[n++]='"';return n;
}
static void emit(char *line,unsigned n)
{
    line[n++]='}';line[n++]='\n';
    if(logfile>=0){p005_sys(SYS_WRITE,logfile,(long)line,n,0,0,0);p005_sys(SYS_FSYNC,logfile,0,0,0,0,0);}
}
static void log_value(const char *event,uint64_t value,int hex)
{
    char line[240];unsigned n=put(line,0,"{\"build\":\"P007\",\"side\":\"helper\",\"event\":\"");
    n=put(line,n,event);n=put(line,n,"\",\"value\":");n=put_number(line,n,value,hex);emit(line,n);
}
static void log_region(const struct p007_vq *info)
{
    char line[240],name[33];unsigned n=put(line,0,"{\"build\":\"P007\",\"side\":\"helper\",\"event\":\"region\",\"start\":");
    for(unsigned i=0;i<32;i++){char c=info->name[i];name[i]=(c>=32 && c<127 && c!='"' && c!='\\')?c:(c?'?':0);}name[32]=0;
    n=put_number(line,n,info->start,1);n=put(line,n,",\"end\":");n=put_number(line,n,info->end,1);
    n=put(line,n,",\"prot\":");n=put_number(line,n,(uint32_t)info->prot,0);n=put(line,n,",\"type\":");
    n=put_number(line,n,(uint32_t)info->type,0);n=put(line,n,",\"bits\":");n=put_number(line,n,info->bits,0);
    n=put(line,n,",\"name\":\"");n=put(line,n,name);line[n++]='"';emit(line,n);
}
static void path_join(char *out,const char *dir,const char *name)
{
    unsigned n=0;while(n<159 && dir[n]){out[n]=dir[n];n++;}out[n++]='/';
    while(*name && n<220)out[n++]=*name++;out[n]=0;
}
static void clear(void *where,unsigned bytes){volatile char *p=where;while(bytes--)*p++=0;}
static long query(uint64_t address,struct p007_vq *info)
{
    clear(info,sizeof(*info));return p005_sys(SYS_VIRTUAL_QUERY,(long)address,1,(long)info,sizeof(*info),0,0);
}
/* the first mapping at or after BASE that starts below BASE+P007_SPAN (0 when the span is free) */
static long occupant(struct p007_vq *info)
{
    long rc=query(P007_BASE,info);
    if(rc<0)return rc;  /* nothing mapped at or after it */
    return info->start<P007_BASE+P007_SPAN?1:0;
}
static int contains(const struct p007_vq *info,uint64_t address){return address>=info->start && address<info->end;}

__attribute__((noreturn,force_align_arg_pointer)) void _start(void)
{
    struct p007_request request;struct p007_vq info;char path[224];int result=80;struct p007_state *state=0;
    long sock=-1,own_file=-1,received=-1;void *fixed=0;volatile uint64_t stack_marker=0;
    long fd=p005_sys(SYS_OPEN,(long)P005_REQUEST_PATH,0,0,0,0,0);
    if(fd<0)goto done;
    long bytes=p005_sys(SYS_READ,fd,(long)&request,sizeof(request),0,0,0);p005_sys(SYS_CLOSE,fd,0,0,0,0,0);
    if(bytes!=sizeof(request) || request.magic!=P007_MAGIC || request.directory[159])goto done;
    /* only this probe's run directories can be selected by the request */
    const char *prefix=P007_RUN_PREFIX;unsigned i=0;while(prefix[i] && request.directory[i]==prefix[i])i++;
    if(prefix[i])goto done;
    for(unsigned j=i;request.directory[j];j++)if(request.directory[j]=='.')goto done;
    path_join(path,request.directory,"helper.jsonl");logfile=p005_sys(SYS_OPEN,(long)path,1|0x200|0x800,0644,0,0,0);
    uint32_t pid=(uint32_t)p005_sys(SYS_GETPID,0,0,0,0,0,0);log_value("helper_entered",pid,0);
    path_join(path,request.directory,"state.bin");fd=p005_sys(SYS_OPEN,(long)path,2,0,0,0,0);
    if(fd<0){result=81;goto done;}
    long view=p005_sys(SYS_MMAP,0,P005_PAGE,3,1,fd,0);p005_sys(SYS_CLOSE,fd,0,0,0,0,0);
    if(view<0){result=82;goto done;}state=(void *)view;
    if(state->magic!=P007_MAGIC || state->token[0]!=request.token[0] || state->token[1]!=request.token[1] ||
       state->observer_pid!=request.observer_pid || state->observer_pid==pid){result=83;goto done;}
    state->helper_ppid=(uint32_t)p005_sys(SYS_GETPPID,0,0,0,0,0,0);
    __atomic_store_n(&state->helper_pid,pid,__ATOMIC_RELEASE);

    /* 1. this process's mappings below 4 GiB */
    uint64_t cursor=0;unsigned count=0;long rc=0;
    for(unsigned n=0;n<256;n++){
        rc=query(cursor,&info);if(rc<0 || info.end<=cursor || info.start>=UINT64_C(0x100000000))break;
        log_region(&info);
        if(count<P007_REGIONS){
            struct p007_region *r=&state->regions[count++];r->start=info.start;r->end=info.end;r->prot=info.prot;
            r->type=info.type;r->bits=info.bits;for(unsigned k=0;k<32;k++)r->name[k]=info.name[k];
        }
        cursor=info.end;
    }
    state->helper_region_count=count;state->helper_vq_status=(int32_t)(rc<0?rc:0);log_value("regions",count,0);

    /* 2. the fixed base */
    long occupied=occupant(&info);
    state->helper_span_free_before=occupied==0 || occupied<0;
    if(occupied>0){
        state->helper_occupant_start=info.start;state->helper_occupant_end=info.end;
        for(unsigned k=0;k<32;k++)state->helper_occupant_name[k]=info.name[k];
        log_value("occupant_start",info.start,1);log_value("occupant_end",info.end,1);
    }
    if(occupied>0 && (request.flags&P007_FLAG_UNMAP_HOST)){
        uint64_t code=(uint64_t)&_start,stack=(uint64_t)&stack_marker,mine=(uint64_t)state;
        for(unsigned n=0;n<32 && occupant(&info)>0;n++){
            if(contains(&info,code) || contains(&info,stack) || contains(&info,mine)){log_value("occupant_is_own",info.start,1);break;}
            uint64_t from=info.start<P007_BASE?P007_BASE:info.start;
            uint64_t to=info.end>P007_BASE+P007_SPAN?P007_BASE+P007_SPAN:info.end;
            rc=p005_sys(SYS_MUNMAP,(long)from,(long)(to-from),0,0,0,0);
            log_value(rc<0?"unmap_failed":"unmapped",from,1);if(rc<0)break;
            state->helper_unmapped++;
        }
    }
    if(occupant(&info)==0 || query(P007_BASE,&info)<0){
        /* MAP_PRIVATE|MAP_ANON|MAP_FIXED over a span this process just found empty */
        long mapping=p005_sys(SYS_MMAP,(long)P007_BASE,(long)P007_SPAN,3,2|0x1000|0x10,-1,0);
        if(mapping==(long)P007_BASE){
            fixed=(void *)mapping;uint32_t marker=0xc0de0000u|(pid&0xffff);
            ((volatile uint32_t *)fixed)[0]=marker;((volatile uint32_t *)((char *)fixed+P007_SPAN))[-1]=marker;
            state->helper_marker=((volatile uint32_t *)fixed)[0];state->helper_fixed_address=(uint64_t)mapping;
            state->helper_fixed_ok=state->helper_marker==marker;
        }
        log_value("fixed_map",(uint64_t)mapping,1);
    }
    log_value("fixed_ok",state->helper_fixed_ok,0);

    /* 3. the title's socket: connect, receive its descriptor, send ours */
    state->helper_ipc_stage=1;sock=p005_sys(SYS_SOCKET,1,1,0,0,0,0);
    if(sock<0){state->helper_ipc_error=(int32_t)sock;goto heartbeat;}
    struct {uint8_t length,family;char path[104];} address;clear(&address,sizeof(address));
    path_join(path,request.directory,"ipc.sock");
    unsigned length=0;while(path[length] && length<103){address.path[length]=path[length];length++;}
    address.length=(uint8_t)(2+length+1);address.family=1;
    state->helper_ipc_stage=2;
    for(unsigned n=0;n<100;n++){rc=p005_sys(SYS_CONNECT,sock,(long)&address,address.length,0,0,0);if(rc>=0)break;p005_delay();}
    if(rc<0){state->helper_ipc_error=(int32_t)rc;log_value("connect_failed",(uint64_t)-rc,0);goto heartbeat;}
    state->helper_connected=1;log_value("connected",1,0);

    state->helper_ipc_stage=3;
    char byte=0;struct p007_iov iov={&byte,1};struct p007_fd_control control;struct p007_msg message;
    clear(&control,sizeof(control));clear(&message,sizeof(message));
    message.iov=&iov;message.iovlen=1;message.control=&control;message.controllen=sizeof(control);
    rc=p005_sys(SYS_RECVMSG,sock,(long)&message,0,0,0,0);
    if(rc!=1 || byte!='T' || message.controllen<20 || control.level!=0xffff || control.type!=1){
        state->helper_ipc_error=(int32_t)(rc<0?rc:-1000-(int)message.controllen);log_value("receive_failed",(uint64_t)(rc<0?-rc:message.controllen),0);goto heartbeat;
    }
    received=control.fd;log_value("received_fd",(uint64_t)received,0);
    uint64_t content[2]={0,0};
    p005_sys(SYS_LSEEK,received,0,0,0,0,0);rc=p005_sys(SYS_READ,received,(long)content,P007_FILE_BYTES,0,0,0);
    state->helper_got_fd=rc==P007_FILE_BYTES && content[0]==request.token[0] && content[1]==UINT64_C(0x214446454c544954);
    log_value("received_fd_content_ok",state->helper_got_fd,0);

    state->helper_ipc_stage=4;
    path_join(path,request.directory,"helper-file.bin");
    own_file=p005_sys(SYS_OPEN,(long)path,2|0x200|0x400,0666,0,0,0);
    if(own_file<0){state->helper_ipc_error=(int32_t)own_file;goto heartbeat;}
    content[0]=request.token[1];content[1]=UINT64_C(0x44465245504c4548);  /* "HELPERFD" */
    p005_sys(SYS_WRITE,own_file,(long)content,P007_FILE_BYTES,0,0,0);p005_sys(SYS_FSYNC,own_file,0,0,0,0,0);
    p005_sys(SYS_LSEEK,own_file,0,0,0,0,0);
    byte='H';clear(&control,sizeof(control));control.length=20;control.level=0xffff;control.type=1;control.fd=(int32_t)own_file;
    clear(&message,sizeof(message));message.iov=&iov;message.iovlen=1;message.control=&control;message.controllen=24;
    rc=p005_sys(SYS_SENDMSG,sock,(long)&message,0,0,0,0);
    state->helper_sent_fd=rc==1;log_value("sent_fd",state->helper_sent_fd,0);
    if(rc!=1)state->helper_ipc_error=(int32_t)rc;
    state->helper_ipc_stage=5;

heartbeat:
    {
        uint32_t start=__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE);
        for(unsigned n=0;n<250;n++){
            __atomic_add_fetch(&state->helper_tick,1,__ATOMIC_RELEASE);
            if(__atomic_load_n(&state->observer_tick,__ATOMIC_ACQUIRE)>=start+5 &&
               __atomic_load_n(&state->observer_seen_child,__ATOMIC_ACQUIRE) && n>=10 &&
               (!state->helper_sent_fd || __atomic_load_n(&state->observer_got_fd,__ATOMIC_ACQUIRE))){
                state->helper_parent_progress=1;result=42;break;
            }
            p005_delay();
        }
    }
    if(result!=42)result=84;
    if(fixed)log_value("fixed_marker_still",((volatile uint32_t *)fixed)[0],1);
    __atomic_store_n(&state->helper_done,(uint32_t)result,__ATOMIC_RELEASE);
done:
    log_value("helper_exit_requested",(uint32_t)result,0);
    /* the socket closes with the process: the title must see its end without being told */
    if(received>=0)p005_sys(SYS_CLOSE,received,0,0,0,0,0);
    if(own_file>=0)p005_sys(SYS_CLOSE,own_file,0,0,0,0,0);
    if(fixed)p005_sys(SYS_MUNMAP,(long)fixed,(long)P007_SPAN,0,0,0,0);
    if(state)p005_sys(SYS_MUNMAP,(long)state,P005_PAGE,0,0,0,0);
    if(logfile>=0)p005_sys(SYS_CLOSE,logfile,0,0,0,0,0);
    (void)sock;
    p005_sys(SYS_EXIT,result,0,0,0,0,0);__builtin_trap();
}
