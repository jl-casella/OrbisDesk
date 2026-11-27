/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_OVERLAY_PROFILES_H
#define PW_OVERLAY_PROFILES_H
/* Basenames are Wine AppDefaults identities, never paths to open or execute. */
#include <string.h>
#include <strings.h>
#include <stdio.h>
enum {PW_PROFILE_MAX=128};
struct pw_profile {char name[64];int bits;};
struct pw_profiles {struct pw_profile rows[PW_PROFILE_MAX];int count;};
static int pw_profile_allowed(const char *name)
{
    static const char *const internal[]={"wfm.exe","explorer.exe","services.exe","winedevice.exe",
        "plugplay.exe","rpcss.exe","svchost.exe","conhost.exe","wineboot.exe","winemenubuilder.exe",
        "orbis32host.exe","start.exe","rundll32.exe"};
    size_t n=name?strlen(name):0;
    if(n<=4 || n>=64 || strcasecmp(name+n-4,".exe") || name[0]==' ' || name[0]=='.') return 0;
    for(const unsigned char *p=(const unsigned char *)name;*p;p++)
        if(*p<32 || *p==127 || strchr("/\\:*?\"<>|=",*p)) return 0;
    for(unsigned i=0;i<sizeof(internal)/sizeof(internal[0]);i++) if(!strcasecmp(name,internal[i])) return 0;
    return 1;
}
/* MRU first. append is for saved-only entries: it does not displace recent launches. */
static int pw_profiles_note(struct pw_profiles *p,const char *name,int bits,int append)
{
    int i;
    struct pw_profile row;
    if(!pw_profile_allowed(name)) return 0;
    for(i=0;i<p->count && strcasecmp(name,p->rows[i].name);i++);
    if(i<p->count) {
        if(bits!=32 && bits!=64) bits=p->rows[i].bits;
        if(append || !i) {p->rows[i].bits=bits;return 1;}
        row=p->rows[i];row.bits=bits;
        memmove(p->rows+1,p->rows,(size_t)i*sizeof(row));p->rows[0]=row;
        return 1;
    }
    memset(&row,0,sizeof(row));snprintf(row.name,sizeof(row.name),"%s",name);
    row.bits=bits==32 || bits==64?bits:0;
    if(append) {
        if(p->count==PW_PROFILE_MAX) return 0;
        p->rows[p->count++]=row;
    } else {
        if(p->count<PW_PROFILE_MAX) p->count++;
        memmove(p->rows+1,p->rows,(size_t)(p->count-1)*sizeof(row));p->rows[0]=row;
    }
    return 1;
}
#endif
