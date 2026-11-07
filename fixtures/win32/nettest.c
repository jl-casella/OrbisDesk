/* SPDX-License-Identifier: LGPL-2.1-or-later */
/* Phase 8: networking as a Windows program sees it (ws2_32, iphlpapi), 64-bit (guest) and 32-bit.
 * Steps, each on its own line of C:\orbis\net-result.txt with its Winsock or Win32 error code:
 *   dns      getaddrinfo of a name (argument 1, example.com by default), port 80
 *   tcp      a blocking TCP connect to the first IPv4 answer (or argument 2, a numeric IPv4
 *            address, when the name did not resolve)
 *   http     send of "HEAD / HTTP/1.0" and recv of the status line, 10 s receive timeout
 *   nbio     the same connect on a non-blocking socket, completed through select()
 *   udp      sendto of a DNS question for the same name to the first DNS server the adapters
 *            report (8.8.8.8 when there is none), recvfrom with a 5 s timeout
 *   loopback bind/listen on 127.0.0.1:0, connect, accept and one byte each way
 *   adapters GetAdaptersAddresses: each adapter's name, type, state and IPv4 addresses, gateway
 *            and DNS servers
 * The file is appended to, one block per run, so the 64- and 32-bit runs both stay in it. A step
 * that cannot run because an earlier one failed says so (skipped=...), never ok. */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0600   /* inet_pton, gateways and prefix lengths in GetAdaptersAddresses */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <iphlpapi.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>

static FILE *out;

static void line(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vfprintf(out, format, args);
    va_end(args);
    fputc('\n', out);
    fflush(out);
}

static const char *ipv4(const struct sockaddr *address, char *text, size_t size)
{
    DWORD length = (DWORD)size;
    if (!address) return "-";
    if (WSAAddressToStringA((struct sockaddr *)address, address->sa_family == AF_INET6 ? sizeof(struct sockaddr_in6) :
                            sizeof(struct sockaddr_in), NULL, text, &length)) return "?";
    return text;
}

/* A DNS question for an A record (RFC 1035), id 0x4f57. */
static int dns_question(const char *name, unsigned char *buffer, int size)
{
    int n = 12;
    const char *label = name;
    memset(buffer, 0, 12);
    buffer[0] = 0x4f; buffer[1] = 0x57; buffer[2] = 0x01; buffer[5] = 1;
    while (*label)
    {
        const char *dot = strchr(label, '.');
        int length = dot ? (int)(dot - label) : (int)strlen(label);
        if (length < 1 || length > 63 || n + length + 6 > size) return -1;
        buffer[n++] = (unsigned char)length;
        memcpy(buffer + n, label, length);
        n += length;
        label += length + (dot ? 1 : 0);
    }
    buffer[n++] = 0;
    buffer[n++] = 0; buffer[n++] = 1;   /* type A */
    buffer[n++] = 0; buffer[n++] = 1;   /* class IN */
    return n;
}

static void adapters_step(struct sockaddr_in *dns_server)
{
    ULONG size = 16384, error;
    IP_ADAPTER_ADDRESSES *list = NULL, *adapter;
    int count = 0;
    char a[64];

    for (int attempt = 0; attempt < 3; attempt++)
    {
        free(list);
        if (!(list = malloc(size))) { line("adapters ok=0 error=%lu stage=malloc", (unsigned long)ERROR_OUTOFMEMORY); return; }
        error = GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_INCLUDE_GATEWAYS, NULL, list, &size);
        if (error != ERROR_BUFFER_OVERFLOW) break;
    }
    if (error != NO_ERROR)
    {
        line("adapters ok=0 error=%lu", (unsigned long)error);
        free(list);
        return;
    }
    for (adapter = list; adapter; adapter = adapter->Next) count++;
    line("adapters ok=1 error=0 count=%d", count);
    for (adapter = list; adapter; adapter = adapter->Next)
    {
        IP_ADAPTER_UNICAST_ADDRESS *unicast;
        IP_ADAPTER_GATEWAY_ADDRESS *gateway;
        IP_ADAPTER_DNS_SERVER_ADDRESS *server;
        line("adapter name=%s type=%lu oper=%d if=%lu mtu=%lu mac=%02x:%02x:%02x:%02x:%02x:%02x", adapter->AdapterName,
             (unsigned long)adapter->IfType, (int)adapter->OperStatus, (unsigned long)adapter->IfIndex,
             (unsigned long)adapter->Mtu, adapter->PhysicalAddress[0], adapter->PhysicalAddress[1],
             adapter->PhysicalAddress[2], adapter->PhysicalAddress[3], adapter->PhysicalAddress[4],
             adapter->PhysicalAddress[5]);
        for (unicast = adapter->FirstUnicastAddress; unicast; unicast = unicast->Next)
            line("  address=%s prefix=%u", ipv4(unicast->Address.lpSockaddr, a, sizeof(a)), (unsigned)unicast->OnLinkPrefixLength);
        for (gateway = adapter->FirstGatewayAddress; gateway; gateway = gateway->Next)
            line("  gateway=%s", ipv4(gateway->Address.lpSockaddr, a, sizeof(a)));
        for (server = adapter->FirstDnsServerAddress; server; server = server->Next)
        {
            line("  dns=%s", ipv4(server->Address.lpSockaddr, a, sizeof(a)));
            if (!dns_server->sin_addr.s_addr && server->Address.lpSockaddr->sa_family == AF_INET)
                *dns_server = *(struct sockaddr_in *)server->Address.lpSockaddr;
        }
    }
    free(list);
}

