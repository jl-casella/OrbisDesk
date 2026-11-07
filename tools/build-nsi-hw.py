#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variant of Wine's nsi.dll, 64-bit (PE64) and 32-bit (PE32).

Phase 8. Same method as build-ddraw-hw.py: the pinned sources are copied to an overlay and
revised there; each object is compiled with the exact command the pinned Wine build uses (taken
from `make -n`), only with the overlay source and a separate output.

nsi.dll asks \\\\.\\Nsi (nsiproxy.sys, run by winedevice.exe) for every network table iphlpapi
reads. winedevice is a second process and does not run in the single-process model, so
GetAdaptersAddresses, GetAdaptersInfo, ipconfig and Winsock's local-address lookups all failed.
nsiproxy's Unix side would not help either: it reads getifaddrs (musl: netlink) and sysctl.

When the device cannot be opened, the revised nsi.dll answers the tables itself from the
console's settings, which its Unix side (nsi.so, platform/ps4/pw_wine_netctl.c) reads with
sceNetCtlGetInfo:
- NDIS interface info and index->LUID: a loopback interface (1) and the console's wired or
  wireless interface (2), with its MAC address and MTU; up when the console has an IPv4 address;
- IPv4 unicast addresses: 127.0.0.1/8 and the console's address with its netmask;
- IPv4 routes: 127.0.0.0/8, the console's subnet and the default route to its gateway;
- IPv6: the loopback address only, no routes (the console's IPv6 settings are not read).
Link speeds and traffic counters are not known and stay 0. Any other table (TCP/UDP endpoints,
statistics, neighbours, IP interface parameters, change notifications) returns
ERROR_NOT_SUPPORTED with an ERR line, as does every table when libSceNetCtl cannot be read.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/nsi-hw-overlay';work=ROOT/'build/nsi-hw';out=ROOT/'out/nsi-hw'
ARCHS=('x86_64-windows','i386-windows')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'dlls/nsi',overlay)
shutil.copyfile(ROOT/'platform/ps4/pw_netctl_info.h',overlay/'pw_netctl_info.h')
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})

revise('nsi.c','''#include "winsock2.h"
#include "winternl.h"''','''#define __WINE_INIT_NPI_MODULEID  /* OrbisDesk phase 8: the module ids the console tables name */
#include "winsock2.h"
#include "winternl.h"''','The NPI module ids are defined here, as in iphlpapi.')
revise('nsi.c','''#include "wine/nsi.h"
#include "wine/debug.h"
''','''#include "wine/nsi.h"
#include "wine/debug.h"
#include "wine/unixlib.h"
#include "pw_netctl_info.h"
''','The Unix side call and its settings layout.')

