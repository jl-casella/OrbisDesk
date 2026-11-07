/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Mbed TLS 3.6.6 for the Steam client title (ORBS00001), on top of the library's default
 * mbedtls_config.h (MBEDTLS_USER_CONFIG_FILE). As Playden's PS5 build: threads on, since the
 * client's HTTP and CM connections share entropy, DRBG and PSA state.
 * The console has neither the library's sockets (MBEDTLS_NET_C, Linux numbers in the SDK's
 * headers) nor a platform entropy source it knows (FreeBSD's KERN_ARND sysctl): the title reads
 * /dev/urandom itself in mbedtls_hardware_poll (native/steam/steam_tls.c), and fails if it can't.
 * No key storage on disk: PSA keys live in memory only. No file access in the library either
 * (MBEDTLS_FS_IO): its directory walk imports getdents, which no running eboot imports; the
 * title reads the CA bundle itself and hands the bytes to mbedtls_x509_crt_parse. */
#undef MBEDTLS_FS_IO
#undef MBEDTLS_NET_C
#undef MBEDTLS_TIMING_C
#undef MBEDTLS_PSA_CRYPTO_STORAGE_C
#undef MBEDTLS_PSA_ITS_FILE_C
#define MBEDTLS_NO_PLATFORM_ENTROPY
#define MBEDTLS_ENTROPY_HARDWARE_ALT
#define MBEDTLS_THREADING_C
#define MBEDTLS_THREADING_PTHREAD
