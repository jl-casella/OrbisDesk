/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * alpha-1: an AVI splitter for 32-bit DirectShow (MEDIASUBTYPE_Avi), in pwmpeg1.ax.
 *
 * Warcraft III 1.07's movies (Movies\*.mpq) are AVI files: DivX video and MP3 audio. Game.dll
 * plays them with IGraphBuilder::RenderFile, and Windows' built-in AVI Splitter splits them for
 * the game's own DivX decoder (blizzard.ax, registered by War3.exe) and for the MPEG Layer-3 ACM
 * codec (ACM Wrapper). The pinned Wine has its AVI splitter only in winegstreamer, which needs
 * GStreamer; the PS4 has none, RenderFile failed, and Game.dll, which does not check its result,
 * read through the NULL graph on its first timer tick (run-0187).
 *
 * Like Windows' splitter this filter does not decode: it reads the RIFF/AVI headers and the
 * idx1 index (or walks the movi list when there is none) through quartz's File Source
 * (IAsyncReader), and offers each video and audio stream on its own output pin ("Stream 00"...)
 * with the stream's own format: video as FORMAT_VideoInfo with the strf BITMAPINFOHEADER and
 * the biCompression FOURCC as subtype, audio as FORMAT_WaveFormatEx with the strf WAVEFORMATEX
 * and the wFormatTag subtype. Each pin delivers its chunks with stream times from strh
 * dwScale/dwRate on its own thread, as pwmpeg1.c does, so neither renderer waits on the other.
 * Not handled: OpenDML (AVIX, indx) beyond the first RIFF, palette changes, seeking.
 */
#define COBJMACROS
#include "dshow.h"
#include "mmreg.h"
#include "wine/strmbase.h"
#include "wine/debug.h"

WINE_DEFAULT_DEBUG_CHANNEL(quartz);

/* {d1abd1fc-1295-47e2-a8fc-65868f9c0c90} */
const GUID CLSID_PWAviSplitter = {0xd1abd1fc, 0x1295, 0x47e2, {0xa8, 0xfc, 0x65, 0x86, 0x8f, 0x9c, 0x0c, 0x90}};

#define AVI_MAX_STREAMS 4
#define AVI_KEYFRAME 0x10   /* AVIIF_KEYFRAME */
#define AVI_LIST 0x1        /* AVIIF_LIST */

#define FCC(a, b, c, d) ((DWORD)(BYTE)(a) | ((DWORD)(BYTE)(b) << 8) | ((DWORD)(BYTE)(c) << 16) | ((DWORD)(BYTE)(d) << 24))

struct chunk
{
    LONGLONG offset;    /* of the data, past the chunk header */
    DWORD size, flags;
};

struct avi_filter;

struct avi_stream
{
    struct strmbase_source pin;
    struct avi_filter *filter;
    unsigned int number;          /* the NN of the stream's NNdc/NNwb chunks */
    BOOL video;
    AM_MEDIA_TYPE mt;
    DWORD scale, rate, start, length, sample_size;
    struct chunk *chunks;
    unsigned int count, capacity;
    DWORD max_size;
    HANDLE thread;
    SourceSeeking seek;           /* duration and stop only: the graph's position and EC_COMPLETE use them */
};

struct avi_filter
{
    struct strmbase_filter filter;
    struct strmbase_sink sink;
    struct avi_stream streams[AVI_MAX_STREAMS];
    unsigned int stream_count;    /* pins in use: streams[0 .. stream_count - 1] */
    IAsyncReader *reader;
    LONGLONG size;
    BOOL indexed;
    volatile LONG stopping;
};

static inline struct avi_filter *impl_from_strmbase_filter(struct strmbase_filter *iface)
{
    return CONTAINING_RECORD(iface, struct avi_filter, filter);
}

static inline struct avi_stream *impl_from_source(struct strmbase_source *iface)
{
    return CONTAINING_RECORD(iface, struct avi_stream, pin);
}

