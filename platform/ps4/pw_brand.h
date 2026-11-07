/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef PW_BRAND_H
#define PW_BRAND_H
#define PW_APP_NAME "OrbisDesk"
#ifndef PW_STATE_ROOT
#define PW_STATE_ROOT "/data/orbisdesk"
#endif
/* Compatibility only: never rewrite old logs or lose settings on an update. */
#ifndef PW_LEGACY_STATE_ROOT
#define PW_LEGACY_STATE_ROOT "/data/orbis-win"
#endif
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

/* Import small launcher settings once. Existing new files always win. Prefix,
 * documents, games and saves already live outside this state directory. */
static inline int pw_brand_prepare_state(void)
{
    static const char *const names[] = {"boot-mode.txt", "launch.txt", "next.txt",
        "next-context.txt", "user-reg-delivered.json"};
    char old[192], fresh[192], buffer[4096];
    int failures = 0;
    if (mkdir(PW_STATE_ROOT, 0777) && errno != EEXIST) return -1;
    int marker = open(PW_STATE_ROOT "/.brand-migrated-v1", O_RDONLY);
    if (marker >= 0) { close(marker); return 0; }
    for (unsigned i = 0; i < sizeof(names) / sizeof(names[0]); i++)
    {
        snprintf(old, sizeof(old), "%s/%s", PW_LEGACY_STATE_ROOT, names[i]);
        snprintf(fresh, sizeof(fresh), "%s/%s", PW_STATE_ROOT, names[i]);
        int source = open(old, O_RDONLY);
        if (source < 0) { if (errno != ENOENT) failures++; continue; }
        int target = open(fresh, O_WRONLY | O_CREAT | O_EXCL, 0666);
        if (target < 0) { if (errno != EEXIST) failures++; close(source); continue; }
        int failed = 0;
        ssize_t count;
        while ((count = read(source, buffer, sizeof(buffer))) > 0)
        {
            ssize_t done = 0;
            while (done < count)
            {
                ssize_t n = write(target, buffer + done, (size_t)(count - done));
                if (n <= 0) { failed = 1; break; }
                done += n;
            }
            if (failed) break;
        }
        if (count < 0 || fsync(target)) failed = 1;
        close(source);
        if (close(target)) failed = 1;
        if (failed) { unlink(fresh); failures++; }
    }
    if (!failures)
    {
        marker = open(PW_STATE_ROOT "/.brand-migrated-v1", O_WRONLY | O_CREAT | O_EXCL, 0644);
        if (marker >= 0) close(marker);
        else if (errno != EEXIST) failures++;
    }
    return failures ? -1 : 0;
}
#endif
