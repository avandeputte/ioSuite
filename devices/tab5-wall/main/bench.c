/* The screen measured on the board itself: a finger that is not there scrolls Settings, drags a slider, swipes to a
 * view and back and asks for the next photo, and each of these is timed frame by frame (ui_frames_*). The result is
 * written to the log, a line per scene, and kept for Settings to show. This is how a change to the drawing is told
 * to be faster on the board and not only on a PC (tools/sim counts the work, never the board's time).
 *
 * Started from Settings › "Measure the screen", and by itself half a minute after the start on a pull request's
 * build (version "pr…"), so that a board on a cable is measured by restarting it. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "driver/gptimer.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/task.h"
#include "wall.h"

static const char *TAG = "bench";

static lv_indev_t *finger;          /* the finger that is not there */
static volatile int at_x, at_y;
static volatile bool down;
static volatile bool running, fresh;
static char result[1800];

/* LVGL turns a touch's point with the screen (lv_indev.c): the finger is put where that ends at at_x, at_y */
static void finger_read(lv_indev_t *i, lv_indev_data_t *d)
{
    lv_display_t *disp = lv_indev_get_display(i);
    int w = lv_display_get_original_horizontal_resolution(disp), h = lv_display_get_original_vertical_resolution(disp);
    int x = at_x, y = at_y;
    switch (lv_display_get_rotation(disp)) {
    case LV_DISPLAY_ROTATION_90: d->point.x = y; d->point.y = h - 1 - x; break;
    case LV_DISPLAY_ROTATION_180: d->point.x = w - 1 - x; d->point.y = h - 1 - y; break;
    case LV_DISPLAY_ROTATION_270: d->point.x = w - 1 - y; d->point.y = x; break;
    default: d->point.x = x; d->point.y = y; break;
    }
    d->state = down ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

static void wait_ms(int ms)
{
    vTaskDelay(pdMS_TO_TICKS(ms));
}

/* Where the time goes, on a pull request's build: a timer interrupts the screen's task two thousand times a second
 * and notes where it was (the program counter, and the return address, which for a function that calls nothing, as
 * memcpy, is who called it). After each scene the places are written to the log as "where:" lines, and
 * tools/where.py names the functions from the build's list of symbols. Without this, what a frame is made of was
 * guessed from a PC's count of the work, which knows nothing of how slow this board's memory is. */
#define WHERE_MAX 2000
typedef struct {
    uint32_t pc, ra;
} where_t;
static where_t *where;
static volatile uint32_t where_n, where_busy, where_ticks;
static volatile bool where_on;
static TaskHandle_t ui_task;
static gptimer_handle_t where_timer;

/* FreeRTOS keeps an interrupted task's registers at the top of its stack, the program counter first and the return
 * address after it (RvExcFrame), and the stack's top is the first thing in its handle */
static bool where_tick(gptimer_handle_t t, const gptimer_alarm_event_data_t *e, void *arg)
{
    if (!where_on) return false;
    where_ticks++;
    TaskHandle_t now = xTaskGetCurrentTaskHandleForCore(xPortGetCoreID());
    if (now != ui_task) return false;
    where_busy++;
    if (where_n < WHERE_MAX) {
        const uint32_t *regs = *(const uint32_t *const *)now;
        where[where_n].pc = regs[0];
        where[where_n].ra = regs[1];
        where_n++;
    }
    return false;
}

/* on the screen's task: the timer's interrupt comes on the core it is set up from */
static void where_setup(void *arg)
{
    ui_task = xTaskGetCurrentTaskHandle();
    if (where_timer) return;
    where = heap_caps_malloc(WHERE_MAX * sizeof *where, MALLOC_CAP_SPIRAM);
    const gptimer_config_t cfg = {.clk_src = GPTIMER_CLK_SRC_DEFAULT, .direction = GPTIMER_COUNT_UP, .resolution_hz = 1000000};
    const gptimer_event_callbacks_t cbs = {.on_alarm = where_tick};
    /* not a round number of the tick's milliseconds: the samples do not fall in step with it */
    const gptimer_alarm_config_t alarm = {.alarm_count = 487, .flags.auto_reload_on_alarm = true};
    gptimer_handle_t t = NULL;
    if (!where || gptimer_new_timer(&cfg, &t) != ESP_OK) return;
    if (gptimer_register_event_callbacks(t, &cbs, NULL) != ESP_OK || gptimer_set_alarm_action(t, &alarm) != ESP_OK ||
        gptimer_enable(t) != ESP_OK || gptimer_start(t) != ESP_OK) {
        gptimer_del_timer(t);
        return;
    }
    where_timer = t;
}

static void where_from_here(void)
{
    where_on = false;
    where_n = where_busy = where_ticks = 0;
    where_on = where_timer != NULL;
}

static int where_order(const void *a, const void *b)
{
    const where_t *x = a, *y = b;
    if (x->pc != y->pc) return x->pc < y->pc ? -1 : 1;
    return x->ra < y->ra ? -1 : x->ra > y->ra;
}

static void where_say(void)
{
    if (!where_timer) return;
    where_on = false;
    wait_ms(2);
    uint32_t n = where_n;
    ESP_LOGI(TAG, "where: %u places, the screen's task at work in %u of %u samples", (unsigned)n, (unsigned)where_busy,
             (unsigned)where_ticks);
    qsort(where, n, sizeof *where, where_order);
    char line[200];
    size_t used = 0;
    for (uint32_t i = 0; i < n;) {
        uint32_t same = 1;
        while (i + same < n && where[i + same].pc == where[i].pc && where[i + same].ra == where[i].ra) same++;
        used += (size_t)snprintf(line + used, sizeof line - used, " %x:%x*%u", (unsigned)where[i].pc, (unsigned)where[i].ra,
                                 (unsigned)same);
        i += same;
        if (used > sizeof line - 28 || i >= n) {
            ESP_LOGI(TAG, "where:%s", line);
            used = 0;
        }
    }
}

static void drag(int x0, int y0, int x1, int y1, int ms)
{
    at_x = x0;
    at_y = y0;
    down = true;
    wait_ms(30);
    for (int t = 0; t <= ms; t += 5) {
        at_x = x0 + (x1 - x0) * t / ms;
        at_y = y0 + (y1 - y0) * t / ms;
        wait_ms(5);
    }
    down = false;
}

static lv_obj_t *find(lv_obj_t *o, const lv_obj_class_t *cls)
{
    if (lv_obj_check_type(o, cls) && !lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN)) return o;
    uint32_t n = lv_obj_get_child_count(o);
    for (uint32_t i = 0; i < n; i++) {
        lv_obj_t *c = lv_obj_get_child(o, i);
        if (lv_obj_has_flag(c, LV_OBJ_FLAG_HIDDEN)) continue;
        lv_obj_t *f = find(c, cls);
        if (f) return f;
    }
    return NULL;
}