static BOOL read_at(struct avi_filter *filter, LONGLONG pos, LONG size, void *buffer)
{
    if (pos < 0 || size < 0 || pos + size > filter->size) return FALSE;
    return IAsyncReader_SyncRead(filter->reader, pos, size, buffer) == S_OK;
}

static REFERENCE_TIME stream_time(const struct avi_stream *stream, LONGLONG units)
{
    return stream->rate ? units * stream->scale * 10000000 / stream->rate : 0;
}

/* ---- headers ---- */

static void clear_streams(struct avi_filter *filter)
{
    unsigned int i;

    for (i = 0; i < AVI_MAX_STREAMS; i++)
    {
        struct avi_stream *stream = &filter->streams[i];

        FreeMediaType(&stream->mt);
        memset(&stream->mt, 0, sizeof(stream->mt));
        free(stream->chunks);
        stream->chunks = NULL;
        stream->count = stream->capacity = stream->max_size = 0;
    }
    filter->stream_count = 0;
    filter->indexed = FALSE;
}

static struct avi_stream *stream_by_number(struct avi_filter *filter, unsigned int number)
{
    unsigned int i;

    for (i = 0; i < filter->stream_count; i++)
        if (filter->streams[i].number == number) return &filter->streams[i];
    return NULL;
}

static GUID fourcc_subtype(DWORD fourcc)
{
    GUID subtype = MEDIASUBTYPE_PCM;   /* {XXXXXXXX-0000-0010-8000-00AA00389B71} */

    subtype.Data1 = fourcc;
    return subtype;
}

static BOOL video_type(struct avi_stream *stream, const BYTE *strf, DWORD size)
{
    const BITMAPINFOHEADER *bih = (const BITMAPINFOHEADER *)strf;
    DWORD length = offsetof(VIDEOINFOHEADER, bmiHeader) + size;
    VIDEOINFOHEADER *format;

    if (size < sizeof(BITMAPINFOHEADER) || bih->biWidth <= 0 || !bih->biHeight) return FALSE;
    if (!(format = CoTaskMemAlloc(length))) return FALSE;
    memset(format, 0, length);
    memcpy(&format->bmiHeader, strf, size);
    if (stream->rate) format->AvgTimePerFrame = stream_time(stream, 1);

    stream->mt.majortype = MEDIATYPE_Video;
    if (bih->biCompression == BI_RGB)
    {
        switch (bih->biBitCount)
        {
        case 8: stream->mt.subtype = MEDIASUBTYPE_RGB8; break;
        case 16: stream->mt.subtype = MEDIASUBTYPE_RGB555; break;
        case 24: stream->mt.subtype = MEDIASUBTYPE_RGB24; break;
        case 32: stream->mt.subtype = MEDIASUBTYPE_RGB32; break;
        default: CoTaskMemFree(format); return FALSE;
        }
        stream->mt.bFixedSizeSamples = TRUE;
        stream->mt.lSampleSize = bih->biSizeImage;
    }
    else
    {
        stream->mt.subtype = fourcc_subtype(bih->biCompression);
        stream->mt.bTemporalCompression = TRUE;
    }
    stream->mt.formattype = FORMAT_VideoInfo;
    stream->mt.cbFormat = length;
    stream->mt.pbFormat = (BYTE *)format;
    return TRUE;
}

