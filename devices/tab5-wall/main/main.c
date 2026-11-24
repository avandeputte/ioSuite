/* ioWall: the start page's wall on the wall, on an M5Stack Tab5 or a Waveshare ESP32-P4-WIFI6-Touch-LCD-7B (board.h). */
#include <string.h>
#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

#if defined(WALL_BOARD_WAVESHARE7B)
#include "bsp/touch.h"
#include "esp_lvgl_port.h"

/* The 7B's screen is started here and not by its board package (bsp_display_start_with_config), with the same calls
 * the package makes, for one difference: the panel turns the picture itself. This board is only ever turned by half
 * a turn, and its panel's driver chip (EK79007) scans the other way round on a command. The package has the P4's pixel
 * processor turn every frame instead, into a third buffer: measured on the board, 27 ms for a whole screen, 20 of the
 * 35 ms a frame of Settings scrolling took, and nothing at all the other way up. (The package's own setting for
 * leaving the turning to the panel mirrors it from top to bottom only, and its touch with it.) */
static lv_display_t *screen_start(const bsp_display_cfg_t *cfg)
{
    if (lvgl_port_init(&cfg->lvgl_port_cfg) != ESP_OK || bsp_display_brightness_init() != ESP_OK) return NULL;
    bsp_lcd_handles_t lcd;
    if (bsp_display_new_with_handles(NULL, &lcd) != ESP_OK) return NULL;
    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = lcd.io,
        .panel_handle = lcd.panel,
        .control_handle = lcd.control,
        .buffer_size = cfg->buffer_size,
        .double_buffer = cfg->double_buffer,
        .hres = BSP_LCD_H_RES,
        .vres = BSP_LCD_V_RES,
        /* as the panel scans when nothing is said (from left to right, from the top down): what the port sets for no
         * turn, and the opposite of both for half a turn */
        .rotation = {.swap_xy = false, .mirror_x = true, .mirror_y = false},
        .color_format = LV_COLOR_FORMAT_RGB565,
        .flags = {
            .buff_dma = cfg->flags.buff_dma,
            .buff_spiram = cfg->flags.buff_spiram,
            .swap_bytes = BSP_LCD_BIGENDIAN ? true : false,
            .sw_rotate = false,
        },
    };
    const lvgl_port_display_dsi_cfg_t dsi_cfg = {0};
    lv_display_t *disp = lvgl_port_add_disp_dsi(&disp_cfg, &dsi_cfg);
    if (!disp) return NULL;
    esp_lcd_touch_handle_t tp = NULL;
    if (bsp_touch_new(NULL, &tp) == ESP_OK && tp) {
        const lvgl_port_touch_cfg_t touch_cfg = {.disp = disp, .handle = tp};
        lvgl_port_add_touch(&touch_cfg);
    } else {
        ESP_LOGE(TAG_WALL, "no touch");
    }
    return disp;
}
#else
#define screen_start bsp_display_start_with_config
#endif

void app_main(void)
{
    boot_begin();
    settings_load();
    settings_start();
    if (S.posix[0]) clock_set_zone(S.posix);   /* the clock in local time before the network is up */

    boot_step(BOOT_SCREEN);
    /* as M5Stack's own firmware sets the Tab5's screen up: two whole-screen buffers in the PSRAM, so a change is drawn
     * and sent in one go (small buffers in internal memory sent a screen in dozens of strips, each turned by itself:
     * a second or two per touch) */
    bsp_display_cfg_t cfg = {
        .lvgl_port_cfg = ESP_LVGL_PORT_INIT_CONFIG(),
        .buffer_size = BSP_LCD_H_RES * BSP_LCD_V_RES,
        .double_buffer = true,
        .flags = {
            .buff_dma = true,
            .buff_spiram = true,
            .sw_rotate = true,   /* the Tab5: turned (BOARD_ROTATION) by the P4's pixel processor (LVGL_PORT_ENABLE_PPA) */
        },
    };
    cfg.lvgl_port_cfg.task_stack = 32768;   /* the TrueType rasterizer draws on this stack */
    cfg.lvgl_port_cfg.task_affinity = 0;
    lv_display_t *disp = screen_start(&cfg);
    if (!disp) {
        ESP_LOGE(TAG_WALL, "no display");
        return;
    }
    bsp_display_backlight_on();
    ESP_LOGI(TAG_WALL, "%s, %s; screen up; internal memory free: %u", BOARD_NAME, WALL_OTA_FILE, (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));

    /* the last start stopped somewhere: say where, then go on without that part when the wall can do without it */
    boot_report(boot_skip(BOOT_SOUND) || boot_skip(BOOT_WIFI) || boot_skip(BOOT_OTA) || boot_skip(BOOT_RUNNING));

    /* each step waits a moment before the next, so a stop is put down to the step that caused it */
    if (!boot_skip(BOOT_SOUND)) {
        boot_step(BOOT_SOUND);
        alarm_start();   /* before the screens: the volume, and a ring's sound */
        vTaskDelay(pdMS_TO_TICKS(300));
    }

    power_start();   /* the battery's level, where the board measures it */

    boot_step(BOOT_ROTATE);
    ui_lock();
    bsp_display_rotate(disp, BOARD_ROTATION(S.flip));
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    ui_unlock();
    vTaskDelay(pdMS_TO_TICKS(600));

    boot_step(BOOT_UI);
    feed_init();   /* the screens read the feed and hand their calls to its task from the first moment */
    ui_lock();
    ui_start(disp);
    ui_unlock();
    vTaskDelay(pdMS_TO_TICKS(1500));

    if (!boot_skip(BOOT_WIFI)) {
        boot_step(BOOT_WIFI);
        net_init();
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
    boot_step(BOOT_FEED);
    feed_start();
    vTaskDelay(pdMS_TO_TICKS(1000));
    if (!boot_skip(BOOT_OTA)) {
        boot_step(BOOT_OTA);
        ota_start();
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    boot_running();
    ESP_LOGI(TAG_WALL, "ioWall %s", wall_version());
    /* a pull request's build measures its own screen once the wall is up: a board on a cable is restarted for it */
    if (!strncmp(wall_version(), "pr", 2)) bench_start(30000);
}
