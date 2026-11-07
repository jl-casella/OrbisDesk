/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * W225: a DirectShow filter for MPEG-1 system streams (.mpg), for 32-bit programs.
 *
 * The pinned Wine has its MPEG-1 splitter and decoders only in winegstreamer, which needs
 * GStreamer; the PS4 has none, and GTA Vice City's intro videos (movies/Logo.mpg,
 * GTAtitles.mpg: MPEG-1 video 640x480 at 25 fps, MPEG-1 layer II audio at 48 kHz) did not
 * play. This filter takes the stream from quartz's File Source (Async.) and decodes it with
 * pl_mpeg (MIT, .deps/downloads/pl_mpeg-c871f2be): RGB32 video and 16-bit PCM audio, each on
 * its own pin, thread and pl_mpeg instance, so that neither renderer waits on the other.
 * Anything pl_mpeg cannot decode is refused at connection with a PWMPEG line, as a Windows
 * without the codec refuses it. See docs/investigacion-gta-vc-base-0x400000.md.
 */
#define COBJMACROS
#define PLM_NO_STDIO
#define PL_MPEG_IMPLEMENTATION
#include "pl_mpeg.h"

#include "dshow.h"
#include "wine/strmbase.h"
#include "wine/debug.h"

WINE_DEFAULT_DEBUG_CHANNEL(quartz);

/* {d1abd1fb-1295-47e2-a8fc-65868f9c0c90} */
static const GUID CLSID_PWMpeg1 = {0xd1abd1fb, 0x1295, 0x47e2, {0xa8, 0xfc, 0x65, 0x86, 0x8f, 0x9c, 0x0c, 0x90}};

struct mpeg_filter;

struct stream_pin
{
    struct strmbase_source pin;
    struct mpeg_filter *filter;
    BOOL video;
    HANDLE thread;
};

struct mpeg_filter
{
    struct strmbase_filter filter;
    struct strmbase_sink sink;
    struct stream_pin video, audio;
    IAsyncReader *reader;
    LONGLONG size;
    BOOL has_video, has_audio;
    int width, height, samplerate;
    double framerate, duration;
    volatile LONG stopping;
};

/* pl_mpeg reads the file through the File Source's IAsyncReader */
struct reader
{
    IAsyncReader *reader;
    LONGLONG pos, size;
};

static void reader_load(plm_buffer_t *buffer, void *user)
{
    struct reader *r = user;
    size_t space;
    LONG count;

    if (buffer->discard_read_bytes) plm_buffer_discard_read_bytes(buffer);
    space = buffer->capacity - buffer->length;
    count = (LONG)min((LONGLONG)space, r->size - r->pos);
    if (count <= 0 || FAILED(IAsyncReader_SyncRead(r->reader, r->pos, count, buffer->bytes + buffer->length)))
    {
        buffer->has_ended = TRUE;
        return;
    }
    r->pos += count;
    buffer->length += count;
}

static void reader_seek(plm_buffer_t *buffer, size_t offset, void *user)
{
    struct reader *r = user;
    r->pos = offset;
}

static size_t reader_tell(plm_buffer_t *buffer, void *user)
{
    struct reader *r = user;
    return (size_t)r->pos;
}

static plm_t *open_stream(struct mpeg_filter *filter, struct reader *r)
{
    plm_buffer_t *buffer;

    r->reader = filter->reader;
    r->pos = 0;
    r->size = filter->size;
    if (!(buffer = plm_buffer_create_with_callbacks(reader_load, reader_seek, reader_tell, (size_t)r->size, r)))
        return NULL;
    return plm_create_with_buffer(buffer, TRUE);
}

static inline struct mpeg_filter *impl_from_strmbase_filter(struct strmbase_filter *iface)
{
    return CONTAINING_RECORD(iface, struct mpeg_filter, filter);
}

static inline struct stream_pin *impl_from_source(struct strmbase_source *iface)
{
    return CONTAINING_RECORD(iface, struct stream_pin, pin);
}

/* ---- media types ---- */