static BOOL audio_type(struct avi_stream *stream, const BYTE *strf, DWORD size)
{
    DWORD length = max(size, sizeof(WAVEFORMATEX));
    WAVEFORMATEX *format;

    if (size < sizeof(PCMWAVEFORMAT)) return FALSE;
    if (!(format = CoTaskMemAlloc(length))) return FALSE;
    memset(format, 0, length);
    memcpy(format, strf, size);
    if (size < sizeof(WAVEFORMATEX)) format->cbSize = 0;
    else if (format->cbSize > size - sizeof(WAVEFORMATEX)) format->cbSize = size - sizeof(WAVEFORMATEX);
    if (!format->nSamplesPerSec || !format->nChannels)
    {
        CoTaskMemFree(format);
        return FALSE;
    }

    stream->mt.majortype = MEDIATYPE_Audio;
    stream->mt.subtype = fourcc_subtype(format->wFormatTag);
    stream->mt.bFixedSizeSamples = TRUE;
    stream->mt.lSampleSize = max(format->nBlockAlign, 1);
    stream->mt.formattype = FORMAT_WaveFormatEx;
    stream->mt.cbFormat = length;
    stream->mt.pbFormat = (BYTE *)format;
    return TRUE;
}

/* one LIST strl: strh, then strf */
static void parse_strl(struct avi_filter *filter, LONGLONG pos, LONGLONG end, unsigned int number)
{
    BYTE strh[56] = {0}, *strf = NULL;
    DWORD strh_size = 0, strf_size = 0, header[2];
    struct avi_stream *stream;
    DWORD type;

    while (pos + 8 <= end && read_at(filter, pos, 8, header))
    {
        if (header[0] == FCC('s','t','r','h'))
        {
            strh_size = min(header[1], sizeof(strh));
            if (!read_at(filter, pos + 8, strh_size, strh)) strh_size = 0;
        }
        else if (header[0] == FCC('s','t','r','f') && !strf && header[1] && header[1] < 0x10000)
        {
            if ((strf = malloc(header[1])) && read_at(filter, pos + 8, header[1], strf)) strf_size = header[1];
        }
        pos += 8 + header[1] + (header[1] & 1);
    }

    type = *(DWORD *)strh;
    if (strh_size < 48 || !strf_size || (type != FCC('v','i','d','s') && type != FCC('a','u','d','s')))
    {
        ERR("PWAVI stream %u not offered type=%s strh=%lu strf=%lu\n", number,
            debugstr_fourcc(type), strh_size, strf_size);
        free(strf);
        return;
    }
    if (filter->stream_count == AVI_MAX_STREAMS)
    {
        ERR("PWAVI stream %u not offered: more than %u streams\n", number, AVI_MAX_STREAMS);
        free(strf);
        return;
    }
    stream = &filter->streams[filter->stream_count];
    stream->number = number;
    stream->video = type == FCC('v','i','d','s');
    stream->scale = *(DWORD *)(strh + 20);
    stream->rate = *(DWORD *)(strh + 24);
    stream->start = *(DWORD *)(strh + 28);
    stream->length = *(DWORD *)(strh + 32);
    stream->sample_size = *(DWORD *)(strh + 44);
    memset(&stream->mt, 0, sizeof(stream->mt));
    if (!stream->scale || !stream->rate
            || !(stream->video ? video_type(stream, strf, strf_size) : audio_type(stream, strf, strf_size)))
    {
        ERR("PWAVI stream %u not offered: bad format scale=%lu rate=%lu strf=%lu\n", number,
            stream->scale, stream->rate, strf_size);
        memset(&stream->mt, 0, sizeof(stream->mt));
        free(strf);
        return;
    }
    free(strf);
    EnterCriticalSection(&stream->seek.cs);
    stream->seek.llCurrent = 0;
    stream->seek.llDuration = stream->seek.llStop = stream_time(stream, (LONGLONG)stream->start + stream->length);
    LeaveCriticalSection(&stream->seek.cs);
    swprintf(stream->pin.pin.name, ARRAY_SIZE(stream->pin.pin.name), L"Stream %02u", number);
    swprintf(stream->pin.pin.id, ARRAY_SIZE(stream->pin.pin.id), L"Stream %02u", number);
    filter->stream_count++;
}

static void parse_hdrl(struct avi_filter *filter, LONGLONG pos, LONGLONG end)
{
    unsigned int number = 0;
    DWORD header[3];

    while (pos + 8 <= end && read_at(filter, pos, 12, header))
    {
        if (header[0] == FCC('L','I','S','T') && header[2] == FCC('s','t','r','l'))
            parse_strl(filter, pos + 12, min(end, pos + 8 + header[1]), number++);
        pos += 8 + header[1] + (header[1] & 1);
    }
}

