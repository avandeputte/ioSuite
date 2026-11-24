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
#include "bsp/esp-bsp.h"
#include "driver/gptimer.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/idf_additions.h"
#include "freertos/task.h"
#include "lvgl_private.h"
#include "wall.h"

static const char *TAG = "bench";

static lv_indev_t *finger;          /* the finger that is not there */
static volatile int at_x, at_y;
static volatile bool down;
static volatile bool running, fresh;
#define RESULT_MAX 9000
static char *result;   /* what the last measuring said, a line per scene: in the PSRAM, the memory inside is short */

/* LVGL turns a touch's point with the screen (lv_indev.c): the finger is put where that ends at at_x, at_y */
static void finger_read(lv_indev_t *i, lv_indev_data_t *d)
{
    lv_display_t *disp = lv_indev_get_display(i);
    int w = lv_display_get_original_horizontal_resolution(disp), h = lv_display_get_original_vertical_resolution(disp);
    /* on the screen as it stands now: on a pull request's build the 7B stands on its side for a moment */
    int x = LV_CLAMP(0, at_x, lv_display_get_horizontal_resolution(disp) - 1);
    int y = LV_CLAMP(0, at_y, lv_display_get_vertical_resolution(disp) - 1);
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
 * memcpy, is who called it), and what it was at: between frames, laying one out, drawing, sending. After each scene
 * the places are written to the log as "where:" lines, and
 * tools/where.py names the functions from the build's list of symbols. Without this, what a frame is made of was
 * guessed from a PC's count of the work, which knows nothing of how slow this board's memory is. */
