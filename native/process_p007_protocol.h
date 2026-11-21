/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* P007: the two prerequisites of a Wine child process, between the title and a loader-started helper:
 * its own fixed PE32 base (0x400000) and a real cross-process channel (AF_UNIX connect plus SCM_RIGHTS
 * in both directions, and the helper's end seen as the socket's end). Raw syscalls only on the helper side. */
#ifndef PROCESS_P007_PROTOCOL_H
#define PROCESS_P007_PROTOCOL_H
#ifndef P005_REQUEST_PATH
#define P005_REQUEST_PATH "/data/orbisdesk/process-p007/request.bin"
#endif
#include "process_loader_protocol.h"
#define P007_MAGIC UINT64_C(0x50303037464958ab)
#ifndef P007_RUN_PREFIX
#define P007_RUN_PREFIX "/data/orbisdesk/process-p007/run-"
#endif
#define P007_BASE UINT64_C(0x400000)
/* the span a fixed-base EXE of this kind needs at least (a PE32 image and its first heap) */
#define P007_SPAN UINT64_C(0x1000000)
#define P007_FLAG_UNMAP_HOST 1u  /* the helper may unmap what occupies the span, never its own code, stack or state */
#define P007_REGIONS 48
struct p007_request { uint64_t magic,token[2];uint32_t observer_pid,flags;char directory[160]; };
struct p007_region { uint64_t start,end;int32_t prot,type;uint32_t bits,pad;char name[32]; };
struct p007_state {
    uint64_t magic,token[2];
    uint32_t observer_pid,observer_tick,helper_pid,helper_ppid,helper_tick;
    uint32_t observer_seen_child,helper_done,helper_parent_progress;
    /* fixed base, helper side */
    int32_t helper_vq_status;uint32_t helper_region_count,helper_span_free_before,helper_unmapped;
    uint32_t helper_fixed_ok,helper_marker;uint64_t helper_fixed_address,helper_occupant_start,helper_occupant_end;
    char helper_occupant_name[32];
    /* channel */
    uint32_t helper_connected,helper_got_fd,helper_sent_fd,observer_got_fd;
    int32_t helper_ipc_stage,helper_ipc_error;
    struct p007_region regions[P007_REGIONS];
};
/* the kernel's sceKernelVirtualQuery record (OrbisKernelVirtualQueryInfo): its five flag bits take one byte
 * and the name follows at offset 33 (P007's first console run read "cutable" for "executable" at 36) */
struct p007_vq { uint64_t start,end;int64_t offset;int32_t prot,type;uint8_t bits;char name[32];uint8_t pad[7]; };
/* the kernel's msghdr and control header (platform/ps4/pw_wine_net.c, PwMessage/PwControl) */
struct p007_iov { void *base;uint64_t length; };
struct p007_msg { void *name;uint32_t namelen,pad0;struct p007_iov *iov;int32_t iovlen,pad1;void *control;uint32_t controllen;int32_t flags; };
struct p007_fd_control { uint32_t length;int32_t level,type;uint32_t pad;int32_t fd,fill; };
_Static_assert(sizeof(struct p007_request)==192,"request ABI");
_Static_assert(sizeof(struct p007_region)==64,"region ABI");
_Static_assert(sizeof(struct p007_vq)==72 && offsetof(struct p007_vq,name)==33,"virtual query ABI");
_Static_assert(sizeof(struct p007_msg)==48,"Orbis msghdr ABI");
_Static_assert(sizeof(struct p007_state)<=P005_PAGE,"state fits one page");
#define P007_FILE_BYTES 16
#endif