static HRESULT video_media_type(struct mpeg_filter *filter, AM_MEDIA_TYPE *mt)
{
    VIDEOINFOHEADER *format;

    if (!(format = CoTaskMemAlloc(sizeof(*format)))) return E_OUTOFMEMORY;
    memset(format, 0, sizeof(*format));
    SetRect(&format->rcSource, 0, 0, filter->width, filter->height);
    format->rcTarget = format->rcSource;
    format->AvgTimePerFrame = (REFERENCE_TIME)(10000000.0 / filter->framerate);
    format->bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    format->bmiHeader.biWidth = filter->width;
    format->bmiHeader.biHeight = filter->height;   /* bottom-up, as BI_RGB DIBs are */
    format->bmiHeader.biPlanes = 1;
    format->bmiHeader.biBitCount = 32;
    format->bmiHeader.biCompression = BI_RGB;
    format->bmiHeader.biSizeImage = filter->width * filter->height * 4;

    memset(mt, 0, sizeof(*mt));
    mt->majortype = MEDIATYPE_Video;
    mt->subtype = MEDIASUBTYPE_RGB32;
    mt->bFixedSizeSamples = TRUE;
    mt->lSampleSize = format->bmiHeader.biSizeImage;
    mt->formattype = FORMAT_VideoInfo;
    mt->cbFormat = sizeof(*format);
    mt->pbFormat = (BYTE *)format;
    return S_OK;
}

static HRESULT audio_media_type(struct mpeg_filter *filter, AM_MEDIA_TYPE *mt)
{
    WAVEFORMATEX *format;

    if (!(format = CoTaskMemAlloc(sizeof(*format)))) return E_OUTOFMEMORY;
    memset(format, 0, sizeof(*format));
    format->wFormatTag = WAVE_FORMAT_PCM;
    format->nChannels = 2;
    format->nSamplesPerSec = filter->samplerate;
    format->wBitsPerSample = 16;
    format->nBlockAlign = 4;
    format->nAvgBytesPerSec = filter->samplerate * 4;

    memset(mt, 0, sizeof(*mt));
    mt->majortype = MEDIATYPE_Audio;
    mt->subtype = MEDIASUBTYPE_PCM;
    mt->bFixedSizeSamples = TRUE;
    mt->lSampleSize = 4;
    mt->formattype = FORMAT_WaveFormatEx;
    mt->cbFormat = sizeof(*format);
    mt->pbFormat = (BYTE *)format;
    return S_OK;
}

/* ---- output pins ---- */

static HRESULT source_query_accept(struct strmbase_pin *iface, const AM_MEDIA_TYPE *mt)
{
    struct stream_pin *pin = impl_from_source(CONTAINING_RECORD(iface, struct strmbase_source, pin));

    if (pin->video)
        return IsEqualGUID(&mt->majortype, &MEDIATYPE_Video) && IsEqualGUID(&mt->subtype, &MEDIASUBTYPE_RGB32) ? S_OK : S_FALSE;
    return IsEqualGUID(&mt->majortype, &MEDIATYPE_Audio) && IsEqualGUID(&mt->subtype, &MEDIASUBTYPE_PCM) ? S_OK : S_FALSE;
}

static HRESULT source_get_media_type(struct strmbase_pin *iface, unsigned int index, AM_MEDIA_TYPE *mt)
{
    struct stream_pin *pin = impl_from_source(CONTAINING_RECORD(iface, struct strmbase_source, pin));

    if (index) return VFW_S_NO_MORE_ITEMS;
    return pin->video ? video_media_type(pin->filter, mt) : audio_media_type(pin->filter, mt);
}

static HRESULT WINAPI source_decide_buffer_size(struct strmbase_source *iface,
        IMemAllocator *allocator, ALLOCATOR_PROPERTIES *props)
{
    struct stream_pin *pin = impl_from_source(iface);
    ALLOCATOR_PROPERTIES actual;

    if (pin->video)
    {
        props->cBuffers = max(props->cBuffers, 2);
        props->cbBuffer = max(props->cbBuffer, pin->filter->width * pin->filter->height * 4);
    }
    else
    {
        props->cBuffers = max(props->cBuffers, 16);
        props->cbBuffer = max(props->cbBuffer, PLM_AUDIO_SAMPLES_PER_FRAME * 4);
    }
    props->cbAlign = max(props->cbAlign, 1);
    return IMemAllocator_SetProperties(allocator, props, &actual);
}

static const struct strmbase_source_ops source_ops =
{
    .base.pin_query_accept = source_query_accept,
    .base.pin_get_media_type = source_get_media_type,
    .pfnAttemptConnection = BaseOutputPinImpl_AttemptConnection,
    .pfnDecideAllocator = BaseOutputPinImpl_DecideAllocator,
    .pfnDecideBufferSize = source_decide_buffer_size,
};