static void loopback_step(void)
{
    SOCKET listener = INVALID_SOCKET, client = INVALID_SOCKET, server = INVALID_SOCKET;
    struct sockaddr_in address = {0};
    int length = sizeof(address);
    char byte = 'x', reply = 0;
    const char *stage = "socket";

    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if ((listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)) == INVALID_SOCKET) goto failed;
    stage = "bind";
    if (bind(listener, (struct sockaddr *)&address, sizeof(address))) goto failed;
    stage = "getsockname";
    if (getsockname(listener, (struct sockaddr *)&address, &length)) goto failed;
    stage = "listen";
    if (listen(listener, 1)) goto failed;
    stage = "connect";
    if ((client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)) == INVALID_SOCKET) goto failed;
    if (connect(client, (struct sockaddr *)&address, sizeof(address))) goto failed;
    stage = "accept";
    if ((server = accept(listener, NULL, NULL)) == INVALID_SOCKET) goto failed;
    stage = "send";
    if (send(client, &byte, 1, 0) != 1) goto failed;
    stage = "recv";
    if (recv(server, &reply, 1, 0) != 1 || reply != byte) goto failed;
    stage = "send-back";
    if (send(server, &reply, 1, 0) != 1) goto failed;
    stage = "recv-back";
    reply = 0;
    if (recv(client, &reply, 1, 0) != 1 || reply != byte) goto failed;
    line("loopback ok=1 error=0 port=%u", (unsigned)ntohs(address.sin_port));
    goto done;
failed:
    line("loopback ok=0 error=%d stage=%s", WSAGetLastError(), stage);
done:
    if (server != INVALID_SOCKET) closesocket(server);
    if (client != INVALID_SOCKET) closesocket(client);
    if (listener != INVALID_SOCKET) closesocket(listener);
}

static void udp_step(const char *name, struct sockaddr_in *dns_server)
{
    unsigned char question[300], answer[1500];
    struct sockaddr_in local = {0}, from = {0};
    int length, from_length = sizeof(from), received, timeout = 5000;
    SOCKET s;
    char a[64];

    if (!dns_server->sin_addr.s_addr)
    {
        dns_server->sin_family = AF_INET;
        inet_pton(AF_INET, "8.8.8.8", &dns_server->sin_addr);
    }
    dns_server->sin_port = htons(53);
    if ((length = dns_question(name, question, sizeof(question))) < 0) { line("udp ok=0 error=0 stage=name"); return; }
    if ((s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)) == INVALID_SOCKET) { line("udp ok=0 error=%d stage=socket", WSAGetLastError()); return; }
    local.sin_family = AF_INET;
    if (bind(s, (struct sockaddr *)&local, sizeof(local))) { line("udp ok=0 error=%d stage=bind", WSAGetLastError()); goto done; }
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof(timeout));
    if (sendto(s, (const char *)question, length, 0, (struct sockaddr *)dns_server, sizeof(*dns_server)) != length)
    {
        line("udp ok=0 error=%d stage=sendto server=%s", WSAGetLastError(), ipv4((struct sockaddr *)dns_server, a, sizeof(a)));
        goto done;
    }
    received = recvfrom(s, (char *)answer, sizeof(answer), 0, (struct sockaddr *)&from, &from_length);
    if (received < 12)
    {
        line("udp ok=0 error=%d stage=recvfrom received=%d server=%s", WSAGetLastError(), received,
             ipv4((struct sockaddr *)dns_server, a, sizeof(a)));
        goto done;
    }
    /* The reply must be ours (same id) and come from the server asked. */
    line("udp ok=%d error=0 server=%s from=%s bytes=%d id=%02x%02x rcode=%d answers=%d",
         answer[0] == 0x4f && answer[1] == 0x57 && from.sin_addr.s_addr == dns_server->sin_addr.s_addr,
         ipv4((struct sockaddr *)dns_server, a, sizeof(a)), ipv4((struct sockaddr *)&from, (char[64]){0}, 64),
         received, answer[0], answer[1], answer[3] & 15, answer[6] << 8 | answer[7]);