static BOOL add_chunk(struct avi_stream *stream, LONGLONG offset, DWORD size, DWORD flags)
{
    if (stream->count == stream->capacity)
    {
        unsigned int capacity = max(stream->capacity * 2, 256);
        struct chunk *chunks = realloc(stream->chunks, capacity * sizeof(*chunks));

        if (!chunks) return FALSE;
        stream->chunks = chunks;
        stream->capacity = capacity;
    }
    stream->chunks[stream->count].offset = offset;
    stream->chunks[stream->count].size = size;
    stream->chunks[stream->count].flags = flags;
    stream->count++;
    stream->max_size = max(stream->max_size, size);
    return TRUE;
}

/* the stream of a chunk id "NNdc", "NNdb", "NNwb" (not "NNpc", palette changes) */
static struct avi_stream *chunk_stream(struct avi_filter *filter, DWORD id)
{
    BYTE c0 = id, c1 = id >> 8, c2 = id >> 16, c3 = id >> 24;

    if (c0 < '0' || c0 > '9' || c1 < '0' || c1 > '9') return NULL;
    if (!((c2 == 'd' && (c3 == 'c' || c3 == 'b')) || (c2 == 'w' && c3 == 'b'))) return NULL;
    return stream_by_number(filter, (c0 - '0') * 10 + (c1 - '0'));
}

static BOOL read_idx1(struct avi_filter *filter, LONGLONG pos, DWORD size, LONGLONG movi)
{
    DWORD count = size / 16, i, check[2], *entries;
    LONGLONG base = movi;   /* offsets count from the "movi" fourcc; some writers use file offsets */
    struct avi_stream *stream;

    if (!count || !(entries = malloc(count * 16))) return FALSE;
    if (!read_at(filter, pos, count * 16, entries))
    {
        free(entries);
        return FALSE;
    }
    for (i = 0; i < count; i++)
        if (!(entries[i * 4 + 1] & AVI_LIST)) break;
    if (i < count && (!read_at(filter, base + entries[i * 4 + 2], 8, check) || check[0] != entries[i * 4]))
    {
        base = 0;
        if (!read_at(filter, entries[i * 4 + 2], 8, check) || check[0] != entries[i * 4])
        {
            ERR("PWAVI idx1 offsets match neither the movi list nor the file, walking movi\n");
            free(entries);
            return FALSE;
        }
    }
    for (i = 0; i < count; i++)
    {
        DWORD *entry = entries + i * 4;

        if ((entry[1] & AVI_LIST) || !(stream = chunk_stream(filter, entry[0]))) continue;
        if (!add_chunk(stream, base + entry[2] + 8, entry[3], entry[1]))
        {
            free(entries);
            return FALSE;
        }
    }
    free(entries);
    return TRUE;
}

static BOOL walk_movi(struct avi_filter *filter, LONGLONG pos, LONGLONG end)
{
    struct avi_stream *stream;
    DWORD header[3];

    while (pos + 8 <= end && read_at(filter, pos, 8, header))
    {
        if (header[0] == FCC('L','I','S','T'))
        {
            pos += 12;   /* into LIST rec */
            continue;
        }
        if ((stream = chunk_stream(filter, header[0]))
                && !add_chunk(stream, pos + 8, header[1], AVI_KEYFRAME))
            return FALSE;
        pos += 8 + header[1] + (header[1] & 1);
    }
    return TRUE;
}