revise('nsi.c','''DWORD WINAPI NsiAllocateAndGetTable(''','''/* OrbisDesk phase 8: the tables answered without nsiproxy.sys (tools/build-nsi-hw.py). */
#define CONSOLE_INTERFACES 2
struct console_interface
{
    UINT index;
    NET_LUID luid;
    GUID guid;
    UINT type;
    const WCHAR *alias;
    const WCHAR *descr;
    BYTE mac[6];
    USHORT mac_len;
    UINT mtu;
    UINT oper;
    IN_ADDR addr;
    IN_ADDR mask;
    IN_ADDR gateway;
};

struct console
{
    struct console_interface ifs[CONSOLE_INTERFACES];
};

static DWORD console_read( struct console *console )
{
    static NTSTATUS init_status = STATUS_PENDING;
    struct pw_netctl_info info;
    struct console_interface *lo = &console->ifs[0], *net = &console->ifs[1];
    NTSTATUS status;
    UINT i;

    if (init_status == STATUS_PENDING) init_status = __wine_init_unix_call();
    if (init_status)
    {
        ERR( "PWNSI no Unix side for nsi.dll, status %#lx\\n", init_status );
        return ERROR_NOT_SUPPORTED;
    }
    memset( &info, 0, sizeof(info) );
    if ((status = WINE_UNIX_CALL( pw_netctl_get_info, &info )))
    {
        ERR( "PWNSI libSceNetCtl not read: init %#x, status %#lx\\n", info.init_rc, status );
        return ERROR_NOT_SUPPORTED;
    }

    memset( console, 0, sizeof(*console) );
    lo->index = 1;
    lo->type = IF_TYPE_SOFTWARE_LOOPBACK;
    lo->alias = L"Loopback";
    lo->descr = L"Software Loopback Interface 1";
    lo->mtu = 16384;
    lo->oper = IfOperStatusUp;
    lo->addr.S_un.S_un_b.s_b1 = 127;
    lo->addr.S_un.S_un_b.s_b4 = 1;
    lo->mask.S_un.S_un_b.s_b1 = 255;

    net->index = 2;
    net->type = info.device == PW_NETCTL_DEVICE_WIRELESS ? IF_TYPE_IEEE80211 : IF_TYPE_ETHERNET_CSMACD;
    net->alias = net->type == IF_TYPE_IEEE80211 ? L"Wi-Fi" : L"Ethernet";
    net->descr = net->type == IF_TYPE_IEEE80211 ? L"PlayStation 4 wireless network" : L"PlayStation 4 wired network";
    if (!info.mac_rc)
    {
        memcpy( net->mac, info.mac, sizeof(net->mac) );
        net->mac_len = sizeof(net->mac);
    }
    if (!info.mtu_rc) net->mtu = info.mtu;
    if (!info.ip_rc) memcpy( &net->addr, info.ip, 4 );
    if (!info.netmask_rc) memcpy( &net->mask, info.netmask, 4 );
    if (!info.route_rc) memcpy( &net->gateway, info.route, 4 );
    net->oper = net->addr.S_un.S_addr ? IfOperStatusUp : IfOperStatusDown;

    for (i = 0; i < CONSOLE_INTERFACES; i++)
    {
        struct console_interface *entry = &console->ifs[i];
        entry->luid.Info.NetLuidIndex = entry->index;
        entry->luid.Info.IfType = entry->type;
        /* as nsiproxy.sys makes them */
        entry->guid.Data1 = entry->index;
        memcpy( entry->guid.Data4 + 2, "NetDev", 6 );
    }
    return ERROR_SUCCESS;
}

static void console_string( IF_COUNTED_STRING *str, const WCHAR *value )
{
    memset( str, 0, sizeof(*str) );
    str->Length = min( wcslen( value ), ARRAY_SIZE(str->String) - 1 ) * sizeof(WCHAR);
    memcpy( str->String, value, str->Length );
}

static UINT prefix_length( IN_ADDR mask )
{
    const BYTE *bytes = &mask.S_un.S_un_b.s_b1;
    UINT length = 0, i, bit;
    for (i = 0; i < 4; i++)
        for (bit = 0x80; bit; bit >>= 1)
        {
            if (!(bytes[i] & bit)) return length;
            length++;
        }
    return length;
}

/* A table's rows: fill writes row ROW into zeroed buffers of the table's sizes. */
typedef void (*console_fill)( const struct console *console, UINT row, void *key, void *rw, void *dyn, void *stat );

static void ndis_ifinfo_fill( const struct console *console, UINT row, void *key, void *rw_data, void *dyn_data,
                              void *stat_data )
{
    const struct console_interface *entry = &console->ifs[row];
    struct nsi_ndis_ifinfo_rw *rw = rw_data;
    struct nsi_ndis_ifinfo_dynamic *dyn = dyn_data;
    struct nsi_ndis_ifinfo_static *stat = stat_data;

    *(NET_LUID *)key = entry->luid;
    rw->admin_status = MIB_IF_ADMIN_STATUS_UP;
    console_string( &rw->alias, entry->alias );
    rw->phys_addr.Length = entry->mac_len;
    memcpy( rw->phys_addr.Address, entry->mac, entry->mac_len );
    dyn->oper_status = entry->oper;
    dyn->media_conn_state = entry->oper == IfOperStatusUp ? MediaConnectStateConnected : MediaConnectStateDisconnected;
    dyn->mtu = entry->mtu;
    stat->if_index = entry->index;
    console_string( &stat->descr, entry->descr );
    stat->type = entry->type;
    stat->access_type = entry->type == IF_TYPE_SOFTWARE_LOOPBACK ? NET_IF_ACCESS_LOOPBACK : NET_IF_ACCESS_BROADCAST;
    stat->conn_type = NET_IF_CONNECTION_DEDICATED;
    stat->if_guid = entry->guid;
    stat->conn_present = entry->type != IF_TYPE_SOFTWARE_LOOPBACK;
    stat->perm_phys_addr = rw->phys_addr;
    stat->flags.hw = entry->type != IF_TYPE_SOFTWARE_LOOPBACK;
}

static void ndis_index_luid_fill( const struct console *console, UINT row, void *key, void *rw, void *dyn, void *stat )
{
    *(UINT *)key = console->ifs[row].index;
    *(NET_LUID *)stat = console->ifs[row].luid;
}

/* The interfaces with an IPv4 address: loopback always, the network one when it has one. */
static UINT ipv4_interfaces( const struct console *console, const struct console_interface *rows[CONSOLE_INTERFACES] )
{
    UINT i, count = 0;
    for (i = 0; i < CONSOLE_INTERFACES; i++)
        if (console->ifs[i].addr.S_un.S_addr) rows[count++] = &console->ifs[i];
    return count;
}

static void ipv4_unicast_fill( const struct console *console, UINT row, void *key_data, void *rw_data, void *dyn_data,
                               void *stat )
{
    const struct console_interface *rows[CONSOLE_INTERFACES];
    struct nsi_ipv4_unicast_key *key = key_data;
    struct nsi_ip_unicast_rw *rw = rw_data;
    struct nsi_ip_unicast_dynamic *dyn = dyn_data;

    ipv4_interfaces( console, rows );
    key->luid = rows[row]->luid;
    key->addr = rows[row]->addr;
    rw->preferred_lifetime = rw->valid_lifetime = ~0u;
    rw->prefix_origin = rows[row]->type == IF_TYPE_SOFTWARE_LOOPBACK ? IpPrefixOriginWellKnown : IpPrefixOriginOther;
    rw->suffix_origin = rows[row]->type == IF_TYPE_SOFTWARE_LOOPBACK ? IpSuffixOriginWellKnown : IpSuffixOriginOther;
    rw->on_link_prefix = prefix_length( rows[row]->mask );
    dyn->dad_state = IpDadStatePreferred;
}

/* IPv4 routes: per interface its subnet, and the default route of the network interface. */
struct console_route
{
    const struct console_interface *entry;
    IN_ADDR prefix;
    UINT prefix_len;
    IN_ADDR next_hop;
};

static UINT ipv4_routes( const struct console *console, struct console_route routes[3] )
{
    const struct console_interface *rows[CONSOLE_INTERFACES];
    UINT i, count = 0, interfaces = ipv4_interfaces( console, rows );

    for (i = 0; i < interfaces; i++)
    {
        routes[count].entry = rows[i];
        routes[count].prefix.S_un.S_addr = rows[i]->addr.S_un.S_addr & rows[i]->mask.S_un.S_addr;
        routes[count].prefix_len = prefix_length( rows[i]->mask );
        routes[count++].next_hop.S_un.S_addr = 0;
        if (rows[i]->gateway.S_un.S_addr)
        {
            routes[count].entry = rows[i];
            routes[count].prefix.S_un.S_addr = 0;
            routes[count].prefix_len = 0;
            routes[count++].next_hop = rows[i]->gateway;
        }
    }
    return count;
}

static void ipv4_forward_fill( const struct console *console, UINT row, void *key_data, void *rw_data, void *dyn_data,
                               void *stat_data )
{
    struct console_route routes[3];
    struct nsi_ipv4_forward_key *key = key_data;
    struct nsi_ip_forward_rw *rw = rw_data;
    struct nsi_ipv4_forward_dynamic *dyn = dyn_data;
    struct nsi_ip_forward_static *stat = stat_data;

    ipv4_routes( console, routes );
    key->prefix = routes[row].prefix;
    key->prefix_len = routes[row].prefix_len;
    key->luid = key->luid2 = routes[row].entry->luid;
    key->next_hop = routes[row].next_hop;
    rw->valid_lifetime = rw->preferred_lifetime = ~0u;
    rw->metric = routes[row].entry->type == IF_TYPE_SOFTWARE_LOOPBACK ? 75 : 25;
    rw->protocol = routes[row].next_hop.S_un.S_addr ? 3 /* MIB_IPPROTO_NETMGMT */ : 2 /* MIB_IPPROTO_LOCAL */;
    rw->loopback = routes[row].entry->type == IF_TYPE_SOFTWARE_LOOPBACK;
    rw->immortal = 1;
    dyn->addr2 = routes[row].prefix;
    stat->origin = NlroManual;
    stat->if_index = routes[row].entry->index;
}

static void ipv6_unicast_fill( const struct console *console, UINT row, void *key_data, void *rw_data, void *dyn_data,
                               void *stat )
{
    struct nsi_ipv6_unicast_key *key = key_data;
    struct nsi_ip_unicast_rw *rw = rw_data;
    struct nsi_ip_unicast_dynamic *dyn = dyn_data;

    key->luid = console->ifs[0].luid;
    key->addr.u.Byte[15] = 1;
    rw->preferred_lifetime = rw->valid_lifetime = ~0u;
    rw->prefix_origin = IpPrefixOriginWellKnown;
    rw->suffix_origin = IpSuffixOriginWellKnown;
    rw->on_link_prefix = 128;
    dyn->dad_state = IpDadStatePreferred;
}

struct console_table
{
    const NPI_MODULEID *module;
    DWORD table;
    DWORD sizes[4];
    console_fill fill;
};

static const struct console_table console_tables[] =
{
    { &NPI_MS_NDIS_MODULEID, NSI_NDIS_IFINFO_TABLE, { sizeof(NET_LUID), sizeof(struct nsi_ndis_ifinfo_rw),
      sizeof(struct nsi_ndis_ifinfo_dynamic), sizeof(struct nsi_ndis_ifinfo_static) }, ndis_ifinfo_fill },
    { &NPI_MS_NDIS_MODULEID, NSI_NDIS_INDEX_LUID_TABLE, { sizeof(UINT), 0, 0, sizeof(NET_LUID) }, ndis_index_luid_fill },
    { &NPI_MS_IPV4_MODULEID, NSI_IP_UNICAST_TABLE, { sizeof(struct nsi_ipv4_unicast_key), sizeof(struct nsi_ip_unicast_rw),
      sizeof(struct nsi_ip_unicast_dynamic), sizeof(struct nsi_ip_unicast_static) }, ipv4_unicast_fill },
    { &NPI_MS_IPV4_MODULEID, NSI_IP_FORWARD_TABLE, { sizeof(struct nsi_ipv4_forward_key), sizeof(struct nsi_ip_forward_rw),
      sizeof(struct nsi_ipv4_forward_dynamic), sizeof(struct nsi_ip_forward_static) }, ipv4_forward_fill },
    { &NPI_MS_IPV6_MODULEID, NSI_IP_UNICAST_TABLE, { sizeof(struct nsi_ipv6_unicast_key), sizeof(struct nsi_ip_unicast_rw),
      sizeof(struct nsi_ip_unicast_dynamic), sizeof(struct nsi_ip_unicast_static) }, ipv6_unicast_fill },
    { &NPI_MS_IPV6_MODULEID, NSI_IP_FORWARD_TABLE, { sizeof(struct nsi_ipv6_forward_key), sizeof(struct nsi_ip_forward_rw),
      sizeof(struct nsi_ipv6_forward_dynamic), sizeof(struct nsi_ip_forward_static) }, NULL },
};

static UINT console_rows( const struct console_table *table, const struct console *console )
{
    const struct console_interface *rows[CONSOLE_INTERFACES];
    struct console_route routes[3];

    if (table->module == &NPI_MS_NDIS_MODULEID) return CONSOLE_INTERFACES;
    if (table->module == &NPI_MS_IPV4_MODULEID)
        return table->table == NSI_IP_UNICAST_TABLE ? ipv4_interfaces( console, rows ) : ipv4_routes( console, routes );
    return table->table == NSI_IP_UNICAST_TABLE ? 1 : 0;  /* IPv6: loopback only */
}

static const struct console_table *console_find( const NPI_MODULEID *module, DWORD table )
{
    UINT i;
    for (i = 0; i < ARRAY_SIZE(console_tables); i++)
        if (!memcmp( console_tables[i].module, module, sizeof(*module) ) && console_tables[i].table == table)
            return &console_tables[i];
    ERR( "PWNSI table %lu of module %s not provided without nsiproxy.sys\\n", table, debugstr_guid( &module->Guid ) );
    return NULL;
}

/* One row in zeroed buffers of the table's sizes. */
struct console_row
{
    BYTE data[4][1536];
};

static DWORD console_fill_row( const struct console_table *table, const struct console *console, UINT row,
                               struct console_row *out )
{
    UINT i;
    for (i = 0; i < 4; i++) if (table->sizes[i] > sizeof(out->data[i])) return ERROR_INVALID_PARAMETER;
    memset( out, 0, sizeof(*out) );
    table->fill( console, row, out->data[0], out->data[1], out->data[2], out->data[3] );
    return ERROR_SUCCESS;
}

static DWORD console_check_sizes( const struct console_table *table, const DWORD sizes[4] )
{
    UINT i;
    for (i = 0; i < 4; i++)
        if (sizes[i] && sizes[i] != table->sizes[i])
        {
            ERR( "PWNSI table %lu: size %lu of part %u, expected %lu\\n", table->table, sizes[i], i, table->sizes[i] );
            return ERROR_INVALID_PARAMETER;
        }
    return ERROR_SUCCESS;
}

static DWORD console_enumerate( struct nsi_enumerate_all_ex *params )
{
    const struct console_table *table = console_find( params->module, params->table );
    DWORD sizes[4] = { params->key_size, params->rw_size, params->dynamic_size, params->static_size };
    void *data[4] = { params->key_data, params->rw_data, params->dynamic_data, params->static_data };
    BOOL want_data = params->key_size || params->rw_size || params->dynamic_size || params->static_size;
    struct console *console;
    struct console_row *buffer;
    DWORD err;
    UINT rows, row, i;

    if (!table) return ERROR_NOT_SUPPORTED;
    if ((err = console_check_sizes( table, sizes ))) return err;
    if (!(console = malloc( sizeof(*console) ))) return ERROR_OUTOFMEMORY;
    if (!(buffer = malloc( sizeof(*buffer) ))) { free( console ); return ERROR_OUTOFMEMORY; }
    if ((err = console_read( console ))) goto done;
    rows = console_rows( table, console );
    for (row = 0; want_data && row < rows && row < params->count; row++)
    {
        if ((err = console_fill_row( table, console, row, buffer ))) goto done;
        for (i = 0; i < 4; i++)
            if (sizes[i]) memcpy( (BYTE *)data[i] + row * sizes[i], buffer->data[i], sizes[i] );
    }
    if (!want_data || rows <= params->count) params->count = rows;
    else err = ERROR_MORE_DATA;
done:
    free( buffer );
    free( console );
    return err;
}

/* The row whose key is KEY, filled into BUFFER, or ERROR_NOT_FOUND. */
static DWORD console_lookup( const struct console_table *table, const void *key, DWORD key_size, struct console_row *buffer )
{
    struct console *console;
    DWORD err;
    UINT rows, row;

    if (key_size != table->sizes[0]) return ERROR_INVALID_PARAMETER;
    if (!(console = malloc( sizeof(*console) ))) return ERROR_OUTOFMEMORY;
    if ((err = console_read( console ))) goto done;
    rows = console_rows( table, console );
    err = ERROR_NOT_FOUND;
    for (row = 0; row < rows; row++)
    {
        DWORD fill_err = console_fill_row( table, console, row, buffer );
        if (fill_err) { err = fill_err; break; }
        if (!memcmp( buffer->data[0], key, key_size )) { err = ERROR_SUCCESS; break; }
    }
done:
    free( console );
    return err;
}

static DWORD console_get_all( struct nsi_get_all_parameters_ex *params )
{
    const struct console_table *table = console_find( params->module, params->table );
    DWORD sizes[4] = { params->key_size, params->rw_size, params->dynamic_size, params->static_size };
    void *data[3] = { params->rw_data, params->dynamic_data, params->static_data };
    struct console_row *buffer;
    DWORD err;
    UINT i;

    if (!table) return ERROR_NOT_SUPPORTED;
    if ((err = console_check_sizes( table, sizes ))) return err;
    if (!(buffer = malloc( sizeof(*buffer) ))) return ERROR_OUTOFMEMORY;
    if (!(err = console_lookup( table, params->key, params->key_size, buffer )))
        for (i = 0; i < 3; i++) if (sizes[i + 1]) memcpy( data[i], buffer->data[i + 1], sizes[i + 1] );
    free( buffer );
    return err;
}

static DWORD console_get_parameter( struct nsi_get_parameter_ex *params )
{
    const struct console_table *table = console_find( params->module, params->table );
    struct console_row *buffer;
    DWORD err, part;

    if (!table) return ERROR_NOT_SUPPORTED;
    switch (params->param_type)
    {
    case NSI_PARAM_TYPE_RW: part = 1; break;
    case NSI_PARAM_TYPE_DYNAMIC: part = 2; break;
    case NSI_PARAM_TYPE_STATIC: part = 3; break;
    default: return ERROR_INVALID_PARAMETER;
    }
    if (params->data_offset > table->sizes[part] || params->data_size > table->sizes[part] - params->data_offset)
        return ERROR_INVALID_PARAMETER;
    if (!(buffer = malloc( sizeof(*buffer) ))) return ERROR_OUTOFMEMORY;
    if (!(err = console_lookup( table, params->key, params->key_size, buffer )))
        memcpy( params->data, buffer->data[part] + params->data_offset, params->data_size );
    free( buffer );
    return err;
}

DWORD WINAPI NsiAllocateAndGetTable(''','The tables built from the console settings.')

