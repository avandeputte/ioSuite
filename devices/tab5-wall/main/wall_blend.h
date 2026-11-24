/* LVGL's see-through drawing onto a 16-bit screen, with loops of this firmware's own. LVGL asks here first
 * (LV_DRAW_SW_ASM_CUSTOM: this file is included by its blending code, sdkconfig.defaults and ../CMakeLists.txt) and
 * draws by itself what is not taken.
 *
 * Why: LVGL mixes two colours in a function it calls for every pixel (lv_color_16_16_mix), and reads and writes each
 * pixel of a see-through fill through a volatile pointer. Measured on the board (ESP32-P4, 1024 x 600): black at 3/4
 * over a photo, as under a view, took about 130 ms for a screen, when the same memory is filled in 8 ms and copied
 * in 17. That was most of a swipe to a view (210 ms a frame), of a panel opening (185 ms) and of each frame of a photo
 * fading in (130 ms). Here the mix is in the loop, the colour that stays the same is taken apart once, and of a
 * letter's box the pixels it leaves alone are passed four at a time.
 *
 * What is drawn is the same to the bit: mix() below is lv_color_16_16_mix. tools/sim/run.sh <board> check draws every
 * frame of its script with these loops and with LVGL's own and compares them. */
#pragma once

/* LVGL includes this file from more of its drawing code than the blending: only there are the types below known */
#ifdef LV_DRAW_SW_BLEND_PRIVATE_H

#include <stdint.h>

typedef uint32_t __attribute__((may_alias)) wall_blend_u32;   /* four bytes of a mask read as one number */

/* a 16-bit colour with green moved up out of the way, so one multiplication mixes all three */
static inline uint32_t wall_blend_apart(uint32_t c)
{
    return (c | (c << 16)) & 0x7E0F81F;
}

/* lv_color_16_16_mix(fg, c2, mix) for mix below 255, fg already taken apart and mix already (mix + 4) >> 3 */
static inline uint16_t wall_blend_mix(uint32_t fg, uint32_t c2, uint32_t mix5)
{
    uint32_t bg = wall_blend_apart(c2);
    uint32_t r = ((((fg - bg) * mix5) >> 5) + bg) & 0x7E0F81F;
    return (uint16_t)((r >> 16) | r);
}

/* one colour, see-through, over an area: what darkens the wall under a view or a panel, a chip, the bar */
static inline lv_result_t wall_blend_color_opa(lv_draw_sw_blend_fill_dsc_t *dsc)
{
    if (dsc->opa == 255) return LV_RESULT_INVALID;
    uint32_t fg = wall_blend_apart(lv_color_to_u16(dsc->color)), mix5 = ((uint32_t)dsc->opa + 4) >> 3;
    uint16_t *d = dsc->dest_buf;
    int32_t w = dsc->dest_w;
    for (int32_t y = dsc->dest_h; y > 0; y--) {
        for (int32_t x = 0; x < w; x++) d[x] = wall_blend_mix(fg, d[x], mix5);
        d = (uint16_t *)((uint8_t *)d + dsc->dest_stride);
    }
    return LV_RESULT_OK;
}

/* one colour through a mask: every letter, and the round corners of everything */
static inline lv_result_t wall_blend_color_mask(lv_draw_sw_blend_fill_dsc_t *dsc)
{
    uint16_t c16 = lv_color_to_u16(dsc->color);
    uint32_t fg = wall_blend_apart(c16);
    uint16_t *d = dsc->dest_buf;
    const uint8_t *m = dsc->mask_buf;
    int32_t w = dsc->dest_w;
    for (int32_t y = dsc->dest_h; y > 0; y--) {
        int32_t x = 0;
        while (x < w) {
            /* most of a letter's box is not the letter */
            if (!((uintptr_t)(m + x) & 3)) {
                while (x + 4 <= w && *(const wall_blend_u32 *)(m + x) == 0) x += 4;
                if (x >= w) break;
            }
            uint32_t a = m[x];
            if (a == 255) d[x] = c16;
            else if (a) d[x] = wall_blend_mix(fg, d[x], (a + 4) >> 3);
            x++;
        }
        d = (uint16_t *)((uint8_t *)d + dsc->dest_stride);
        m += dsc->mask_stride;
    }
    return LV_RESULT_OK;
}

/* one colour through a mask, see-through as well: a chip's round corners, dimmed text */
static inline lv_result_t wall_blend_color_mask_opa(lv_draw_sw_blend_fill_dsc_t *dsc)
{
    uint32_t fg = wall_blend_apart(lv_color_to_u16(dsc->color)), opa = dsc->opa;
    uint16_t *d = dsc->dest_buf;
    const uint8_t *m = dsc->mask_buf;
    int32_t w = dsc->dest_w;
    for (int32_t y = dsc->dest_h; y > 0; y--) {
        for (int32_t x = 0; x < w; x++) {
            uint32_t a = (m[x] * opa) >> 8;   /* LV_OPA_MIX2: never 255 */
            if (a) d[x] = wall_blend_mix(fg, d[x], (a + 4) >> 3);
        }
        d = (uint16_t *)((uint8_t *)d + dsc->dest_stride);
        m += dsc->mask_stride;
    }
    return LV_RESULT_OK;
}

/* a picture, see-through, over what is there: a photo fading in over the one before */
static inline lv_result_t wall_blend_image_opa(lv_draw_sw_blend_image_dsc_t *dsc)
{
    if (dsc->opa == 255) return LV_RESULT_INVALID;
    uint32_t mix5 = ((uint32_t)dsc->opa + 4) >> 3;
    uint16_t *d = dsc->dest_buf;
    const uint16_t *s = dsc->src_buf;
    int32_t w = dsc->dest_w;
    for (int32_t y = dsc->dest_h; y > 0; y--) {
        for (int32_t x = 0; x < w; x++) d[x] = wall_blend_mix(wall_blend_apart(s[x]), d[x], mix5);
        d = (uint16_t *)((uint8_t *)d + dsc->dest_stride);
        s = (const uint16_t *)((const uint8_t *)s + dsc->src_stride);
    }
    return LV_RESULT_OK;
}

#define LV_DRAW_SW_COLOR_BLEND_TO_RGB565_WITH_OPA(dsc) wall_blend_color_opa(dsc)
#define LV_DRAW_SW_COLOR_BLEND_TO_RGB565_WITH_MASK(dsc) wall_blend_color_mask(dsc)
#define LV_DRAW_SW_COLOR_BLEND_TO_RGB565_MIX_MASK_OPA(dsc) wall_blend_color_mask_opa(dsc)
#define LV_DRAW_SW_RGB565_BLEND_NORMAL_TO_RGB565_WITH_OPA(dsc) wall_blend_image_opa(dsc)

#endif
