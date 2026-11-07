/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_DIRENT_RECORD_H
#define PW_DIRENT_RECORD_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef struct PwDirHeader {uint32_t inode;uint16_t length;uint8_t type,namelen;} PwDirHeader;
/* -1 malformed; 0 unused/whiteout BSD slot (advance by length); 1 active entry.
 * Unused records can retain a deleted name or have no name at all.
 * BSD opendir/readdir also hides DT_WHT (14), which is not a live file. */
static inline int pw_dirent_record(const unsigned char *record,size_t remaining,PwDirHeader *header)
{
    if(remaining<sizeof(*header)) return -1;
    memcpy(header,record,sizeof(*header));
    if(header->length<sizeof(*header) || header->length>remaining) return -1;
    if(!header->inode || header->type==14) return 0;
    if(!header->namelen || header->length<sizeof(*header)+header->namelen+1 ||
       record[sizeof(*header)+header->namelen] || memchr(record+sizeof(*header),0,header->namelen)) return -1;
    return 1;
}
#endif