/* what is on the screen is changed on LVGL's own task, as a touch would change it */
static void on_ui(lv_async_cb_t fn)
{
    ui_lock();
    lv_async_call(fn, NULL);
    ui_unlock();
}

static void home(void *arg)
{
    kit_close_panel();
    if (ui_views_showing()) ui_views_home();
}

static void settings(void *arg)
{
    ui_show_settings();
    ui_frames_reset(1);
}

static void turn(void *arg)
{
    S.flip = !S.flip;   /* not saved: turned back right after */
    ui_apply_rotation();
}

static void rows_drawn(void *arg)
{
    kit_panel_keep(false);
}

static void rows_kept(void *arg)
{
    kit_panel_keep(true);
}

static void whole(void *arg)
{
    lv_obj_invalidate(lv_screen_active());
}

static void scroll_settings(void)
{
    for (int i = 0; i < 3; i++) {
        drag(WALL_W / 2, WALL_H * 3 / 4, WALL_W / 2, WALL_H / 4, 400);
        wait_ms(900);
        drag(WALL_W / 2, WALL_H / 4, WALL_W / 2, WALL_H * 3 / 4, 400);
        wait_ms(900);
    }
}

static void settings_again(void *arg)
{
    ui_show_settings();
}

/* the frames from here on are counted: those that send this share of the screen or more (0: every one) */
static void from_here(int percent)
{
    ui_lock();
    ui_frames_reset(percent ? (uint32_t)(WALL_W * WALL_H / 100 * percent) : 1);
    ui_unlock();
    where_from_here();
}

static void note(const char *line)
{
    ESP_LOGI(TAG, "%s", line);
    size_t used = strlen(result);
    snprintf(result + used, sizeof result - used, "%s%s", used ? "\n" : "", line);
}

/* how fast the memory the screen is drawn in is by itself: a screen of pixels copied within the PSRAM, as a photo is
 * copied under the wall's text and a panel's picture into a frame. A frame cannot be drawn faster than this. */
static void memory(void)
{
    size_t n = (size_t)WALL_W * WALL_H * 2;
    uint8_t *a = heap_caps_malloc(n, MALLOC_CAP_SPIRAM), *b = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
    if (a && b) {
        memset(a, 0x55, n);
        memset(b, 0, n);
        int64_t t0 = esp_timer_get_time();
        for (int i = 0; i < 4; i++) memcpy(i & 1 ? a : b, i & 1 ? b : a, n);
        unsigned copy = (unsigned)((esp_timer_get_time() - t0) / 4);
        t0 = esp_timer_get_time();
        for (int i = 0; i < 4; i++) memset(a, i, n);
        unsigned fill = (unsigned)((esp_timer_get_time() - t0) / 4);
        volatile uint8_t seen = a[n / 2] ^ b[n / 3];   /* read: the copies and fills are not left out as unused */
        (void)seen;
        char line[120];
        snprintf(line, sizeof line, "A screen of pixels in memory: copied in %u.%u ms, filled in %u.%u", copy / 1000, copy % 1000 / 100,
                 fill / 1000, fill % 1000 / 100);
        note(line);
    }
    heap_caps_free(a);
    heap_caps_free(b);
}