/* ---- streaming ---- */

static HRESULT deliver(struct stream_pin *pin, IMediaSample *sample, REFERENCE_TIME start, REFERENCE_TIME stop)
{
    IMediaSample_SetTime(sample, &start, &stop);
    IMediaSample_SetSyncPoint(sample, TRUE);
    return IMemInputPin_Receive(pin->pin.pMemInputPin, sample);
}

static DWORD WINAPI stream_thread(void *arg)
{
    struct stream_pin *pin = arg;
    struct mpeg_filter *filter = pin->filter;
    const char *what = pin->video ? "video" : "audio";
    unsigned int count = 0;
    struct reader r;
    HRESULT hr = S_OK;
    plm_t *plm;

    if (!(plm = open_stream(filter, &r)))
    {
        ERR("PWMPEG %s open_failed\n", what);
        return 0;
    }
    plm_set_video_enabled(plm, pin->video);
    plm_set_audio_enabled(plm, !pin->video);
    if (!pin->video) plm_set_audio_stream(plm, 0);
    IPin_NewSegment(pin->pin.pin.peer, 0, (REFERENCE_TIME)(filter->duration * 10000000.0), 1.0);

    while (!filter->stopping)
    {
        IMediaSample *sample;
        BYTE *data;

        if (pin->video)
        {
            plm_frame_t *frame = plm_decode_video(plm);
            REFERENCE_TIME start;

            if (!frame) break;
            if (FAILED(hr = IMemAllocator_GetBuffer(pin->pin.pAllocator, &sample, NULL, NULL, 0))) break;
            IMediaSample_GetPointer(sample, &data);
            /* bottom-up rows: the last row first, walking up */
            plm_frame_to_bgra(frame, data + (filter->height - 1) * filter->width * 4, -filter->width * 4);
            IMediaSample_SetActualDataLength(sample, filter->width * filter->height * 4);
            start = (REFERENCE_TIME)(frame->time * 10000000.0);
            hr = deliver(pin, sample, start, start + (REFERENCE_TIME)(10000000.0 / filter->framerate));
        }
        else
        {
            plm_samples_t *samples = plm_decode_audio(plm);
            REFERENCE_TIME start;
            short *pcm;
            unsigned int i;

            if (!samples) break;
            if (FAILED(hr = IMemAllocator_GetBuffer(pin->pin.pAllocator, &sample, NULL, NULL, 0))) break;
            IMediaSample_GetPointer(sample, &data);
            pcm = (short *)data;
            for (i = 0; i < samples->count * 2; i++)
            {
                float v = samples->interleaved[i] * 32767.0f;
                pcm[i] = v > 32767.0f ? 32767 : v < -32768.0f ? -32768 : (short)v;
            }
            IMediaSample_SetActualDataLength(sample, samples->count * 4);
            start = (REFERENCE_TIME)(samples->time * 10000000.0);
            hr = deliver(pin, sample, start, start + (REFERENCE_TIME)samples->count * 10000000 / filter->samplerate);
        }
        IMediaSample_Release(sample);
        if (!count++) ERR("PWMPEG %s first_sample hr=%#lx\n", what, hr);
        if (hr != S_OK) break;
    }

    if (!filter->stopping && hr == S_OK)
    {
        IPin_EndOfStream(pin->pin.pin.peer);
        ERR("PWMPEG %s eos samples=%u\n", what, count);
    }
    else
        ERR("PWMPEG %s stopped samples=%u hr=%#lx\n", what, count, hr);
    plm_destroy(plm);
    return 0;
}

/* ---- input pin ---- */

static HRESULT sink_query_accept(struct strmbase_pin *iface, const AM_MEDIA_TYPE *mt)
{
    return IsEqualGUID(&mt->majortype, &MEDIATYPE_Stream) && IsEqualGUID(&mt->subtype, &MEDIASUBTYPE_MPEG1System) ? S_OK : S_FALSE;
}

static HRESULT sink_get_media_type(struct strmbase_pin *iface, unsigned int index, AM_MEDIA_TYPE *mt)
{
    return VFW_S_NO_MORE_ITEMS;
}

