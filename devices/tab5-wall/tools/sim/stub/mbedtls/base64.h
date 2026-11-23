#pragma once
#include <stddef.h>
static inline int mbedtls_base64_encode(unsigned char *dst, size_t dlen, size_t *olen, const unsigned char *src, size_t slen) { if (dlen) dst[0] = 0; *olen = 0; return 0; }