revise('nsi.c','''    BYTE *out, *ptr;

    if (device == INVALID_HANDLE_VALUE) return GetLastError();

    out_size = sizeof(DWORD) +''','''    BYTE *out, *ptr;

    if (device == INVALID_HANDLE_VALUE) return console_enumerate( params );  /* OrbisDesk phase 8 */

    out_size = sizeof(DWORD) +''','Enumeration without the device.')
revise('nsi.c','''    BYTE *out, *ptr;

    if (device == INVALID_HANDLE_VALUE) return GetLastError();

    in = malloc( in_size );
    out = malloc( out_size );''','''    BYTE *out, *ptr;

    if (device == INVALID_HANDLE_VALUE) return console_get_all( params );  /* OrbisDesk phase 8 */

    in = malloc( in_size );
    out = malloc( out_size );''','All parameters of one row without the device.')
revise('nsi.c','''    DWORD err = ERROR_SUCCESS;

    if (device == INVALID_HANDLE_VALUE) return GetLastError();

    in = malloc( in_size );
    if (!in) return ERROR_OUTOFMEMORY;
    in->module = *params->module;
    in->first_arg = params->first_arg;
    in->table = params->table;
    in->key_size = params->key_size;
    in->param_type''','''    DWORD err = ERROR_SUCCESS;

    if (device == INVALID_HANDLE_VALUE) return console_get_parameter( params );  /* OrbisDesk phase 8 */

    in = malloc( in_size );
    if (!in) return ERROR_OUTOFMEMORY;
    in->module = *params->module;
    in->first_arg = params->first_arg;
    in->table = params->table;
    in->key_size = params->key_size;
    in->param_type''','One parameter of one row without the device.')
