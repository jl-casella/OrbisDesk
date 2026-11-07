/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pw_dos_audio.h"
#include <orbis/AudioOut.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
static pthread_mutex_t audio_lock=PTHREAD_MUTEX_INITIALIZER;
static int port=-1;
static uint64_t generation,blocks,nonzero,frames_in;
static unsigned peak,interval_peak;
static unsigned used,phase,rate;
static int16_t pcm[256*2] __attribute__((aligned(16)));

uint32_t pw_dos_audio_query(void *data,uint32_t bytes,uint32_t *returned)
{
    struct pw_dos_audio_packet *p=data;
    if(returned)*returned=sizeof(*p);
    if(bytes!=sizeof(*p))return 0xc0000004u;
    if(!p)return 0xc0000005u;
    if(p->size!=sizeof(*p)||p->version!=1)return 0xc000000du;
    pthread_mutex_lock(&audio_lock);p->status=0;
    if(p->action==PW_DOS_AUDIO_OPEN) {
        if(port>=0)p->status=-EBUSY;
        else if(p->sample_rate<8000||p->sample_rate>96000)p->status=-EINVAL;
        else {
            int rc=sceAudioOutInit();
            fprintf(stderr,"PWDOSAUDIO init rc=%08x\n",(unsigned)rc);
            if(rc && (uint32_t)rc!=ORBIS_AUDIO_OUT_ERROR_ALREADY_INIT)p->status=rc;
            else {
                port=sceAudioOutOpen(0xff,ORBIS_AUDIO_OUT_PORT_TYPE_MAIN,0,256,48000,ORBIS_AUDIO_OUT_PARAM_FORMAT_S16_STEREO);
                if(port<0)p->status=port;
                else {
                    /* W113: explicit 0 dB on both channels instead of relying on the port default. */
                    int32_t volume[8]={32768,32768,32768,32768,32768,32768,32768,32768};
                    int vrc=sceAudioOutSetVolume(port,(1<<0)|(1<<1),volume);
                    fprintf(stderr,"PWDOSAUDIO volume port=%d rc=%08x\n",port,(unsigned)vrc);
                    if(vrc<0){sceAudioOutClose(port);port=-1;p->status=vrc;}
                    else {rate=p->sample_rate;used=phase=0;blocks=nonzero=frames_in=0;peak=interval_peak=0;p->token=++generation;}
                }
            }
        }
        fprintf(stderr,"PWDOSAUDIO open source_rate=%u port=%d status=%08x token=%llu\n",p->sample_rate,port,(unsigned)p->status,(unsigned long long)p->token);
    } else if(port<0||p->token!=generation)p->status=-EINVAL;
    else if(p->action==PW_DOS_AUDIO_SUBMIT) {
        if(!p->pcm||!p->frames||p->frames>8192||p->sample_rate!=rate)p->status=-EINVAL;
        else {
            const int16_t *src=(const int16_t *)(uintptr_t)p->pcm;
            /* Continuous rational sample-and-hold conversion to the port's 48kHz.
             * The kernel consumes real 256-frame stereo blocks; no new worker. */
            for(unsigned i=0;i<p->frames && !p->status;++i) {
                /* W113: signal level of what the core sends, to tell silence from output loss. */
                for(unsigned c=0;c<2;c++) {
                    int v=src[i*2+c];unsigned a=(unsigned)(v<0?-v:v);
                    if(a){nonzero++;if(a>interval_peak)interval_peak=a;}
                }
                frames_in++;
                phase+=48000;
                while(phase>=rate) {
                    phase-=rate;pcm[used*2]=src[i*2];pcm[used*2+1]=src[i*2+1];
                    if(++used==256) {
                        int rc=sceAudioOutOutput(port,pcm);used=0;
                        if(rc<0){p->status=rc;break;}blocks++;
                        if(blocks%938==0) {
                            fprintf(stderr,"PWDOSAUDIO level blocks=%llu frames_in=%llu nonzero=%llu peak=%u\n",
                                    (unsigned long long)blocks,(unsigned long long)frames_in,(unsigned long long)nonzero,interval_peak);
                            if(interval_peak>peak)peak=interval_peak;
                            interval_peak=0;
                        }
                    }
                }
            }
        }
        if(p->status)fprintf(stderr,"PWDOSAUDIO submit status=%08x\n",(unsigned)p->status);
    } else if(p->action==PW_DOS_AUDIO_CLOSE) {
        if(used){memset(pcm+used*2,0,(256-used)*2*sizeof(*pcm));int rc=sceAudioOutOutput(port,pcm);if(rc<0)p->status=rc;}
        int rc=sceAudioOutClose(port);if(rc<0&&!p->status)p->status=rc;
        if(interval_peak>peak)peak=interval_peak;
        fprintf(stderr,"PWDOSAUDIO close blocks=%llu frames_in=%llu nonzero=%llu peak=%u status=%08x\n",(unsigned long long)blocks,
                (unsigned long long)frames_in,(unsigned long long)nonzero,peak,(unsigned)p->status);
        port=-1;used=phase=0;
    } else p->status=-EINVAL;
    pthread_mutex_unlock(&audio_lock);return 0;
}
