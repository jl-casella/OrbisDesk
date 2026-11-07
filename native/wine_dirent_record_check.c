/* Focused wire-format contract check; no filesystem deletion or synthetic success. */
#include "pw_dirent_record.h"
#include <stdio.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL line %d\n",__LINE__);return 1;}} while(0)
static size_t append(unsigned char *p,unsigned inode,const char *name) {
    size_t n=strlen(name),bytes=(sizeof(PwDirHeader)+n+1+3)&~(size_t)3;
    PwDirHeader h={inode,bytes,8,n};memset(p,0,bytes);memcpy(p,&h,sizeof(h));memcpy(p+sizeof(h),name,n+1);return bytes;
}
int main(void) {
    unsigned char buffer[256];size_t bytes=0,pos=0;unsigned active=0,unused=0;PwDirHeader h;
    bytes+=append(buffer+bytes,11,"keep.txt");bytes+=append(buffer+bytes,0,"deleted.bmp");
    bytes+=append(buffer+bytes,0,"");
    size_t whiteout=bytes;bytes+=append(buffer+bytes,1,"whiteout");buffer[whiteout+6]=14;
    bytes+=append(buffer+bytes,12,"tail.mid");
    while(pos<bytes) {int state=pw_dirent_record(buffer+pos,bytes-pos,&h);CHECK(state>=0);if(state)active++;else unused++;pos+=h.length;}
    CHECK(active==2 && unused==3 && pos==bytes);
    memset(buffer,0,sizeof(buffer));CHECK(pw_dirent_record(buffer,8,&h)==-1);
    PwDirHeader bad={0,64,0,0};memcpy(buffer,&bad,sizeof(bad));CHECK(pw_dirent_record(buffer,8,&h)==-1);
    bytes=append(buffer,1,"a");buffer[sizeof(PwDirHeader)+1]='x';CHECK(pw_dirent_record(buffer,bytes,&h)==-1);
    bytes=append(buffer,1,"abc");buffer[sizeof(PwDirHeader)+1]=0;CHECK(pw_dirent_record(buffer,bytes,&h)==-1);
    CHECK(pw_dirent_record(buffer,7,&h)==-1);
    puts("PASS active/deleted/empty-unused/whiteout/tail records; reject malformed length and names");return 0;
}