revise('nsi.c','''    if (params->unk) FIXME( "unknown parameter %#lx.\\n", params->unk );

    if (device == INVALID_HANDLE_VALUE) return GetLastError();''','''    if (params->unk) FIXME( "unknown parameter %#lx.\\n", params->unk );

    if (device == INVALID_HANDLE_VALUE)
    {
        /* OrbisDesk phase 8: nothing reports changes of the console's settings */
        ERR( "PWNSI change notifications are not provided without nsiproxy.sys\\n" );
        return ERROR_NOT_SUPPORTED;
    }''','Change notifications without the device: an error with a trace.')

results={}
for arch in ARCHS:
    dry=subprocess.run(['make','-n','-W../../source/dlls/nsi/nsi.c',f'dlls/nsi/{arch}/nsi.dll'],cwd=BUILD,
                       capture_output=True,text=True,check=True).stdout.replace('\\\n',' ')
    arch_work=work/arch;arch_work.mkdir(exist_ok=True)
    commands=[]
    for line in dry.splitlines():
        if 'dlls/nsi/' not in line:continue
        line=line.replace('../../source/dlls/nsi/nsi.c',str(overlay/'nsi.c'))
        for name in ('nsi.o','nsi.dll'):line=line.replace(f'dlls/nsi/{arch}/'+name,str(arch_work/name))
        commands.append(line)
    if not any(str(overlay/'nsi.c') in c for c in commands) or not any(str(arch_work/'nsi.dll') in c for c in commands):
        raise SystemExit('make -n did not give the nsi commands for '+arch+':\n'+dry[-2000:])
    for command in commands:
        run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
        if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
        if 'warning' in run.stderr:print(run.stderr)
    target=out/arch/'nsi.dll';target.parent.mkdir(exist_ok=True);shutil.copyfile(arch_work/'nsi.dll',target)
    results[arch]={'path':str(target.relative_to(out)),'sha256':sha(target),'commands':commands}
manifest={'schema_version':1,'wine_commit':commit,'nsi':results,'revisions':revisions,
          'overlay_sha256':{'nsi.c':sha(overlay/'nsi.c'),'pw_netctl_info.h':sha(overlay/'pw_netctl_info.h')},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({arch:e['sha256'] for arch,e in results.items()}))
