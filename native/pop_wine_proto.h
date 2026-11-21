/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Minimal, self-contained wineserver wire types for the Phase B slim client (pop_wine_join.c).
 * include/wine/server_protocol.h cannot be included alone (it pulls in the full Windows headers), so these
 * structs are transcribed verbatim from the PINNED wine source
 * (.deps/wine/source/include/wine/server_protocol.h, SERVER_PROTOCOL_VERSION 961). Layouts, the fixed 64-byte
 * message size (struct request_max_size { int pad[16]; }), and the REQ_* enum ordinals are taken from it.
 * Drift is caught at runtime: the server sends its SERVER_PROTOCOL_VERSION during init and the client aborts
 * on mismatch, exactly like dlls/ntdll/unix/server.c. tools/check-wine-proto-pin.py re-verifies these values
 * against the pinned header at build time. */
#ifndef POP_WINE_PROTO_H
#define POP_WINE_PROTO_H
#include <stdint.h>

#define POP_SERVER_PROTOCOL_VERSION 961
#define POP_REQ_init_first_thread   5
#define POP_REQ_create_mutex        36
#define POP_GENERIC_MESSAGE_SIZE    64   /* sizeof(union generic_request)=sizeof(struct request_max_size) */

typedef unsigned int obj_handle_t;
typedef unsigned int data_size_t;
typedef unsigned int process_id_t;
typedef unsigned int thread_id_t;
typedef int64_t      timeout_t;

struct pop_request_header { int req; data_size_t request_size; data_size_t reply_size; };
struct pop_reply_header   { unsigned int error; data_size_t reply_size; };

struct init_first_thread_request {
    struct pop_request_header __header;
    int          unix_pid;
    int          unix_tid;
    int          debug_level;
    int          reply_fd;
    int          wait_fd;
    unsigned int page_size;
    char         __pad_36[4];
};
struct init_first_thread_reply {
    struct pop_reply_header __header;
    process_id_t pid;
    thread_id_t  tid;
    timeout_t    server_start;
    unsigned int session_id;
    obj_handle_t inproc_device;
    data_size_t  info_size;
    char         __pad_36[4];
};
struct create_mutex_request {
    struct pop_request_header __header;
    unsigned int access;
    int          owned;
    char         __pad_20[4];
};
struct create_mutex_reply {
    struct pop_reply_header __header;
    obj_handle_t handle;
    char         __pad_12[4];
};
struct object_attributes {
    obj_handle_t rootdir;
    unsigned int attributes;
    data_size_t  sd_len;
    data_size_t  name_len;
    /* followed by sd (sd_len bytes) then the object name as WCHAR (name_len bytes) */
};
struct send_fd { thread_id_t tid; int fd; };


_Static_assert(sizeof(struct init_first_thread_request)<=POP_GENERIC_MESSAGE_SIZE,"ift req fits");
_Static_assert(sizeof(struct init_first_thread_reply)<=POP_GENERIC_MESSAGE_SIZE,"ift reply fits");
_Static_assert(sizeof(struct create_mutex_request)<=POP_GENERIC_MESSAGE_SIZE,"cm req fits");
_Static_assert(sizeof(struct object_attributes)==16,"object_attributes is 16 bytes");

/* ---- Phase C (P015): window station, desktop, window, message queue. Transcribed from the same pinned
 * server_protocol.h (961); ordinals verified by tools/check-wine-proto-pin.py, layouts by the offsetof
 * asserts below. ---- */
#define POP_REQ_get_message             122
#define POP_REQ_reply_message           123
#define POP_REQ_accept_hardware_message 124
#define POP_REQ_create_window           142
#define POP_REQ_destroy_window          143
#define POP_REQ_set_window_pos          156
#define POP_REQ_set_window_text         159
#define POP_REQ_redraw_window           166
#define POP_REQ_open_winstation         172
#define POP_REQ_set_process_winstation  176
#define POP_REQ_open_desktop            179
#define POP_REQ_set_thread_desktop      184
#define POP_REQ_create_class            204

typedef unsigned int user_handle_t;
typedef unsigned int atom_t;
typedef uint64_t     lparam_t;
typedef uint64_t     client_ptr_t;
typedef client_ptr_t mod_handle_t;

enum pop_message_type { POP_MSG_ASCII, POP_MSG_UNICODE, POP_MSG_NOTIFY, POP_MSG_CALLBACK, POP_MSG_CALLBACK_RESULT,
                        POP_MSG_OTHER_PROCESS, POP_MSG_POSTED, POP_MSG_HARDWARE, POP_MSG_WINEVENT, POP_MSG_HOOK_LL };

struct pop_ratio { unsigned short num, den; };
struct pop_rectangle { int left, top, right, bottom; };
struct pop_obj_locator { uint64_t id; uint64_t offset; };
struct pop_class_info {
    atom_t atom; unsigned int style, cls_extra, win_extra;
    user_handle_t cursor, background, icon, icon_small;
    mod_handle_t instance; client_ptr_t wndproc, menu_name;
};

