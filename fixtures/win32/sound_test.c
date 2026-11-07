/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* W120: plays a 440 Hz tone for two seconds through winmm (waveOut -> mmdevapi -> the
 * console's audio driver) and writes each step's result next to the executable, as
 * sound-result.txt: the tone is heard or not, and the codes say where it stopped. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include <math.h>
#include <stdio.h>

#define RATE 44100
#define SECONDS 2

static short samples[RATE * SECONDS * 2];

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    char path[MAX_PATH], text[512];
    int n = 0;
    DWORD length = GetModuleFileNameA(NULL, path, MAX_PATH), written;
    WAVEFORMATEX format = {WAVE_FORMAT_PCM, 2, RATE, RATE * 4, 4, 16, 0};
    WAVEHDR header = {0};
    HWAVEOUT wave = NULL;
    MMRESULT rc;
    (void)instance; (void)previous; (void)command; (void)show;

    for (int i = 0; i < RATE * SECONDS; i++)
        samples[2 * i] = samples[2 * i + 1] = (short)(12000 * sin(2 * 3.14159265358979 * 440 * i / RATE));
    n += snprintf(text + n, sizeof(text) - n, "devices=%u", waveOutGetNumDevs());
    rc = waveOutOpen(&wave, WAVE_MAPPER, &format, 0, 0, CALLBACK_NULL);
    n += snprintf(text + n, sizeof(text) - n, ";open=%u", rc);
    if (rc == MMSYSERR_NOERROR)
    {
        header.lpData = (LPSTR)samples;
        header.dwBufferLength = sizeof(samples);
        rc = waveOutPrepareHeader(wave, &header, sizeof(header));
        n += snprintf(text + n, sizeof(text) - n, ";prepare=%u", rc);
        if (rc == MMSYSERR_NOERROR)
        {
            rc = waveOutWrite(wave, &header, sizeof(header));
            n += snprintf(text + n, sizeof(text) - n, ";write=%u", rc);
            for (int waited = 0; rc == MMSYSERR_NOERROR && !(header.dwFlags & WHDR_DONE) && waited < 50; waited++) Sleep(100);
            n += snprintf(text + n, sizeof(text) - n, ";done=%u", (header.dwFlags & WHDR_DONE) ? 1u : 0u);
            waveOutUnprepareHeader(wave, &header, sizeof(header));
        }
        waveOutClose(wave);
    }
    n += snprintf(text + n, sizeof(text) - n, "\r\n");
    while (length && path[length - 1] != '\\') --length;
    lstrcpyA(path + length, "sound-result.txt");
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE)
    {
        WriteFile(file, text, (DWORD)n, &written, NULL);
        CloseHandle(file);
    }
    return 0;
}
