# SPDX-License-Identifier: LGPL-2.1-or-later
"""Client descriptor cache pressure policy (GTA IV, 04.59).

Regular files/directories at fd >= 512 use Wine needs_close; no server handle is dropped.
04.61 also bounds retained file/directory copies before that numeric threshold.
"""
OLD = '                    *needs_close = (!reply->cacheable ||\n                                    !add_fd_to_cache( handle, fd, reply->type,\n                                                      reply->access, reply->options ));'
NEW = '#ifdef __ORBIS__\n                    if (reply->cacheable && fd >= 512 && (reply->type == FD_TYPE_FILE || reply->type == FD_TYPE_DIR))\n                    {\n                        static int logged;\n                        if (!__atomic_exchange_n( &logged, 1, __ATOMIC_RELAXED )) fprintf( stderr, "PWFS fd_cache off fd=%d type=%d: kept uncached from here\\n", fd, reply->type );\n                        *needs_close = 1;\n                    }\n                    else\n#endif\n                    *needs_close = (!reply->cacheable ||\n                                    !add_fd_to_cache( handle, fd, reply->type,\n                                                      reply->access, reply->options ));'

def patch_server(text):
    if text.count(NEW) == 1 and OLD not in text.replace(NEW, ""):
        return text
    if text.count(OLD) != 1 or "PWFS fd_cache off" in text:
        raise ValueError("Unexpected ntdll server fd cache context")
    return text.replace(OLD, NEW, 1)


# Cache mutations already run under fd_cache_mutex. Do not evict a cached fd:
# another thread may be using that borrowed descriptor outside the mutex.
BUDGET_CHANGES = [
    ('static union fd_cache_entry *fd_cache[FD_CACHE_ENTRIES];',
     '''static union fd_cache_entry *fd_cache[FD_CACHE_ENTRIES];
#ifdef __ORBIS__
/* 04.61: the in-process server already owns each live file. Bound client copies
 * independently of fd numbering; a file above the budget uses needs_close.
 * Existing cached copies stay valid until the normal NtClose/DuplicateHandle.
 * Each native client namespace has its own budget. */
enum { PW_FILE_FD_CACHE_LIMIT = 64 };
static unsigned int pw_cached_file_fds;
/* Lock-free diagnostics: pw_wine_open may run on the server while a client
 * holds fd_cache_mutex waiting for that server. Never take that mutex here. */
static unsigned int pw_fd_diag_retained, pw_fd_diag_peak, pw_fd_diag_bypasses;
void pw_wine_fd_cache_snapshot( unsigned int *retained, unsigned int *peak, unsigned int *bypasses, unsigned int *limit );
void pw_wine_fd_cache_snapshot( unsigned int *retained, unsigned int *peak, unsigned int *bypasses, unsigned int *limit )
{
    *retained = __atomic_load_n( &pw_fd_diag_retained, __ATOMIC_RELAXED );
    *peak = __atomic_load_n( &pw_fd_diag_peak, __ATOMIC_RELAXED );
    *bypasses = __atomic_load_n( &pw_fd_diag_bypasses, __ATOMIC_RELAXED );
    *limit = PW_FILE_FD_CACHE_LIMIT;
}
static int pw_file_fd_type( enum server_fd_type type )
{
    return type == FD_TYPE_FILE || type == FD_TYPE_DIR;
}
#endif'''),
    ('''    if (entry >= FD_CACHE_ENTRIES)
    {
        FIXME( "too many allocated handles, not caching %p\\n", handle );''',
     '''#ifdef __ORBIS__
    if (pw_file_fd_type( type ) && pw_cached_file_fds >= PW_FILE_FD_CACHE_LIMIT)
    {
        static int logged;
        __atomic_fetch_add( &pw_fd_diag_bypasses, 1, __ATOMIC_RELAXED );
        if (!logged)
        {
            logged = 1;
            fprintf( stderr, "PWFS fd_cache budget=%u: further file copies use needs_close\\n",
                     (unsigned int)PW_FILE_FD_CACHE_LIMIT );
        }
        return FALSE;
    }
#endif
    if (entry >= FD_CACHE_ENTRIES)
    {
        FIXME( "too many allocated handles, not caching %p\\n", handle );'''),
    ('''    assert( !cache.s.fd );
    return TRUE;''',
     '''    assert( !cache.s.fd );
#ifdef __ORBIS__
    if (pw_file_fd_type( type ))
    {
        ++pw_cached_file_fds;
        __atomic_store_n( &pw_fd_diag_retained, pw_cached_file_fds, __ATOMIC_RELAXED );
        if (pw_cached_file_fds > __atomic_load_n( &pw_fd_diag_peak, __ATOMIC_RELAXED ))
            __atomic_store_n( &pw_fd_diag_peak, pw_cached_file_fds, __ATOMIC_RELAXED );
    }
#endif
    return TRUE;'''),
    ('''        if (cache.s.type != FD_TYPE_INVALID) fd = cache.s.fd - 1;''',
     '''        if (cache.s.type != FD_TYPE_INVALID)
        {
            fd = cache.s.fd - 1;
#ifdef __ORBIS__
            if (cache.s.fd && pw_file_fd_type( cache.s.type ))
            {
                assert( pw_cached_file_fds );
                --pw_cached_file_fds;
                __atomic_store_n( &pw_fd_diag_retained, pw_cached_file_fds, __ATOMIC_RELAXED );
            }
#endif
        }'''),
    ('''            else if (reply->cacheable)
            {
                add_fd_to_cache( handle, ret, FD_TYPE_INVALID, 0, 0 );''',
     '''            else if (reply->cacheable
#ifdef __ORBIS__
                     && ret != STATUS_TOO_MANY_OPENED_FILES
                     && ret != STATUS_NO_MEMORY && ret != STATUS_INSUFFICIENT_RESOURCES
#endif
                     )
            {
                add_fd_to_cache( handle, ret, FD_TYPE_INVALID, 0, 0 );'''),
    ('''    server_leave_uninterrupted_section( &fd_cache_mutex, &sigset );

done:
    if (!ret && ((access & wanted_access) != wanted_access))''',
     '''#ifdef __ORBIS__
    if (ret == STATUS_TOO_MANY_OPENED_FILES || ret == STATUS_NO_MEMORY || ret == STATUS_INSUFFICIENT_RESOURCES)
    {
        static unsigned int failures;
        if (failures < 16)
        {
            ++failures;
            fprintf( stderr, "PWFS fd_lookup_failed status=%#x handle=%p cached_files=%u budget=%u\\n",
                     (unsigned int)ret, (void *)handle, pw_cached_file_fds, (unsigned int)PW_FILE_FD_CACHE_LIMIT );
        }
    }
#endif
    server_leave_uninterrupted_section( &fd_cache_mutex, &sigset );

done:
    if (!ret && ((access & wanted_access) != wanted_access))'''),
]


def patch_cache_budget(text):
    """Apply once to pinned/prepared server.c; reject partial/stale contexts."""
    if all(text.count(new) == 1 for old, new in BUDGET_CHANGES):
        return text
    if 'PW_FILE_FD_CACHE_LIMIT' in text:
        raise ValueError('Partial descriptor cache budget patch')
    for old, new in BUDGET_CHANGES:
        if text.count(old) != 1:
            raise ValueError('Unexpected descriptor cache budget context: ' + old[:70])
        text = text.replace(old, new, 1)
    return text