static HRESULT parse_avi(struct avi_filter *filter)
{
    LONGLONG pos = 12, end, movi = 0, movi_end = 0, idx1 = 0;
    DWORD header[3], idx1_size = 0;
    unsigned int i;

    if (!read_at(filter, 0, 12, header) || header[0] != FCC('R','I','F','F') || header[2] != FCC('A','V','I',' '))
        return VFW_E_INVALID_FILE_FORMAT;
    end = min(filter->size, 8 + (LONGLONG)header[1]);
    while (pos + 8 <= end && read_at(filter, pos, 8, header))
    {
        if (header[0] == FCC('L','I','S','T') && read_at(filter, pos + 8, 4, &header[2]))
        {
            if (header[2] == FCC('h','d','r','l')) parse_hdrl(filter, pos + 12, min(end, pos + 8 + header[1]));
            else if (header[2] == FCC('m','o','v','i'))
            {
                movi = pos + 8;
                movi_end = min(end, pos + 8 + header[1]);
            }
        }
        else if (header[0] == FCC('i','d','x','1'))
        {
            idx1 = pos + 8;
            idx1_size = header[1];
        }
        pos += 8 + header[1] + (header[1] & 1);
    }
    if (pos + 12 <= filter->size && read_at(filter, pos, 12, header) && header[0] == FCC('R','I','F','F'))
        ERR("PWAVI OpenDML continuation at %s not read: playback ends with the first RIFF\n",
            wine_dbgstr_longlong(pos));
    if (!filter->stream_count || !movi) return VFW_E_INVALID_FILE_FORMAT;

    filter->indexed = idx1 && read_idx1(filter, idx1, idx1_size, movi);
    if (!filter->indexed)
    {
        for (i = 0; i < filter->stream_count; i++) filter->streams[i].count = filter->streams[i].max_size = 0;
        if (!walk_movi(filter, movi + 4, movi_end)) return E_OUTOFMEMORY;
    }
    for (i = 0; i < filter->stream_count; i++)
    {
        struct avi_stream *stream = &filter->streams[i];

        ERR("PWAVI stream %u %s subtype=%s scale=%lu rate=%lu start=%lu length=%lu sample_size=%lu chunks=%u max=%lu\n",
            stream->number, stream->video ? "video" : "audio", debugstr_guid(&stream->mt.subtype), stream->scale,
            stream->rate, stream->start, stream->length, stream->sample_size, stream->count, stream->max_size);
    }
    return S_OK;
}

/* ---- output pins ---- */

/* IMediaSeeking on each output pin, as Windows' splitter has, for the duration and stop position: without
 * them quartz's graph keeps its position at 0 (filtergraph.c clamps it to the stop it could not get), and
 * Game.dll reads that position on every timer tick. Seeking itself is not offered: a run starts at 0. */
static inline struct avi_stream *impl_from_IMediaSeeking(IMediaSeeking *iface)
{
    return CONTAINING_RECORD(iface, struct avi_stream, seek.IMediaSeeking_iface);
}

static HRESULT WINAPI seeking_QueryInterface(IMediaSeeking *iface, REFIID iid, void **out)
{
    return IPin_QueryInterface(&impl_from_IMediaSeeking(iface)->pin.pin.IPin_iface, iid, out);
}

static ULONG WINAPI seeking_AddRef(IMediaSeeking *iface)
{
    return IPin_AddRef(&impl_from_IMediaSeeking(iface)->pin.pin.IPin_iface);
}

static ULONG WINAPI seeking_Release(IMediaSeeking *iface)
{
    return IPin_Release(&impl_from_IMediaSeeking(iface)->pin.pin.IPin_iface);
}

static HRESULT WINAPI seeking_change(IMediaSeeking *iface)
{
    return S_OK;
}

