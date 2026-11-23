/* What the wall keeps across restarts: one blob in NVS ("wall"/"cfg"). A blob of another version is not read
 * (pre-release: it starts afresh, set up again on the device). */
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "wall.h"

#define CFG_VERSION 3

wall_settings_t S;
uint32_t VIEWS_OFF;

static void defaults(void)
{
    memset(&S, 0, sizeof S);
    S.version = CFG_VERSION;
    S.clock24 = false;
    S.night_from = 22;
    S.night_to = 6;
    S.day_bright = 90;
    S.night_bright = 12;
    S.volume = 70;
    S.auto_update = true;
    S.snooze_min = 9;
    S.alarms[0] = (wall_alarm_t){.hour = 7, .minute = 0, .days = 0x3e, .on = false, .label = "Weekdays"};
    S.alarms[1] = (wall_alarm_t){.hour = 8, .minute = 30, .days = 0x41, .on = false, .label = "Weekend"};
    S.alarms[2] = (wall_alarm_t){.hour = 6, .minute = 30, .days = 0, .on = false, .label = ""};
    S.alarms[3] = (wall_alarm_t){.hour = 12, .minute = 0, .days = 0, .on = false, .label = ""};
}

void settings_load(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    defaults();
    nvs_handle_t h;
    if (nvs_open("wall", NVS_READONLY, &h) != ESP_OK) {
        return;
    }
    if (nvs_get_u32(h, "views_off", &VIEWS_OFF) != ESP_OK) VIEWS_OFF = 0;
    wall_settings_t got;
    size_t n = sizeof got;
    if (nvs_get_blob(h, "cfg", &got, &n) == ESP_OK && n == sizeof got && got.version == CFG_VERSION) {
        S = got;
        S.ssid[sizeof S.ssid - 1] = 0;
        S.server[sizeof S.server - 1] = 0;
        S.token[sizeof S.token - 1] = 0;
    } else {
        ESP_LOGI(TAG_WALL, "no settings yet (or of another version): set up on the device");
    }
    nvs_close(h);
}

/* Writing to the flash takes a few milliseconds, and many more when NVS has to clear a page first; the screens call
 * settings_save from a touch, holding the screen's lock. So the write is done by a task of its own: the screen goes
 * on at once, and what a switch, a slider let go and a row of chips set one after another goes out in as few writes
 * as it takes. */
static TaskHandle_t saver;
static volatile bool cfg_due, views_due;

static void write_now(void)
{
    nvs_handle_t h;
    if (nvs_open("wall", NVS_READWRITE, &h) != ESP_OK) {
        ESP_LOGE(TAG_WALL, "settings not saved: NVS");
        return;
    }
    if (cfg_due) {
        cfg_due = false;   /* before the copy: a change made while it is written is written after it */
        static wall_settings_t copy;
        copy = S;
        nvs_set_blob(h, "cfg", &copy, sizeof copy);
    }
    if (views_due) {
        views_due = false;
        nvs_set_u32(h, "views_off", VIEWS_OFF);
    }
    nvs_commit(h);
    nvs_close(h);
}

static void save_loop(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        while (cfg_due || views_due) write_now();
    }
}

/* once the settings are read: the task that writes them (before it, a save is written where it is called) */
void settings_start(void)
{
    xTaskCreate(save_loop, "settings", 6144, NULL, 2, &saver);
}

void settings_save(void)
{
    cfg_due = true;
    if (saver) xTaskNotifyGive(saver);
    else write_now();
}

void settings_save_views(void)
{
    views_due = true;
    if (saver) xTaskNotifyGive(saver);
    else write_now();
}

void settings_forget_sign_in(void)
{
    S.token[0] = 0;
    S.user[0] = 0;
    settings_save();
}

void settings_reset(void)
{
    defaults();
    settings_save();
    VIEWS_OFF = 0;
    settings_save_views();
}