done:
    closesocket(s);
}

static void nbio_step(const struct sockaddr_in *target)
{
    u_long on = 1;
    fd_set writable, failed;
    struct timeval wait = {10, 0};
    int error = 0, length = sizeof(error), ready;
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);

    if (s == INVALID_SOCKET) { line("nbio ok=0 error=%d stage=socket", WSAGetLastError()); return; }
    if (ioctlsocket(s, FIONBIO, &on)) { line("nbio ok=0 error=%d stage=fionbio", WSAGetLastError()); goto done; }
    if (!connect(s, (const struct sockaddr *)target, sizeof(*target))) { line("nbio ok=1 error=0 immediate=1"); goto done; }
    if (WSAGetLastError() != WSAEWOULDBLOCK) { line("nbio ok=0 error=%d stage=connect", WSAGetLastError()); goto done; }
    FD_ZERO(&writable); FD_SET(s, &writable);
    FD_ZERO(&failed); FD_SET(s, &failed);
    ready = select(0, NULL, &writable, &failed, &wait);
    if (ready <= 0) { line("nbio ok=0 error=%d stage=select ready=%d", ready ? WSAGetLastError() : WSAETIMEDOUT, ready); goto done; }
    getsockopt(s, SOL_SOCKET, SO_ERROR, (char *)&error, &length);
    line("nbio ok=%d error=%d writable=%d failed=%d", FD_ISSET(s, &writable) && !error, error,
         FD_ISSET(s, &writable) != 0, FD_ISSET(s, &failed) != 0);