static const IMediaSeekingVtbl seeking_vtbl =
{
    seeking_QueryInterface,
    seeking_AddRef,
    seeking_Release,
    SourceSeekingImpl_GetCapabilities,
    SourceSeekingImpl_CheckCapabilities,
    SourceSeekingImpl_IsFormatSupported,
    SourceSeekingImpl_QueryPreferredFormat,
    SourceSeekingImpl_GetTimeFormat,
    SourceSeekingImpl_IsUsingTimeFormat,
    SourceSeekingImpl_SetTimeFormat,
    SourceSeekingImpl_GetDuration,
    SourceSeekingImpl_GetStopPosition,
    SourceSeekingImpl_GetCurrentPosition,
    SourceSeekingImpl_ConvertTimeFormat,
    SourceSeekingImpl_SetPositions,
    SourceSeekingImpl_GetPositions,
    SourceSeekingImpl_GetAvailable,
    SourceSeekingImpl_SetRate,
    SourceSeekingImpl_GetRate,
    SourceSeekingImpl_GetPreroll,
};

static HRESULT source_query_interface(struct strmbase_pin *iface, REFIID iid, void **out)
{
    struct avi_stream *stream = impl_from_source(CONTAINING_RECORD(iface, struct strmbase_source, pin));

    if (!IsEqualGUID(iid, &IID_IMediaSeeking)) return E_NOINTERFACE;
    *out = &stream->seek.IMediaSeeking_iface;
    IMediaSeeking_AddRef(&stream->seek.IMediaSeeking_iface);
    return S_OK;
}

static HRESULT source_query_accept(struct strmbase_pin *iface, const AM_MEDIA_TYPE *mt)
{
    struct avi_stream *stream = impl_from_source(CONTAINING_RECORD(iface, struct strmbase_source, pin));

    return IsEqualGUID(&mt->majortype, &stream->mt.majortype) && IsEqualGUID(&mt->subtype, &stream->mt.subtype)
            ? S_OK : S_FALSE;
}

static HRESULT source_get_media_type(struct strmbase_pin *iface, unsigned int index, AM_MEDIA_TYPE *mt)
{
    struct avi_stream *stream = impl_from_source(CONTAINING_RECORD(iface, struct strmbase_source, pin));

    if (index) return VFW_S_NO_MORE_ITEMS;
    return CopyMediaType(mt, &stream->mt);
}

static HRESULT WINAPI source_decide_buffer_size(struct strmbase_source *iface,
        IMemAllocator *allocator, ALLOCATOR_PROPERTIES *props)
{
    struct avi_stream *stream = impl_from_source(iface);
    ALLOCATOR_PROPERTIES actual;

    props->cBuffers = max(props->cBuffers, stream->video ? 4 : 16);
    props->cbBuffer = max(props->cbBuffer, (LONG)max(stream->max_size, 1));
    props->cbAlign = max(props->cbAlign, 1);
    return IMemAllocator_SetProperties(allocator, props, &actual);
}

static const struct strmbase_source_ops source_ops =
{
    .base.pin_query_accept = source_query_accept,
    .base.pin_get_media_type = source_get_media_type,
    .base.pin_query_interface = source_query_interface,
    .pfnAttemptConnection = BaseOutputPinImpl_AttemptConnection,
    .pfnDecideAllocator = BaseOutputPinImpl_DecideAllocator,
    .pfnDecideBufferSize = source_decide_buffer_size,
};

/* ---- streaming ---- */

