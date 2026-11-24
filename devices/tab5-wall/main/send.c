/* A turned screen's frames, sent beside the drawing of the next one.
 *
 * The Tab5's panel stands on its side and a 7B may be mounted the other way round: what LVGL drew is then turned by
 * the P4's pixel processor before the panel shows it. The board packages' LVGL port has the screen's task wait for
 * that turn (into a buffer of the port's own, which is then copied into the panel's frame). Measured on the 7B, the
 * turn takes 27 ms for a whole screen: 20 of the 35 ms a frame of Settings scrolling took.
 *
 * Here a turned frame is handed to a task of its own, which turns it straight into the panel's frame (the pixel
 * processor for a quarter turn, a loop of its own for half a turn): no second copy, and LVGL draws the next frame
 * into its other buffer meanwhile. LVGL waits before it
 * hands over that next one (send_wait), so two are never on their way at once. A screen that is not turned is sent
 * as before: the port's copy into the panel's frame runs by itself already.
 *
 * A frame that stands alone (a tap) is not on the screen any sooner for this; a row of them (a scroll, a photo
 * fading in) comes as fast as the slower of drawing and turning, not as their sum. */
#include "bsp/esp-bsp.h"
#include "driver/ppa.h"
#include "esp_cache.h"
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_panel_ops.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lvgl_private.h"   /* the display's own flush function and its "being sent" mark */
#include "wall.h"

static const char *TAG = "send";

typedef struct {
    lv_area_t area;      /* as LVGL drew it */
    uint8_t *px;
    int rotation;
    int32_t hres, vres;  /* the screen as LVGL sees it, turned */
} job_t;

static lv_display_t *disp;
static lv_display_flush_cb_t port_flush;   /* the board package's: turn, wait, copy */
static esp_lcd_panel_handle_t panel;       /* seen when the port sends its first frame */
static void *frame;                        /* the panel's frame, which it shows from */
static ppa_client_handle_t turner;
static QueueHandle_t jobs;
static SemaphoreHandle_t sent;
static volatile bool sending, broken;
static int checked = -1, checks;           /* the turn last checked, and how many of its frames are still to check */

/* the panel is the board package's to know: the port's first frame passes it here (-Wl,--wrap in CMakeLists.txt) */
esp_err_t __real_esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t p, int x1, int y1, int x2, int y2, const void *px);
esp_err_t __wrap_esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t p, int x1, int y1, int x2, int y2, const void *px)
{
    if (!panel) panel = p;
    return __real_esp_lcd_panel_draw_bitmap(p, x1, y1, x2, y2, px);
}

/* Half a turn is the area's pixels in the opposite order, and the processor writes them into the panel's frame
 * faster than the pixel processor does: measured on the 7B, the pixel processor took 27 ms for two thirds of a
 * screen while the next frame was drawn, where the same pixels are copied in 11. */
static esp_err_t turn_half(const job_t *j)
{
    int w = lv_area_get_width(&j->area), h = lv_area_get_height(&j->area);
    int x = j->hres - j->area.x2 - 1, y = j->vres - j->area.y2 - 1;
    const uint16_t *s = (const uint16_t *)j->px;
    uint16_t *out = frame;
    for (int r = 0; r < h; r++) {
        uint16_t *d = out + (size_t)(y + h - 1 - r) * BSP_LCD_H_RES + x + w;   /* one past the row's last pixel */
        int i = w;
        for (; i >= 8; i -= 8, s += 8, d -= 8) {
            d[-1] = s[0];
            d[-2] = s[1];
            d[-3] = s[2];
            d[-4] = s[3];
            d[-5] = s[4];
            d[-6] = s[5];
            d[-7] = s[6];
            d[-8] = s[7];
        }
        for (; i > 0; i--) *--d = *s++;
    }
    /* the panel is shown from the memory itself, not through the processor's cache: what was written goes there now */
    return esp_cache_msync(out + (size_t)y * BSP_LCD_H_RES + x, ((size_t)(h - 1) * BSP_LCD_H_RES + w) * 2,
                           ESP_CACHE_MSYNC_FLAG_DIR_C2M | ESP_CACHE_MSYNC_FLAG_UNALIGNED);
}

/* a quarter turn (the Tab5) is the pixel processor's; where the area lands on the panel is worked out as the port
 * does (lvgl_port_ppa_rotate) */
