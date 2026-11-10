/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W120: AudioOut sink for Wine's audio driver (pw_wine_audio.h). Its own main
 * port, separate from the DOS host's (native/dos_audio.c): AudioOut gives each user several
 * main ports. Opened on first use; a failure is logged and returned, never hidden. */
#include "pw_wine_audio.h"
#include "pw_trace.h"
#include <orbis/AudioOut.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static int port=-1,failed;
static uint64_t grains,nonzero;
static unsigned peak;

static int open_port(void)
{
    if(port>=0) return 0;
    if(failed) return failed;
    int rc=sceAudioOutInit();
    if(rc && (uint32_t)rc!=ORBIS_AUDIO_OUT_ERROR_ALREADY_INIT) {failed=rc;}
    else {
        port=sceAudioOutOpen(0xff,ORBIS_AUDIO_OUT_PORT_TYPE_MAIN,0,PW_WINE_AUDIO_GRAIN,PW_WINE_AUDIO_RATE,
                             ORBIS_AUDIO_OUT_PARAM_FORMAT_S16_STEREO);
        if(port<0) {failed=port;port=-1;}
        else {
            int32_t volume[8]={32768,32768,32768,32768,32768,32768,32768,32768};
            int vrc=sceAudioOutSetVolume(port,(1<<0)|(1<<1),volume);
            if(vrc<0) {sceAudioOutClose(port);port=-1;failed=vrc;}
        }
    }
    fprintf(stderr,"PWAUDIO open init=%08x port=%d failed=%08x\n",(unsigned)rc,port,(unsigned)failed);
    return port>=0?0:failed;
}

int pw_wine_audio_available(void)
{
    pthread_mutex_lock(&lock);
    int ok=!open_port();
    pthread_mutex_unlock(&lock);
    return ok;
}

int pw_wine_audio_output(const int16_t *frames)
{
    pthread_mutex_lock(&lock);
    int rc=open_port();
    int current=port;
    pthread_mutex_unlock(&lock);
    if(rc) return rc;
    /* the signal level, as for DOS (W113): tells silence from output loss */
    for(unsigned i=0;i<2*PW_WINE_AUDIO_GRAIN;i++) {
        int v=frames[i];unsigned a=(unsigned)(v<0?-v:v);
        if(a){nonzero++;if(a>peak)peak=a;}
    }
    rc=sceAudioOutOutput(current,frames);
    /* alpha-1: a failing port fails every 5.3 ms grain; the first 8 failures, then every 1000th, always (returned too) */
    if(rc<0) {
        static unsigned failures;
        if(failures++<8 || !(failures%1000))
            fprintf(stderr,"PWAUDIO output rc=%08x grains=%llu failures=%u\n",(unsigned)rc,(unsigned long long)grains,failures);
        return rc;
    }
    if(++grains%938==0 && pw_trace_on()) {  /* the level every ~5 s: traces only (pw_trace.h) */
        fprintf(stderr,"PWAUDIO level grains=%llu nonzero=%llu peak=%u\n",(unsigned long long)grains,(unsigned long long)nonzero,peak);
        peak=0;
    }
    return 0;
}