static HRESULT sink_connect(struct strmbase_sink *iface, IPin *peer, const AM_MEDIA_TYPE *mt)
{
    struct mpeg_filter *filter = impl_from_strmbase_filter(iface->pin.filter);
    LONGLONG available;
    struct reader r;
    HRESULT hr;
    plm_t *plm;

    ERR("PWMPEG connect begin filter=%p thread=%04lx\n", filter, GetCurrentThreadId());  /* W256 */
    if (FAILED(hr = IPin_QueryInterface(peer, &IID_IAsyncReader, (void **)&filter->reader)))
        return hr;
    hr = IAsyncReader_Length(filter->reader, &filter->size, &available);
    ERR("PWMPEG connect length hr=%#lx size=%I64d\n", hr, filter->size);  /* W256 */

    if (!(plm = open_stream(filter, &r)) || !plm_has_headers(plm))
    {
        ERR("PWMPEG reject size=%I64d reason=%s\n", filter->size, plm ? "no_mpeg1_headers" : "open_failed");
        if (plm) plm_destroy(plm);
        IAsyncReader_Release(filter->reader);
        filter->reader = NULL;
        return VFW_E_TYPE_NOT_ACCEPTED;
    }
    filter->has_video = plm_get_num_video_streams(plm) > 0 && plm_get_width(plm) > 0;
    filter->has_audio = plm_get_num_audio_streams(plm) > 0 && plm_get_samplerate(plm) > 0;
    filter->width = plm_get_width(plm);
    filter->height = plm_get_height(plm);
    filter->framerate = plm_get_framerate(plm);
    filter->samplerate = plm_get_samplerate(plm);
    filter->duration = plm_get_duration(plm);
    plm_destroy(plm);
    if (filter->has_video && filter->framerate <= 0.0) filter->has_video = FALSE;

    ERR("PWMPEG open size=%I64d video=%d %dx%d fps=%.3f audio=%d rate=%d duration=%.2f\n", filter->size,
            filter->has_video, filter->width, filter->height, filter->framerate, filter->has_audio,
            filter->samplerate, filter->duration);
    if (!filter->has_video && !filter->has_audio)
    {
        IAsyncReader_Release(filter->reader);
        filter->reader = NULL;
        return VFW_E_TYPE_NOT_ACCEPTED;
    }
    BaseFilterImpl_IncrementPinVersion(&filter->filter);
    return S_OK;
}

static void sink_disconnect(struct strmbase_sink *iface)
{
    struct mpeg_filter *filter = impl_from_strmbase_filter(iface->pin.filter);

    if (filter->reader) IAsyncReader_Release(filter->reader);
    filter->reader = NULL;
    filter->has_video = filter->has_audio = FALSE;
    BaseFilterImpl_IncrementPinVersion(&filter->filter);
}

static const struct strmbase_sink_ops sink_ops =
{
    .base.pin_query_accept = sink_query_accept,
    .base.pin_get_media_type = sink_get_media_type,
    .sink_connect = sink_connect,
    .sink_disconnect = sink_disconnect,
};

/* ---- filter ---- */

static struct strmbase_pin *filter_get_pin(struct strmbase_filter *iface, unsigned int index)
{
    struct mpeg_filter *filter = impl_from_strmbase_filter(iface);

    if (!index--) return &filter->sink.pin;
    if (filter->has_video && !index--) return &filter->video.pin.pin;
    if (filter->has_audio && !index--) return &filter->audio.pin.pin;
    return NULL;
}

static void filter_destroy(struct strmbase_filter *iface)
{
    struct mpeg_filter *filter = impl_from_strmbase_filter(iface);

    ERR("PWMPEG destroy filter=%p thread=%04lx\n", filter, GetCurrentThreadId());  /* W256 */
    if (filter->sink.pin.peer)
    {
        IPin_Disconnect(filter->sink.pin.peer);
        IPin_Disconnect(&filter->sink.pin.IPin_iface);
    }
    strmbase_source_cleanup(&filter->video.pin);
    strmbase_source_cleanup(&filter->audio.pin);
    strmbase_sink_cleanup(&filter->sink);
    strmbase_filter_cleanup(&filter->filter);
    free(filter);
}

static HRESULT start_pin(struct stream_pin *pin)
{
    HRESULT hr;

    if (!pin->pin.pin.peer) return S_OK;
    if (FAILED(hr = IMemAllocator_Commit(pin->pin.pAllocator))) return hr;
    if (!(pin->thread = CreateThread(NULL, 0, stream_thread, pin, 0, NULL))) return HRESULT_FROM_WIN32(GetLastError());
    return S_OK;
}