static esp_err_t turn(const job_t *j)
{
    if (j->rotation == LV_DISPLAY_ROTATION_180) return turn_half(j);
    int w = lv_area_get_width(&j->area), h = lv_area_get_height(&j->area);
    int x = j->area.x1, y = j->area.y1;
    switch (j->rotation) {
    case LV_DISPLAY_ROTATION_90:
        x = j->area.y1;
        y = j->hres - j->area.x2 - 1;
        break;
    case LV_DISPLAY_ROTATION_270:
        x = j->vres - j->area.y2 - 1;
        y = j->area.x1;
        break;
    default:
        break;
    }
    ppa_srm_oper_config_t op = {
        .in = {.buffer = j->px, .pic_w = w, .pic_h = h, .block_w = w, .block_h = h, .srm_cm = PPA_SRM_COLOR_MODE_RGB565},
        .out = {.buffer = frame,
                .buffer_size = (uint32_t)BSP_LCD_H_RES * BSP_LCD_V_RES * 2,
                .pic_w = BSP_LCD_H_RES,
                .pic_h = BSP_LCD_V_RES,
                .block_offset_x = x,
                .block_offset_y = y,
                .srm_cm = PPA_SRM_COLOR_MODE_RGB565},
        .rotation_angle = j->rotation,
        .scale_x = 1.0,
        .scale_y = 1.0,
        .byte_swap = BSP_LCD_BIGENDIAN ? true : false,
        .mode = PPA_TRANS_MODE_BLOCKING,
    };
    return ppa_do_scale_rotate_mirror(turner, &op);
}

/* Every pixel of the area is in the panel's frame where its turn puts it. The first frames of each turn are looked
 * at like this, on any board: the Tab5's quarter turns were written without a Tab5 at hand, and a picture that came
 * out wrong would otherwise stay wrong. */
static bool as_drawn(const job_t *j)
{
    int w = lv_area_get_width(&j->area), h = lv_area_get_height(&j->area);
    const uint16_t *src = (const uint16_t *)j->px, *out = frame;
    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            int lx = j->area.x1 + x, ly = j->area.y1 + y, px, py;
            switch (j->rotation) {
            case LV_DISPLAY_ROTATION_90:
                px = ly;
                py = j->hres - 1 - lx;
                break;
            case LV_DISPLAY_ROTATION_180:
                px = j->hres - 1 - lx;
                py = j->vres - 1 - ly;
                break;
            default:
                px = j->vres - 1 - ly;
                py = lx;
                break;
            }
            if (out[py * BSP_LCD_H_RES + px] != src[y * w + x]) return false;
        }
    }
    return true;
}

static void sender(void *arg)
{
    job_t j;
    for (;;) {
        if (xQueueReceive(jobs, &j, portMAX_DELAY) != pdTRUE) continue;
        int64_t t0 = esp_timer_get_time();
        bool ok = turn(&j) == ESP_OK;
        uint32_t us = (uint32_t)(esp_timer_get_time() - t0);
        if (ok && j.rotation != checked) {
            checked = j.rotation;
            checks = 3;
        }
        if (ok && checks > 0) {
            ok = as_drawn(&j);
            if (ok && !--checks) ESP_LOGI(TAG, "turned frames (%d) are in the panel's frame as drawn", j.rotation * 90);
        }
        if (ok) {
            ui_frames_beside(us, (uint32_t)lv_area_get_size(&j.area));
            sending = false;
            lv_display_flush_ready(disp);
        } else {
            /* this frame and all after it go the port's way */
            ESP_LOGE(TAG, "a frame turned (%d) into the panel's frame is not as drawn: sent as before from here on",
                     j.rotation * 90);
            broken = true;
            port_flush(disp, &j.area, j.px);
            sending = false;
        }
        xSemaphoreGive(sent);
    }
}

bool send_beside(void)
{
    return port_flush && !broken;
}

static void send_flush(lv_display_t *d, const lv_area_t *a, uint8_t *px)
{
    lv_display_rotation_t r = lv_display_get_rotation(d);
    if (!frame && panel) esp_lcd_dpi_panel_get_frame_buffer(panel, 1, &frame);
    if (r == LV_DISPLAY_ROTATION_0 || !frame || broken) {
        port_flush(d, a, px);
        return;
    }
    job_t j = {.area = *a, .px = px, .rotation = r, .hres = lv_display_get_horizontal_resolution(d),
               .vres = lv_display_get_vertical_resolution(d)};
    sending = true;
    xQueueSend(jobs, &j, portMAX_DELAY);
}

/* LVGL has drawn the next frame and waits for the one before it to be on the panel: the screen's task gives up the
 * processor while the sender works, and waits as LVGL itself does for the port's copy, which ends with an interrupt */
static void send_wait(lv_display_t *d)
{
    while (sending) xSemaphoreTake(sent, pdMS_TO_TICKS(100));
    while (d->flushing) {
    }
}

void send_start(lv_display_t *d)
{
    const ppa_client_config_t cfg = {.oper_type = PPA_OPERATION_SRM};
    disp = d;
    jobs = xQueueCreate(1, sizeof(job_t));
    sent = xSemaphoreCreateBinary();
    if (!jobs || !sent || ppa_register_client(&cfg, &turner) != ESP_OK ||
        xTaskCreatePinnedToCore(sender, "send", 4096, NULL, 6, NULL, 1) != pdPASS) {
        ESP_LOGW(TAG, "no task to send turned frames: sent as before");
        return;
    }
    port_flush = d->flush_cb;
    lv_display_set_flush_cb(d, send_flush);
    lv_display_set_flush_wait_cb(d, send_wait);
}
