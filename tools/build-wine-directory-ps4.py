#!/usr/bin/env python3
"""W110: preserve entries with unknown inode identity and audit Wine directory filtering."""
import pathlib,json,hashlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
base=json.loads((ROOT/'build/wine-boot/report.json').read_text());entry=next(e for e in base['results'] if e['unit']=='file')
original=ROOT/'.deps/wine/ps4-overlay/dlls/ntdll/unix/file.c'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if sha(original)!=entry['source_sha256']:raise SystemExit('Wine file.c changed from proven input')
text=original.read_text()
def replace(old,new):
    global text
    if text.count(old)!=1:raise SystemExit('Directory source context changed: '+old[:90])
    text=text.replace(old,new,1)
start=text.index('static NTSTATUS read_directory_data_readdir( ')
end=text.index('\n\n/***********************************************************************',start)
text=text[:start]+r'''static NTSTATUS read_directory_data_readdir( struct dir_data *data, const UNICODE_STRING *mask )
{
    struct dirent *de;
    NTSTATUS status = STATUS_NO_MEMORY;
    DIR *dir = opendir(".");
    if (!dir) return errno_to_status(errno);
    if (!append_entry(data,".",NULL,mask) || !append_entry(data,"..",NULL,mask)) goto done;
    for (;;)
    {
        errno = 0;
        de = readdir(dir);
        if (!de)
        {
            int saved = errno;
            status = saved ? errno_to_status(saved) : STATUS_SUCCESS;
            if (saved) fprintf(stderr,"PWDIRENUM read_failed errno=%d status=%08x\n",saved,status);
            break;
        }
        if (!strcmp(de->d_name,".") || !strcmp(de->d_name,"..")) continue;
        if (!append_entry(data,de->d_name,NULL,mask)) goto done;
    }
done:
    closedir(dir);
    return status;
}
'''+text[end:]
replace('''    if (!stat( name, &st ))
    {
        ignored_files[ignored_files_count].dev''','''    if (!stat( name, &st ) && st.st_ino)
    {
        ignored_files[ignored_files_count].dev''')
replace('''static inline BOOL is_ignored_file( const struct stat *st )
{
    unsigned int i;''','''extern int pw_trace_enabled( void );  /* alpha-1: OrbisDesk's trace switch (platform/ps4/pw_trace.h) */

static inline BOOL is_ignored_file( const struct stat *st )
{
    unsigned int i;
    /* A missing inode is not proof that this entry is the hidden prefix/dev/proc. */
    if (!st->st_ino) return FALSE;''')
# alpha-1: these two fire per directory entry (an entry gone between readdir and stat, the hidden prefix entries);
# traces only (platform/ps4/pw_trace.h, pw_trace_enabled in platform/ps4/pw_wine_platform.c)
replace('''        TRACE( "file no longer exists %s\\n", debugstr_a(names->unix_name) );''','''        if (pw_trace_enabled()) fprintf(stderr,"PWDIRENUM stat_failed name=%s errno=%d\\n",names->unix_name,errno);
        TRACE( "file no longer exists %s\\n", debugstr_a(names->unix_name) );''')
replace('''        TRACE( "ignoring file %s\\n", debugstr_a(names->unix_name) );''','''        if (pw_trace_enabled()) fprintf(stderr,"PWDIRENUM ignored name=%s dev=%llu ino=%llu\\n",names->unix_name,
                (unsigned long long)st.st_dev,(unsigned long long)st.st_ino);
        TRACE( "ignoring file %s\\n", debugstr_a(names->unix_name) );''')