static DWORD WINAPI stream_thread(void *arg)
{
    struct avi_stream *stream = arg;
    struct avi_filter *filter = stream->filter;
    LONGLONG units = stream->start;   /* frames, blocks, or samples for a stream with a sample size */
    unsigned int i, delivered = 0;
    HRESULT hr = S_OK;

    IPin_NewSegment(stream->pin.pin.peer, 0, stream_time(stream, (LONGLONG)stream->start + stream->length), 1.0);
    for (i = 0; i < stream->count && !filter->stopping; i++)
    {
        const struct chunk *chunk = &stream->chunks[i];
        LONGLONG next = units + (stream->sample_size ? chunk->size / stream->sample_size : 1);
        REFERENCE_TIME start = stream_time(stream, units), stop = stream_time(stream, next);
        IMediaSample *sample;
        BYTE *data;

        units = next;
        if (!chunk->size) continue;   /* a dropped video frame: its time passes */
        if (FAILED(hr = IMemAllocator_GetBuffer(stream->pin.pAllocator, &sample, NULL, NULL, 0))) break;
        if (IMediaSample_GetSize(sample) < (LONG)chunk->size)
        {
            ERR("PWAVI stream %u chunk %u of %lu bytes exceeds the %ld byte buffer\n", stream->number, i,
                chunk->size, IMediaSample_GetSize(sample));
            IMediaSample_Release(sample);
            hr = E_FAIL;
            break;
        }
        IMediaSample_GetPointer(sample, &data);
        if (IAsyncReader_SyncRead(filter->reader, chunk->offset, chunk->size, data) != S_OK)
        {
            ERR("PWAVI stream %u chunk %u at %s unreadable\n", stream->number, i, wine_dbgstr_longlong(chunk->offset));
            IMediaSample_Release(sample);
            break;   /* a truncated file ends the stream */
        }
        IMediaSample_SetActualDataLength(sample, chunk->size);
        IMediaSample_SetTime(sample, &start, &stop);
        IMediaSample_SetSyncPoint(sample, !stream->video || (chunk->flags & AVI_KEYFRAME));
        IMediaSample_SetDiscontinuity(sample, !delivered);
        hr = IMemInputPin_Receive(stream->pin.pMemInputPin, sample);
        IMediaSample_Release(sample);
        if (!delivered++) ERR("PWAVI stream %u first_sample hr=%#lx\n", stream->number, hr);
        if (hr != S_OK) break;
    }

    if (!filter->stopping && hr == S_OK)
    {
        IPin_EndOfStream(stream->pin.pin.peer);
        ERR("PWAVI stream %u eos samples=%u\n", stream->number, delivered);
    }
    else
        ERR("PWAVI stream %u stopped samples=%u hr=%#lx\n", stream->number, delivered, hr);
    return 0;
}

/* ---- input pin ---- */

static HRESULT sink_query_accept(struct strmbase_pin *iface, const AM_MEDIA_TYPE *mt)
{
    return IsEqualGUID(&mt->majortype, &MEDIATYPE_Stream) && IsEqualGUID(&mt->subtype, &MEDIASUBTYPE_Avi) ? S_OK : S_FALSE;
}

static HRESULT sink_get_media_type(struct strmbase_pin *iface, unsigned int index, AM_MEDIA_TYPE *mt)
{
    return VFW_S_NO_MORE_ITEMS;
}

static HRESULT sink_connect(struct strmbase_sink *iface, IPin *peer, const AM_MEDIA_TYPE *mt)
{
    struct avi_filter *filter = impl_from_strmbase_filter(iface->pin.filter);
    LONGLONG available;
    HRESULT hr;

    if (FAILED(hr = IPin_QueryInterface(peer, &IID_IAsyncReader, (void **)&filter->reader)))
        return hr;
    if (FAILED(hr = IAsyncReader_Length(filter->reader, &filter->size, &available)) || FAILED(hr = parse_avi(filter)))
    {
        ERR("PWAVI reject size=%s hr=%#lx streams=%u\n", wine_dbgstr_longlong(filter->size), hr, filter->stream_count);
        clear_streams(filter);
        IAsyncReader_Release(filter->reader);
        filter->reader = NULL;
        return VFW_E_TYPE_NOT_ACCEPTED;
    }
    ERR("PWAVI open size=%s streams=%u indexed=%d\n", wine_dbgstr_longlong(filter->size), filter->stream_count,
        filter->indexed);
    BaseFilterImpl_IncrementPinVersion(&filter->filter);
    return S_OK;
}

static void sink_disconnect(struct strmbase_sink *iface)
{
    struct avi_filter *filter = impl_from_strmbase_filter(iface->pin.filter);

    if (filter->reader) IAsyncReader_Release(filter->reader);
    filter->reader = NULL;
    clear_streams(filter);
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
    struct avi_filter *filter = impl_from_strmbase_filter(iface);

    if (!index) return &filter->sink.pin;
    if (index <= filter->stream_count) return &filter->streams[index - 1].pin.pin;
    return NULL;
}

