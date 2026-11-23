#pragma once
#include <stdbool.h>
#include "lvgl.h"
#define BSP_LCD_H_RES 1280
#define BSP_LCD_V_RES 720
typedef void *esp_codec_dev_handle_t_;
bool bsp_display_lock(uint32_t t);
void bsp_display_unlock(void);
void bsp_display_backlight_on(void);
void bsp_display_backlight_off(void);
void bsp_display_brightness_set(int pct);
void bsp_display_rotate(lv_display_t *d, lv_display_rotation_t r);
lv_indev_t *bsp_display_get_input_dev(void);
void *bsp_audio_codec_speaker_init(void);
void *bsp_i2c_get_handle(void);
#define BSP_FEATURE_WIFI 0
static inline int bsp_feature_enable(int f, bool on) { return 0; }