# W151: the per-entry logs of W110 (native_entry, returned, matched, cached) are gone: they wrote
# several lines per file on every Start menu opening. Failures still log.
# W134: FileFsDeviceInformation (GetFileType) from fstat, as Wine's generic branches classify:
# files and directories are disk file systems, pipes and sockets named pipes, character
# devices unknown. Characteristics stay 0: no removable, remote or read-only flag is claimed.
# DVD (J002): except on the optical disc (the device of /mnt/disc, L: in pw_wine_fs.c): a CD-ROM
# file system on removable read-only media, so GetDriveType gives DRIVE_CDROM.
# W133: GetFileType returned FILE_TYPE_UNKNOWN (ERROR_NOT_SUPPORTED) for every file, and an MSVC
# C runtime then closes what it opened (_open_osfhandle): Blitz3D (SuperMarioKart.exe) never read
# its PNG and drew a NULL image.
replace('''#ifdef __ORBIS__
    /* Mount/device characteristics have not been implemented for PS4.
     * Preserve output instead of inventing read-only/local/device flags. */
    return STATUS_NOT_SUPPORTED;
#else''','''#ifdef __ORBIS__
    struct stat st;

    info->Characteristics = 0;
    if (fstat( fd, &st ) < 0) return errno_to_status( errno );
    if (S_ISCHR( st.st_mode )) info->DeviceType = FILE_DEVICE_UNKNOWN;
    else if (S_ISFIFO( st.st_mode ) || S_ISSOCK( st.st_mode )) info->DeviceType = FILE_DEVICE_NAMED_PIPE;
    else
    {
        struct stat disc, mnt;

        info->DeviceType = FILE_DEVICE_DISK_FILE_SYSTEM;
        if (!stat( "/mnt/disc", &disc ) && !stat( "/mnt", &mnt ) && disc.st_dev != mnt.st_dev &&
            disc.st_dev == st.st_dev)
        {
            info->DeviceType = FILE_DEVICE_CD_ROM_FILE_SYSTEM;
            info->Characteristics = FILE_REMOVABLE_MEDIA | FILE_READ_ONLY_DEVICE;
        }
    }
    return STATUS_SUCCESS;
#else''')
# W217: volume sizes (GetDiskFreeSpace, FileFsSizeInformation and the full-size classes) on
# Orbis. The SDK libc's fstatvfs is a raw syscall like its lstat/readlink; it failed on
# hardware, GetDiskFreeSpaceA left BytesPerSector at 0 and gta-vc.exe aligned its CD stream
# buffer to 0 (B007, docs/investigacion-gta-vc-base-0x400000.md).
# W218: W217's libkernel _fstatfs gets EPERM from the sandbox (PWFS statfs rc=-1 errno=1), as
# lstat does. W218 then tried libkernel_sys getfsstat, and the system closed the title inside
# that call (W218 run-0002: the log ends at the EPERM line, no exception, no process exit), so
# it is gone. _fstatfs fills the FreeBSD 9 struct statfs (f_bsize 0x10, f_blocks 0x20, f_bfree
# 0x28, f_bavail 0x30, f_fstypename 0x118, 0x1d8 bytes). When it is refused (user's decision,
# W218): success with the sector geometry Wine reports for any disk (512 bytes x 8, file.c
# below) and the size counts at 0, logged as PWFS geometry_only. No free space is claimed.
replace('''    if (fstatvfs( fd, &stfs ) < 0) return errno_to_status( errno );
    bsize = stfs.f_frsize;''','''#ifdef __ORBIS__
    {
        extern int _fstatfs( int fd, void *buf );
        static int logged_fd, logged_geometry;
        unsigned char kernel_statfs[0x400];
        const unsigned char *found = NULL;
        ULONGLONG blocks = 0, bfree = 0;
        LONGLONG bavail = 0;

        memset( kernel_statfs, 0, sizeof(kernel_statfs) );
        if (!_fstatfs( fd, kernel_statfs )) found = kernel_statfs;
        else if (!logged_fd++) fprintf( stderr, "PWFS statfs rc=-1 errno=%d\\n", errno );
        if (found)
        {
            memcpy( &bsize, found + 0x10, sizeof(bsize) );
            memcpy( &blocks, found + 0x20, sizeof(blocks) );
            memcpy( &bfree, found + 0x28, sizeof(bfree) );
            memcpy( &bavail, found + 0x30, sizeof(bavail) );
            if (!logged_geometry++)
                fprintf( stderr, "PWFS statfs bsize=%llu blocks=%llu bfree=%llu bavail=%lld fstype=%.16s\\n",
                         (unsigned long long)bsize, (unsigned long long)blocks, (unsigned long long)bfree,
                         (long long)bavail, (const char *)found + 0x118 );
        }
        else
        {
            bsize = 4096;   /* not 2048: the 512 x 8 geometry below */
            if (!logged_geometry++) fprintf( stderr, "PWFS geometry_only bytes_per_sector=512 sectors_per_unit=8 counts=0\\n" );
        }
        stfs.f_blocks = blocks;
        stfs.f_bfree = bfree;
        stfs.f_bavail = bavail < 0 ? 0 : bavail;
    }
#else
    if (fstatvfs( fd, &stfs ) < 0) return errno_to_status( errno );
    bsize = stfs.f_frsize;
#endif''')
# DVD (J002): device errors (a disc ejected, or a USB disk pulled, under an open file: its reads
# fail with the kernel's error) leave a trace, the first 32; ENODEV is STATUS_NO_SUCH_DEVICE like
# ENXIO instead of STATUS_UNSUCCESSFUL. Otherwise the program gets Wine's status, as before.
replace('''    case ENXIO:     return STATUS_NO_SUCH_DEVICE;''','''    case ENODEV:
    case ENXIO:     return STATUS_NO_SUCH_DEVICE;''')
replace('''    TRACE( "errno = %d\\n", err );
    switch (err)''','''    TRACE( "errno = %d\\n", err );
#ifdef __ORBIS__
    if (err == EIO || err == ENXIO || err == ENODEV)
    {
        static int logged;

        if (__atomic_add_fetch( &logged, 1, __ATOMIC_RELAXED ) <= 32)
            fprintf( stderr, "PWFS device_error errno=%d\\n", err );
    }
#endif
    switch (err)''')
work=ROOT/'build/directory-ps4';work.mkdir(parents=True,exist_ok=True);selected=work/'file.c';selected.write_text(text);obj=work/'file.o'
command=[str(selected) if arg==str(original) else str(obj) if arg==str(ROOT/'build/wine-boot/file.o') else arg for arg in entry['command']]
with (work/'compile.log').open('w') as log:subprocess.run(command,cwd=ROOT/'.deps/wine/ps4-unix',stdout=log,stderr=subprocess.STDOUT,check=True)
report={'wine_commit':base['wine_commit'],'original_source_sha256':sha(original),'source_sha256':sha(selected),'object':str(obj.relative_to(ROOT)),'object_sha256':sha(obj),'command':command}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
