#pragma once
#include <stdlib.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_INTERNAL 2
static inline void *heap_caps_calloc(size_t n, size_t s, int c) { return calloc(n, s); }
static inline void *heap_caps_malloc(size_t s, int c) { return malloc(s); }
static inline void *heap_caps_realloc(void *p, size_t s, int c) { return realloc(p, s); }
static inline void heap_caps_free(void *p) { free(p); }
static inline size_t heap_caps_get_free_size(int c) { return 0; }
