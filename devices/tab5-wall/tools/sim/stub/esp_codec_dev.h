#pragma once
typedef void *esp_codec_dev_handle_t;
typedef struct { int sample_rate, channel, bits_per_sample; } esp_codec_dev_sample_info_t;
#define ESP_CODEC_DEV_OK 0
static inline int esp_codec_dev_open(void *s, esp_codec_dev_sample_info_t *f) { return 0; }
static inline int esp_codec_dev_write(void *s, void *d, int n) { return 0; }
static inline int esp_codec_dev_set_out_vol(void *s, int v) { return 0; }