#define WHERE_MAX 2000
typedef struct {
    uint32_t pc, ra;
    uint8_t phase;   /* what the screen's task was at (ui_phase) */
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
        where[where_n].phase = ui_phase;
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
    if (x->ra != y->ra) return x->ra < y->ra ? -1 : 1;
    return (int)x->phase - (int)y->phase;
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
        while (i + same < n && where[i + same].pc == where[i].pc && where[i + same].ra == where[i].ra &&
               where[i + same].phase == where[i].phase) {
            same++;
        }
        used += (size_t)snprintf(line + used, sizeof line - used, " %x:%x:%u*%u", (unsigned)where[i].pc, (unsigned)where[i].ra,
                                 (unsigned)where[i].phase, (unsigned)same);
        i += same;
        if (used > sizeof line - 30 || i >= n) {
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

/* What a frame is made of, in pixels: everything LVGL draws ends in one function (lv_draw_sw_blend, wrapped by the
 * linker: CMakeLists.txt), and what passes through it is counted here as tools/sim counts it on a PC: pixels filled
 * with a colour, copied from a picture, and blended (see-through, or through a mask: text, round corners), and how
 * many pieces they came in. With these a scene that is slow on the board is told apart: more drawn than the PC's
 * count of the same scene says, or the same pixels drawn slower. A panel's rows drawn into its picture are counted
 * on their own. */
typedef struct {
    uint32_t calls;
    uint64_t fill, copy, blend;
} pixels_t;
static pixels_t pixels[2];   /* a frame's drawing; a panel's rows */

void __real_lv_draw_sw_blend(lv_draw_task_t *t, const lv_draw_sw_blend_dsc_t *dsc);

void __wrap_lv_draw_sw_blend(lv_draw_task_t *t, const lv_draw_sw_blend_dsc_t *dsc)
{
    lv_area_t a;
    if (lv_area_intersect(&a, dsc->blend_area, &t->clip_area)) {
        pixels_t *p = &pixels[ui_phase == UI_ROWS];
        uint32_t n = lv_area_get_size(&a);
        bool plain = dsc->opa >= LV_OPA_MAX && !dsc->mask_buf;
        p->calls++;
        if (!dsc->src_buf) *(plain ? &p->fill : &p->blend) += n;
        else if (plain && (dsc->src_color_format == LV_COLOR_FORMAT_RGB565 || dsc->src_color_format == LV_COLOR_FORMAT_RGB888)) p->copy += n;
        else p->blend += n;
    }
    __real_lv_draw_sw_blend(t, dsc);
}

/* the top of what an open panel scrolls: a scene that scrolls begins where the one before it began, however far
 * that one's glides went (they go further the longer a frame takes) */
static void top(void *arg)
{
    lv_obj_t *card = kit_panel_card();
    if (card && lv_obj_get_child_count(card)) lv_obj_scroll_to_y(lv_obj_get_child(card, -1), 0, LV_ANIM_OFF);
}

static void home(void *arg)
{
    kit_close_panel();
    if (ui_views_showing()) ui_views_home();
}

static uint32_t made_us;   /* how long the screen's task took to make what the scene opens, before its first frame */

static void settings(void *arg)
{
    int64_t t0 = esp_timer_get_time();
    ui_show_settings();
    made_us = (uint32_t)(esp_timer_get_time() - t0);
    ui_frames_reset(1);
    memset(pixels, 0, sizeof pixels);
}

static void under_drawn(void *arg)
{
    kit_panel_cull(false);
}

static void under_left(void *arg)
{
    kit_panel_cull(true);
}

static void turn(void *arg)
{
    S.flip = !S.flip;   /* not saved: turned back right after */
    ui_apply_rotation();
}

#if defined(WALL_BOARD_WAVESHARE7B)
/* The 7B stands as the Tab5 does for a moment, on a pull request's build: the Tab5's quarter turns go through the
 * same sending (send.c), which looks at its first frames of each turn and says in the log whether they are in the
 * panel's frame as drawn. The picture is cut off meanwhile: the screens are not laid out for this. */
static void quarter(void *arg)
{
    bsp_display_rotate(lv_display_get_default(), LV_DISPLAY_ROTATION_90);
}

static void quarter_other(void *arg)
{
    bsp_display_rotate(lv_display_get_default(), LV_DISPLAY_ROTATION_270);
}

static void upright(void *arg)
{
    ui_apply_rotation();
}
#endif

#define STRIP_BYTES 96000   /* a strip of a large area, in bytes of pixels: well inside the 256 KB kept at hand */

static void strips_on(void *arg)
{
    kit_bands(STRIP_BYTES);
}

static void strips_off(void *arg)
{
    kit_bands(0);
}

/* The rows of the open panel that are in view, drawn into its picture: in one piece and in strips of fewer and fewer
 * rows, three times each and turn about, so that whatever else the board is doing meanwhile falls on all alike. */
static const int rows_strip[] = {0, 128, 64, 32, 16};
static uint32_t rows_us[sizeof rows_strip / sizeof *rows_strip];

static volatile bool rows_done;

static void rows_ab(void *arg)
{
    memset(rows_us, 0, sizeof rows_us);
    for (int r = 0; r < 3; r++) {
        for (size_t k = 0; k < sizeof rows_strip / sizeof *rows_strip; k++) rows_us[k] += kit_panel_rows_us(rows_strip[k]) / 3;
    }
    rows_done = true;
}

static void note(const char *line);

static void rows_say(void)
{
    char line[200];
    rows_done = false;
    on_ui(rows_ab);
    for (int i = 0; i < 100 && !rows_done; i++) wait_ms(100);
    int used = snprintf(line, sizeof line, "A panel's rows drawn into its picture: in one piece %u.%u ms", (unsigned)(rows_us[0] / 1000),
                        (unsigned)(rows_us[0] % 1000 / 100));
    for (size_t k = 1; k < sizeof rows_strip / sizeof *rows_strip && used > 0 && used < (int)sizeof line; k++) {
        used += snprintf(line + used, sizeof line - (size_t)used, "%s of %d rows %u.%u", k == 1 ? "; in strips" : ",", rows_strip[k],
                         (unsigned)(rows_us[k] / 1000), (unsigned)(rows_us[k] % 1000 / 100));
    }
    note(line);
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
    memset(pixels, 0, sizeof pixels);
    ui_unlock();
    where_from_here();
}

static void note(const char *line)
{
    ESP_LOGI(TAG, "%s", line);
    if (!result) return;
    size_t used = strlen(result);
    snprintf(result + used, RESULT_MAX - used, "%s%s", used ? "\n" : "", line);
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
    char line[460];
    if (!f.n) {
        snprintf(line, sizeof line, "%s: nothing drawn", what);
    } else {
        unsigned all = f.all / f.n, sending = f.sending / f.n, beside = f.beside / f.n, layout = f.layout / f.n, rows = f.rows / f.n;
        unsigned drawing = all > sending + layout + rows ? all - sending - layout - rows : 0;
        int used = snprintf(line, sizeof line,
                            "%s: %u frames of %u%%, %u.%u ms each (%u.%u laying out, %u.%u rows, %u.%u drawing, %u.%u sending), slowest %u",
                            what, (unsigned)f.n, (unsigned)((uint64_t)f.px * 100 / f.n / (WALL_W * WALL_H)), all / 1000,
                            all % 1000 / 100, layout / 1000, layout % 1000 / 100, rows / 1000, rows % 1000 / 100, drawing / 1000,
                            drawing % 1000 / 100, sending / 1000, sending % 1000 / 100, (unsigned)((f.worst + 500) / 1000));
        /* a turned screen: each frame is turned beside the drawing of the next (send.c), which a frame's own time
         * shows only as its wait for the one before */
        if (beside && used > 0 && used < (int)sizeof line) {
            used += snprintf(line + used, sizeof line - (size_t)used, "; turned beside the next in %u.%u", beside / 1000,
                             beside % 1000 / 100);
        }
        if (made_us && used > 0 && used < (int)sizeof line) {
            used += snprintf(line + used, sizeof line - (size_t)used, "; made in %u.%u before that", (unsigned)(made_us / 1000),
                             (unsigned)(made_us % 1000 / 100));
        }
        if (used > 0 && used < (int)sizeof line) {
            used += snprintf(line + used, sizeof line - (size_t)used, "; %u K free inside",
                             (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024));
        }
        /* the pixels of a frame, in hundredths of a screen */
        for (int k = 0; k < 2; k++) {
            const pixels_t *p = &pixels[k];
            uint64_t scr = (uint64_t)WALL_W * WALL_H * f.n;
            if (!p->calls || used <= 0 || used >= (int)sizeof line) continue;
            unsigned fill = (unsigned)(p->fill * 100 / scr), copy = (unsigned)(p->copy * 100 / scr), blend = (unsigned)(p->blend * 100 / scr);
            used += snprintf(line + used, sizeof line - (size_t)used, "; %s %u.%02u screens filled, %u.%02u copied, %u.%02u blended in %u pieces",
                             k ? "its rows:" : "a frame:", fill / 100, fill % 100, copy / 100, copy % 100, blend / 100, blend % 100,
                             (unsigned)(p->calls / f.n));
        }
    }
    made_us = 0;
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
    if (!result) result = heap_caps_malloc(RESULT_MAX, MALLOC_CAP_SPIRAM);
    if (result) result[0] = 0;
    char head[200];
    snprintf(head, sizeof head, "%s %s, %s%s, memory free: %u K inside, %u K outside", BOARD_NAME, wall_version(),
             S.flip ? "turned around" : "as mounted", send_beside() ? "" : " (turned frames sent the board package's way)",
             (unsigned)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
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
    rows_say();

    /* and with the wall under its card drawn too, as LVGL does by itself */
    on_ui(home);
    on_ui(under_drawn);
    wait_ms(1000);
    where_from_here();
    on_ui(settings);
    wait_ms(700);
    say("Settings opens, the wall drawn under it");
    on_ui(under_left);

    /* the line in Settings that says how long the redraws took is itself drawn again every second: left out */
    from_here(10);
    scroll_settings();
    say("Settings scrolled");

    /* the same without the picture a panel keeps of its rows (kit_panel): every row drawn at every frame */
    on_ui(top);
    on_ui(rows_drawn);
    wait_ms(300);
    from_here(10);
    scroll_settings();
    say("The same, every row drawn each time");
    /* and each frame of that in strips */
    on_ui(top);
    on_ui(strips_on);
    wait_ms(300);
    from_here(10);
    scroll_settings();
    say("The same, every row drawn each time, in strips");
    on_ui(strips_off);
    on_ui(rows_kept);
    wait_ms(300);
    rows_say();

    /* the same with the screen the other way round: on a board that is turned by half a turn only (the 7B), one of
     * the two is sent as drawn and the other through the pixel processor, and the difference is what turning costs */
    on_ui(top);
    on_ui(turn);
    wait_ms(600);
    from_here(10);
    scroll_settings();
    say(S.flip ? "The same, turned around" : "The same, as mounted");
    on_ui(turn);
    on_ui(top);
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
    /* and once more: the first time, the view's letters are drawn from their outlines */
    from_here(10);
    drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
    wait_ms(1200);
    say("A swipe to the view again");
    drag(WALL_W / 4, WALL_H / 2, WALL_W * 3 / 4, WALL_H / 2, 200);
    wait_ms(1200);
    on_ui(strips_on);
    from_here(10);
    drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
    wait_ms(1200);
    say("A swipe to the view once more, drawn in strips");
    from_here(10);
    drag(WALL_W / 4, WALL_H / 2, WALL_W * 3 / 4, WALL_H / 2, 200);
    wait_ms(1200);
    say("A swipe back, drawn in strips");
    on_ui(strips_off);
    on_ui(home);
    wait_ms(800);

    /* the wall as it stands, all of it, ten times: a photo copied and the text over it, a whole screen sent */
    from_here(10);
    for (int i = 0; i < 10; i++) {
        on_ui(whole);
        wait_ms(150);
    }
    say("The wall drawn whole");
    on_ui(strips_on);
    from_here(10);
    for (int i = 0; i < 10; i++) {
        on_ui(whole);
        wait_ms(150);
    }
    say("The wall drawn whole, in strips");
    on_ui(strips_off);

    from_here(10);
    feed_next_photo();
    wait_ms(7000);   /* fetched, unpacked and faded in */
    say("The next photo");

#if defined(WALL_BOARD_WAVESHARE7B)
    if (!strncmp(wall_version(), "pr", 2)) {
        on_ui(quarter);
        wait_ms(700);
        on_ui(whole);
        wait_ms(500);
        on_ui(quarter_other);
        wait_ms(700);
        on_ui(whole);
        wait_ms(500);
        on_ui(upright);
        wait_ms(700);
        ESP_LOGI(TAG, "stood on its side both ways for a moment and back");
    }
#endif

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
    if (xTaskCreatePinnedToCore(run, "bench", 8192, (void *)(intptr_t)after_ms, 3, NULL, 1) != pdPASS) running = false;
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
    return result ? result : "";
}