static void filter_destroy(struct strmbase_filter *iface)
{
    struct avi_filter *filter = impl_from_strmbase_filter(iface);
    unsigned int i;

    if (filter->sink.pin.peer)
    {
        IPin_Disconnect(filter->sink.pin.peer);
        IPin_Disconnect(&filter->sink.pin.IPin_iface);
    }
    for (i = 0; i < AVI_MAX_STREAMS; i++)
    {
        struct avi_stream *stream = &filter->streams[i];

        if (stream->pin.pin.peer)
        {
            IPin_Disconnect(stream->pin.pin.peer);
            IPin_Disconnect(&stream->pin.pin.IPin_iface);
        }
        strmbase_source_cleanup(&stream->pin);
        strmbase_seeking_cleanup(&stream->seek);
    }
    if (filter->reader) IAsyncReader_Release(filter->reader);
    filter->reader = NULL;
    clear_streams(filter);
    strmbase_sink_cleanup(&filter->sink);
    strmbase_filter_cleanup(&filter->filter);
    free(filter);
}

static HRESULT filter_init_stream(struct strmbase_filter *iface)
{
    struct avi_filter *filter = impl_from_strmbase_filter(iface);
    unsigned int i;
    HRESULT hr;

    if (!filter->reader) return S_OK;
    filter->stopping = 0;
    for (i = 0; i < filter->stream_count; i++)
    {
        struct avi_stream *stream = &filter->streams[i];

        if (!stream->pin.pin.peer) continue;
        if (FAILED(hr = IMemAllocator_Commit(stream->pin.pAllocator))) return hr;
        if (!(stream->thread = CreateThread(NULL, 0, stream_thread, stream, 0, NULL)))
            return HRESULT_FROM_WIN32(GetLastError());
    }
    return S_OK;
}

static HRESULT filter_cleanup_stream(struct strmbase_filter *iface)
{
    struct avi_filter *filter = impl_from_strmbase_filter(iface);
    unsigned int i;

    InterlockedExchange(&filter->stopping, 1);
    for (i = 0; i < filter->stream_count; i++)
    {
        struct avi_stream *stream = &filter->streams[i];

        if (!stream->pin.pin.peer) continue;
        IMemAllocator_Decommit(stream->pin.pAllocator);
        if (stream->thread)
        {
            WaitForSingleObject(stream->thread, INFINITE);
            CloseHandle(stream->thread);
            stream->thread = NULL;
        }
    }
    return S_OK;
}

static const struct strmbase_filter_ops filter_ops =
{
    .filter_get_pin = filter_get_pin,
    .filter_destroy = filter_destroy,
    .filter_init_stream = filter_init_stream,
    .filter_cleanup_stream = filter_cleanup_stream,
};

HRESULT pwavi_create(IUnknown *outer, IUnknown **out)
{
    struct avi_filter *filter;
    unsigned int i;

    if (!(filter = calloc(1, sizeof(*filter)))) return E_OUTOFMEMORY;
    strmbase_filter_init(&filter->filter, outer, &CLSID_PWAviSplitter, &filter_ops);
    strmbase_sink_init(&filter->sink, &filter->filter, L"input pin", &sink_ops, NULL);
    for (i = 0; i < AVI_MAX_STREAMS; i++)
    {
        strmbase_source_init(&filter->streams[i].pin, &filter->filter, L"Stream", &source_ops);
        strmbase_seeking_init(&filter->streams[i].seek, &seeking_vtbl, seeking_change, seeking_change, seeking_change);
        filter->streams[i].seek.dwCapabilities = AM_SEEKING_CanGetStopPos | AM_SEEKING_CanGetDuration;
        filter->streams[i].filter = filter;
    }
    *out = &filter->filter.IUnknown_inner;
    return S_OK;
}