struct open_winstation_request { struct pop_request_header __header; unsigned int access, attributes; obj_handle_t rootdir; };
struct open_winstation_reply   { struct pop_reply_header __header; obj_handle_t handle; char __pad_12[4]; };
struct set_process_winstation_request { struct pop_request_header __header; obj_handle_t handle; };
struct open_desktop_request    { struct pop_request_header __header; obj_handle_t winsta; unsigned int flags, access, attributes; char __pad_28[4]; };
struct open_desktop_reply      { struct pop_reply_header __header; obj_handle_t handle; char __pad_12[4]; };
struct set_thread_desktop_request { struct pop_request_header __header; obj_handle_t handle; };
struct create_class_request    { struct pop_request_header __header; atom_t atom; unsigned int fnid, ansi; client_ptr_t client_ptr;
                                 data_size_t name_offset; char __pad_36[4]; };
struct create_class_reply      { struct pop_reply_header __header; struct pop_obj_locator locator; atom_t atom; char __pad_28[4]; };
struct create_window_request   { struct pop_request_header __header; user_handle_t parent, owner; atom_t atom;
                                 mod_handle_t class_instance, instance; unsigned int dpi_context, style, ex_style, ansi;
                                 struct pop_ratio dpi, raw_dpi; };
struct create_window_reply     { struct pop_reply_header __header; user_handle_t handle, parent, owner; char __pad_20[4]; client_ptr_t class_ptr; };
struct destroy_window_request  { struct pop_request_header __header; user_handle_t handle; };
struct set_window_pos_request  { struct pop_request_header __header; unsigned short swp_flags, paint_flags; user_handle_t handle, previous;
                                 struct pop_rectangle window, client; };
struct set_window_pos_reply    { struct pop_reply_header __header; unsigned int new_style, new_ex_style; user_handle_t surface_win; char __pad_20[4]; };
struct set_window_text_request { struct pop_request_header __header; user_handle_t handle; };
struct redraw_window_request   { struct pop_request_header __header; user_handle_t window; unsigned int flags; char __pad_20[4]; };
struct get_message_request     { struct pop_request_header __header; unsigned int flags; user_handle_t get_win; unsigned int get_first, get_last,
                                 hw_id, wake_mask, changed_mask, internal; char __pad_44[4]; };
struct get_message_reply       { struct pop_reply_header __header; user_handle_t win; unsigned int msg; lparam_t wparam, lparam;
                                 int type, x, y; unsigned int time; data_size_t total; char __pad_52[4]; };
struct reply_message_request   { struct pop_request_header __header; int remove; lparam_t result; };
struct accept_hardware_message_request { struct pop_request_header __header; unsigned int hw_id; };

#include <stddef.h>
_Static_assert(sizeof(struct pop_class_info)==56,"class_info");
_Static_assert(offsetof(struct create_class_request,client_ptr)==24&&sizeof(struct create_class_request)==40,"create_class");
_Static_assert(offsetof(struct create_class_reply,atom)==24,"create_class reply");
_Static_assert(offsetof(struct create_window_request,class_instance)==24&&sizeof(struct create_window_request)==64,"create_window");
_Static_assert(offsetof(struct create_window_reply,class_ptr)==24,"create_window reply");
_Static_assert(offsetof(struct set_window_pos_request,window)==24&&sizeof(struct set_window_pos_request)==56,"set_window_pos");
_Static_assert(sizeof(struct get_message_request)==48,"get_message");
_Static_assert(offsetof(struct get_message_reply,wparam)==16&&offsetof(struct get_message_reply,total)==48&&sizeof(struct get_message_reply)==56,"get_message reply");
_Static_assert(offsetof(struct reply_message_request,result)==16,"reply_message");
_Static_assert(sizeof(struct open_desktop_request)==32&&sizeof(struct open_winstation_request)==24,"winsta/desktop");

/* fixed-size message buffers, like union generic_request / generic_reply */
union pop_request { char raw[POP_GENERIC_MESSAGE_SIZE]; struct pop_request_header header;
                    struct init_first_thread_request ift; struct create_mutex_request cm;
                    struct open_winstation_request ows; struct set_process_winstation_request spw;
                    struct open_desktop_request od; struct set_thread_desktop_request std;
                    struct create_class_request cc; struct create_window_request cw; struct destroy_window_request dw;
                    struct set_window_pos_request swp; struct set_window_text_request swt; struct redraw_window_request rw;
                    struct get_message_request gm; struct reply_message_request rm; struct accept_hardware_message_request ahm; };
union pop_reply   { char raw[POP_GENERIC_MESSAGE_SIZE]; struct pop_reply_header header;
                    struct init_first_thread_reply ift; struct create_mutex_reply cm;
                    struct open_winstation_reply ows; struct open_desktop_reply od; struct create_class_reply cc;
                    struct create_window_reply cw; struct set_window_pos_reply swp; struct get_message_reply gm; };
_Static_assert(sizeof(union pop_request)==POP_GENERIC_MESSAGE_SIZE&&sizeof(union pop_reply)==POP_GENERIC_MESSAGE_SIZE,"64-byte messages");

#endif