done:
    closesocket(s);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show)
{
    const char *name = "example.com", *fallback = NULL;
    char arguments[512], target_text[64] = "-", request[600], response[1024];
    struct addrinfo hints = {0}, *answers = NULL, *answer;
    struct sockaddr_in target = {0}, dns_server = {0};
    int error, have_target = 0, timeout = 10000, sent, received;
    WSADATA data;
    SYSTEMTIME now;
    SOCKET s = INVALID_SOCKET;
    DWORD started;
    (void)instance; (void)previous; (void)show;

    snprintf(arguments, sizeof(arguments), "%s", command ? command : "");
    {
        /* W176: a 64-bit guest gets explorer's command line ("/desktop=shell,1280x720",
         * W174), so arguments that start with '/' are not ours and are skipped. */
        char *token = strtok(arguments, " \t");
        int index = 0;
        for (; token; token = strtok(NULL, " \t"))
        {
            if (token[0] == '/') continue;
            if (index == 0) name = token;
            else if (index == 1) fallback = token;
            index++;
        }
    }
    CreateDirectoryA("C:\\orbis", NULL);
    if (!(out = fopen("C:\\orbis\\net-result.txt", "a"))) return 1;
    GetSystemTime(&now);
    line("run arch=%d name=%s fallback=%s utc=%04u-%02u-%02uT%02u:%02u:%02uZ", (int)sizeof(void *) * 8, name,
         fallback ? fallback : "-", now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute, now.wSecond);
    if ((error = WSAStartup(MAKEWORD(2, 2), &data)))
    {
        line("wsastartup ok=0 error=%d", error);
        line("end");
        fclose(out);
        return 1;
    }
    line("wsastartup ok=1 error=0 version=%u.%u", LOBYTE(data.wVersion), HIBYTE(data.wVersion));

    /* dns */
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    started = GetTickCount();
    error = getaddrinfo(name, "80", &hints, &answers);
    if (error)
        line("dns ok=0 error=%d wsa=%d ms=%lu", error, WSAGetLastError(), (unsigned long)(GetTickCount() - started));
    else
    {
        int count = 0;
        char a[64];
        for (answer = answers; answer; answer = answer->ai_next)
        {
            count++;
            line("  answer family=%d address=%s", answer->ai_family, ipv4(answer->ai_addr, a, sizeof(a)));
            if (!have_target && answer->ai_family == AF_INET)
            {
                target = *(struct sockaddr_in *)answer->ai_addr;
                have_target = 1;
            }
        }
        line("dns ok=%d error=0 answers=%d ipv4=%d ms=%lu", count > 0, count, have_target,
             (unsigned long)(GetTickCount() - started));
        freeaddrinfo(answers);
    }
    if (!have_target && fallback && inet_pton(AF_INET, fallback, &target.sin_addr) == 1)
    {
        target.sin_family = AF_INET;
        target.sin_port = htons(80);
        have_target = 2;
    }
    if (have_target) ipv4((struct sockaddr *)&target, target_text, sizeof(target_text));

    /* tcp + http */
    if (!have_target)
    {
        line("tcp ok=0 error=0 skipped=no-address");
        line("http ok=0 error=0 skipped=no-address");
    }
    else if ((s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)) == INVALID_SOCKET)
    {
        line("tcp ok=0 error=%d stage=socket", WSAGetLastError());
        line("http ok=0 error=0 skipped=no-socket");
    }
    else
    {
        started = GetTickCount();
        if (connect(s, (struct sockaddr *)&target, sizeof(target)))
        {
            line("tcp ok=0 error=%d target=%s source=%s ms=%lu", WSAGetLastError(), target_text,
                 have_target == 2 ? "fallback" : "dns", (unsigned long)(GetTickCount() - started));
            line("http ok=0 error=0 skipped=not-connected");
        }
        else
        {
            struct sockaddr_in local = {0};
            int length = sizeof(local);
            char a[64];
            getsockname(s, (struct sockaddr *)&local, &length);
            line("tcp ok=1 error=0 target=%s source=%s local=%s ms=%lu", target_text, have_target == 2 ? "fallback" : "dns",
                 ipv4((struct sockaddr *)&local, a, sizeof(a)), (unsigned long)(GetTickCount() - started));
            setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof(timeout));
            snprintf(request, sizeof(request), "HEAD / HTTP/1.0\r\nHost: %s\r\nUser-Agent: orbisdesk-nettest\r\n\r\n", name);
            sent = send(s, request, (int)strlen(request), 0);
            if (sent != (int)strlen(request))
                line("http ok=0 error=%d stage=send sent=%d", WSAGetLastError(), sent);
            else
            {
                /* W176: readiness first, so a failure says whether the data never showed
                 * up (select) or the receive itself failed (recv) */
                fd_set readable;
                struct timeval wait = {10, 0};
                int ready;
                FD_ZERO(&readable); FD_SET(s, &readable);
                started = GetTickCount();
                ready = select(0, &readable, NULL, NULL, &wait);
                line("  readable ready=%d error=%d ms=%lu", ready, ready < 0 ? WSAGetLastError() : 0,
                     (unsigned long)(GetTickCount() - started));
                started = GetTickCount();
                received = recv(s, response, sizeof(response) - 1, 0);
                if (received <= 0)
                    line("http ok=0 error=%d stage=recv received=%d ms=%lu", WSAGetLastError(), received,
                         (unsigned long)(GetTickCount() - started));
                else
                {
                    char *end;
                    response[received] = 0;
                    if ((end = strpbrk(response, "\r\n"))) *end = 0;
                    line("http ok=%d error=0 bytes=%d status=%s", !strncmp(response, "HTTP/", 5), received, response);
                }
            }
        }
        closesocket(s);
    }

    if (have_target) nbio_step(&target);
    else line("nbio ok=0 error=0 skipped=no-address");
    loopback_step();
    adapters_step(&dns_server);
    udp_step(name, &dns_server);
    WSACleanup();
    line("end");
    fclose(out);
    return 0;
}
