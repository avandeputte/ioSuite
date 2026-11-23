#pragma once
#include <stdint.h>
#include <stddef.h>
typedef void *jpeg_decoder_handle_t;
typedef struct { int intr_priority, timeout_ms; } jpeg_decode_engine_cfg_t;
typedef struct { int buffer_direction; } jpeg_decode_memory_alloc_cfg_t;
typedef struct { uint32_t width, height; } jpeg_decode_picture_info_t;
typedef struct { int output_format, rgb_order, conv_std; } jpeg_decode_cfg_t;
#define JPEG_DEC_ALLOC_OUTPUT_BUFFER 0
#define JPEG_DEC_ALLOC_INPUT_BUFFER 1
#define JPEG_DECODE_OUT_FORMAT_RGB565 0
#define JPEG_DEC_RGB_ELEMENT_ORDER_BGR 0
#define JPEG_YUV_RGB_CONV_STD_BT601 0
#define ESP_OK 0
int jpeg_new_decoder_engine(const jpeg_decode_engine_cfg_t *c, jpeg_decoder_handle_t *h);
void *jpeg_alloc_decoder_mem(size_t n, const jpeg_decode_memory_alloc_cfg_t *c, size_t *got);
int jpeg_decoder_get_info(const uint8_t *in, size_t n, jpeg_decode_picture_info_t *info);
int jpeg_decoder_process(jpeg_decoder_handle_t h, const jpeg_decode_cfg_t *c, const uint8_t *in, size_t n, uint8_t *out, size_t outn, uint32_t *got);
