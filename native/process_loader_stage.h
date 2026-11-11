/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* File-only bootstrap tracing, independent of libc, the SDK CRT and kernel access. */
#include "process_loader_protocol.h"
#ifndef PW_LOADER_TRACE_PATH
#define PW_LOADER_TRACE_PATH "/data/orbisdesk/process-loader-p006.jsonl"
#endif
static inline __attribute__((unused)) void pw_loader_stage(const char *event,long value)
{
    char text[224],digits[24];unsigned n=0,d=0;unsigned long number;
    const char *p="{\"build\":\"P006\",\"event\":\"";while(*p)text[n++]=*p++;
    while(*event && n<150)text[n++]=*event++;
    p="\",\"value\":";while(*p)text[n++]=*p++;
    if(value<0){text[n++]='-';number=(unsigned long)(-(value+1))+1;}else number=(unsigned long)value;
    do{digits[d++]=(char)('0'+number%10);number/=10;}while(number && d<sizeof(digits));
    while(d)text[n++]=digits[--d];text[n++]='}';text[n++]='\n';
    long fd=p005_sys(5,(long)PW_LOADER_TRACE_PATH,0x209,0666,0,0,0);
    if(fd>=0){p005_sys(4,fd,(long)text,n,0,0,0);p005_sys(95,fd,0,0,0,0,0);p005_sys(6,fd,0,0,0,0,0);}
}