static void stop_pin(struct stream_pin *pin)
{
    if (!pin->pin.pin.peer) return;
    IMemAllocator_Decommit(pin->pin.pAllocator);
    if (pin->thread)
    {
        WaitForSingleObject(pin->thread, INFINITE);
        CloseHandle(pin->thread);
        pin->thread = NULL;
    }
}

static HRESULT filter_init_stream(struct strmbase_filter *iface)
{
    struct mpeg_filter *filter = impl_from_strmbase_filter(iface);
    HRESULT hr;

    ERR("PWMPEG run filter=%p reader=%p thread=%04lx\n", filter, filter->reader, GetCurrentThreadId());  /* W256 */
    if (!filter->reader) return S_OK;
    filter->stopping = 0;
    if (FAILED(hr = start_pin(&filter->video))) return hr;
    return start_pin(&filter->audio);
}

static HRESULT filter_cleanup_stream(struct strmbase_filter *iface)
{
    struct mpeg_filter *filter = impl_from_strmbase_filter(iface);

    ERR("PWMPEG stop filter=%p thread=%04lx\n", filter, GetCurrentThreadId());  /* W256 */
    InterlockedExchange(&filter->stopping, 1);
    stop_pin(&filter->video);
    stop_pin(&filter->audio);
    ERR("PWMPEG stopped filter=%p\n", filter);  /* W256 */
    return S_OK;
}

static const struct strmbase_filter_ops filter_ops =
{
    .filter_get_pin = filter_get_pin,
    .filter_destroy = filter_destroy,
    .filter_init_stream = filter_init_stream,
    .filter_cleanup_stream = filter_cleanup_stream,
};

static HRESULT create_filter(IUnknown *outer, IUnknown **out)
{
    struct mpeg_filter *filter;

    if (!(filter = calloc(1, sizeof(*filter)))) return E_OUTOFMEMORY;
    strmbase_filter_init(&filter->filter, outer, &CLSID_PWMpeg1, &filter_ops);
    strmbase_sink_init(&filter->sink, &filter->filter, L"Input", &sink_ops, NULL);
    strmbase_source_init(&filter->video.pin, &filter->filter, L"Video", &source_ops);
    strmbase_source_init(&filter->audio.pin, &filter->filter, L"Audio", &source_ops);
    filter->video.filter = filter->audio.filter = filter;
    filter->video.video = TRUE;
    *out = &filter->filter.IUnknown_inner;
    ERR("PWMPEG create filter=%p thread=%04lx\n", filter, GetCurrentThreadId());  /* W256 */
    return S_OK;
}

/* ---- class factory ---- */

static HRESULT WINAPI factory_QueryInterface(IClassFactory *iface, REFIID iid, void **out)
{
    if (IsEqualGUID(iid, &IID_IUnknown) || IsEqualGUID(iid, &IID_IClassFactory))
    {
        *out = iface;
        return S_OK;
    }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG WINAPI factory_AddRef(IClassFactory *iface) { return 2; }
static ULONG WINAPI factory_Release(IClassFactory *iface) { return 1; }

static HRESULT WINAPI factory_CreateInstance(IClassFactory *iface, IUnknown *outer, REFIID iid, void **out)
{
    IUnknown *unk;
    HRESULT hr;

    *out = NULL;
    if (outer && !IsEqualGUID(iid, &IID_IUnknown)) return E_NOINTERFACE;
    if (FAILED(hr = create_filter(outer, &unk))) return hr;
    hr = IUnknown_QueryInterface(unk, iid, out);
    IUnknown_Release(unk);
    return hr;
}

static HRESULT WINAPI factory_LockServer(IClassFactory *iface, BOOL lock) { return S_OK; }

static IClassFactoryVtbl factory_vtbl =
{
    factory_QueryInterface, factory_AddRef, factory_Release, factory_CreateInstance, factory_LockServer,
};
static IClassFactory factory = {&factory_vtbl};

HRESULT WINAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void **out)
{
    if (IsEqualGUID(clsid, &CLSID_PWMpeg1)) return IClassFactory_QueryInterface(&factory, iid, out);
    *out = NULL;
    return CLASS_E_CLASSNOTAVAILABLE;
}

HRESULT WINAPI DllCanUnloadNow(void)
{
    return S_FALSE;
}