static void say(const char *what)
{
    ui_frames_t f;
    ui_lock();
    ui_frames_get(&f);
    ui_unlock();
    char line[160];
    if (!f.n) {
        snprintf(line, sizeof line, "%s: nothing drawn", what);
    } else {
        unsigned all = f.all / f.n, sending = f.sending / f.n;
        unsigned drawing = all > sending ? all - sending : 0;
        snprintf(line, sizeof line, "%s: %u frames of %u%%, %u.%u ms each (%u.%u drawing, %u.%u sending), slowest %u",
                 what, (unsigned)f.n, (unsigned)((uint64_t)f.px * 100 / f.n / (WALL_W * WALL_H)), all / 1000, all % 1000 / 100,
                 drawing / 1000, drawing % 1000 / 100, sending / 1000, sending % 1000 / 100, (unsigned)((f.worst + 500) / 1000));
    }
    note(line);
    where_say();
}

static void run(void *arg)
{
    wait_ms((int)(intptr_t)arg);
    if (!S.server[0] || !S.token[0]) {
        ESP_LOGI(TAG, "not signed in: nothing to measure");
        running = false;
        vTaskDelete(NULL);
        return;
    }
    result[0] = 0;
    char head[160];
    snprintf(head, sizeof head, "%s %s, %s, memory free: %u K inside, %u K outside", BOARD_NAME, wall_version(),
             S.flip ? "turned around" : "as mounted", (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
             (unsigned)(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024));
    note(head);
    memory();

    ui_lock();
    if (!finger) {
        finger = lv_indev_create();
        lv_indev_set_type(finger, LV_INDEV_TYPE_POINTER);
        lv_indev_set_read_cb(finger, finger_read);
    }
    ui_unlock();
    if (!strncmp(wall_version(), "pr", 2)) on_ui(where_setup);
    on_ui(home);
    wait_ms(1500);

    where_from_here();
    on_ui(settings);
    wait_ms(700);
    say("Settings opens");

    /* and once more: the first time, every letter of it is drawn from its outline */
    on_ui(home);
    wait_ms(1000);
    where_from_here();
    on_ui(settings);
    wait_ms(700);
    say("Settings opens again");

    /* the line in Settings that says how long the redraws took is itself drawn again every second: left out */
    from_here(10);
    scroll_settings();
    say("Settings scrolled");

    /* the same without the picture a panel keeps of its rows (kit_panel): every row drawn at every frame */
    on_ui(rows_drawn);
    wait_ms(300);
    from_here(10);
    scroll_settings();
    say("The same, every row drawn each time");
    on_ui(rows_kept);
    wait_ms(300);

    /* the same with the screen the other way round: on a board that is turned by half a turn only (the 7B), one of
     * the two is sent as drawn and the other through the pixel processor, and the difference is what turning costs */
    on_ui(turn);
    wait_ms(600);
    from_here(10);
    scroll_settings();
    say(S.flip ? "The same, turned around" : "The same, as mounted");
    on_ui(turn);
    wait_ms(600);

    lv_area_t a = {0};
    ui_lock();
    lv_obj_t *sl = find(lv_screen_active(), &lv_slider_class);
    if (sl) lv_obj_get_coords(sl, &a);
    ui_unlock();
    if (sl) {
        int y = (a.y1 + a.y2) / 2, was = S.day_bright;
        from_here(0);
        drag(a.x1 + 40, y, a.x2 - 40, y, 700);
        wait_ms(200);
        drag(a.x2 - 40, y, a.x1 + 40, y, 700);
        wait_ms(200);
        say("The brightness slider dragged");
        ui_lock();
        S.day_bright = was;   /* as it was set */
        settings_save();
        ui_apply_brightness();
        ui_unlock();
    }

    on_ui(home);
    wait_ms(1500);

    from_here(10);
    drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
    wait_ms(1200);
    say("A swipe to a view");
    from_here(10);
    drag(WALL_W / 4, WALL_H / 2, WALL_W * 3 / 4, WALL_H / 2, 200);
    wait_ms(1200);
    say("A swipe back");
    on_ui(home);
    wait_ms(800);

    /* the wall as it stands, all of it, ten times: a photo copied and the text over it, a whole screen sent */
    from_here(10);
    for (int i = 0; i < 10; i++) {
        on_ui(whole);
        wait_ms(150);
    }
    say("The wall drawn whole");

    from_here(10);
    feed_next_photo();
    wait_ms(4000);
    say("The next photo");

    fresh = true;
    on_ui(settings_again);
    ESP_LOGI(TAG, "done");
    running = false;
    vTaskDelete(NULL);
}

void bench_start(int after_ms)
{
    if (running) return;
    running = true;
    if (xTaskCreatePinnedToCore(run, "bench", 6144, (void *)(intptr_t)after_ms, 3, NULL, 1) != pdPASS) running = false;
}

bool bench_running(void)
{
    return running;
}

bool bench_fresh(void)
{
    bool was = fresh;
    fresh = false;
    return was;
}

const char *bench_result(void)
{
    return result;
}
