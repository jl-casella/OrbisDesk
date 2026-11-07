/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 8: the console's network settings as libSceNetCtl reports them (sceNetCtlGetInfo),
 * passed from the Unix side (platform/ps4/pw_wine_netctl.c, "nsi.so" in pw_wine_unixlibs.c) to
 * the hardware nsi.dll (tools/build-nsi-hw.py), which builds iphlpapi's tables from it.
 * Only fixed-size fields: the same layout for PE32 and PE64, so the WoW64 call is the 64-bit one. */
#ifndef PW_NETCTL_INFO_H
#define PW_NETCTL_INFO_H

enum pw_netctl_call {pw_netctl_get_info,pw_netctl_call_count};

/* device */
#define PW_NETCTL_DEVICE_WIRED    0
#define PW_NETCTL_DEVICE_WIRELESS 1

struct pw_netctl_info
{
    /* libSceNetCtl's return codes: init, then one per item below (0 = read) */
    int init_rc,device_rc,mac_rc,mtu_rc,link_rc,ip_rc,netmask_rc,route_rc,dns1_rc,dns2_rc;
    unsigned int device,mtu,link;
    unsigned char mac[6],pad[2];
    unsigned char ip[4],netmask[4],route[4],dns1[4],dns2[4];  /* network order; 0.0.0.0 when unread */
};

#endif
