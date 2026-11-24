/* The wall display's screens on a PC: LVGL 9.3 drawing into memory as on the device (RGB565, partial refresh into a
 * whole-screen buffer), the firmware's own ui*.c, feed.c and alarm.c, and stand-ins for what the board gives. It
 * counts what each scripted touch costs: frames drawn, pixels filled, copied and blended, and the time LVGL took. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "lvgl.h"
#include "src/misc/lv_area_private.h"
#include "src/draw/lv_draw_private.h"
#include "src/draw/sw/blend/lv_draw_sw_blend_private.h"
#include "wall.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/jpeg_decode.h"

int sim_quiet = 1, sim_notified;
/* what a run of the board's own measuring leaves in Settings (bench.c) */
static const char *sim_bench = "Settings opens: 2 frames of 100% of the screen, 80.1 ms each (61.0 drawing, 19.1 sending), the slowest 120\n"
                               "Settings scrolled: 150 frames of 61% of the screen, 44.8 ms each (30.1 drawing, 14.7 sending), the slowest 61";
static uint32_t now_ms = 1000;
static lv_display_t *disp;
static lv_indev_t *indev;
static uint16_t *fb;            /* what the panel shows */
static int touch_x, touch_y;
static bool touch_down;

/* ------------------------------------------------------------------ counters */

static int verbose;
static struct {
    uint64_t fill, copy, blend, flushed;
    int frames, flushes;
    double cpu;
    double worst;
} C;

void __real_lv_draw_sw_blend(lv_draw_task_t *t, const lv_draw_sw_blend_dsc_t *dsc);
void __wrap_lv_draw_sw_blend(lv_draw_task_t *t, const lv_draw_sw_blend_dsc_t *dsc)
{
    lv_area_t a;
    if (lv_area_intersect(&a, dsc->blend_area, &t->clip_area)) {
        uint64_t n = (uint64_t)lv_area_get_size(&a);
        bool plain = dsc->opa >= LV_OPA_MAX && !dsc->mask_buf;
        if (dsc->src_buf) {
            bool alpha = dsc->src_color_format != LV_COLOR_FORMAT_RGB565 && dsc->src_color_format != LV_COLOR_FORMAT_RGB888;
            if (plain && !alpha) C.copy += n; else C.blend += n;
        } else if (plain) C.fill += n;
        else C.blend += n;
    }
    __real_lv_draw_sw_blend(t, dsc);
}

static double not_lvgl;   /* time spent in here on the simulator's own checks, taken off what LVGL is said to take */

static double cpu_now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static void flush(lv_display_t *d, const lv_area_t *a, uint8_t *px)
{
    int w = lv_area_get_width(a), h = lv_area_get_height(a);
    const uint16_t *src = (const uint16_t *)px;
    for (int y = 0; y < h; y++) memcpy(fb + (size_t)(a->y1 + y) * WALL_W + a->x1, src + (size_t)y * w, (size_t)w * 2);
    C.flushed += (uint64_t)w * h;
    C.flushes++;
    if (verbose) printf("    %u ms: sent %d,%d %dx%d\n", now_ms, a->x1, a->y1, w, h);
    /* what the next area does not draw shows as magenta: nothing may be left undrawn */
    double t0 = cpu_now();
    uint16_t *poison = (uint16_t *)px;
    for (size_t i = 0; i < (size_t)w * h; i++) poison[i] = 0xF81F;
    not_lvgl += cpu_now() - t0;
    lv_display_flush_ready(d);
}

static void on_render(lv_event_t *e) { C.frames++; }

static void touch_read(lv_indev_t *i, lv_indev_data_t *d)
{
    d->point.x = touch_x;
    d->point.y = touch_y;
    d->state = touch_down ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

static uint32_t tick(void) { return now_ms; }
/* the time of day is the script's too (a Monday afternoon): the same pictures at every run, to compare two */
time_t time(time_t *t)
{
    time_t v = 1795446000 + now_ms / 1000;
    if (t) *t = v;
    return v;
}

/* ------------------------------------------------------------------ what the board gives */

bool bsp_display_lock(uint32_t t) { return true; }
void bsp_display_unlock(void) {}
void bsp_display_backlight_on(void) {}
void bsp_display_backlight_off(void) {}
void bsp_display_brightness_set(int pct) {}
void bsp_display_rotate(lv_display_t *d, lv_display_rotation_t r) {}
lv_indev_t *bsp_display_get_input_dev(void) { return indev; }
void *bsp_audio_codec_speaker_init(void) { return NULL; }
void *bsp_i2c_get_handle(void) { return NULL; }
int64_t esp_timer_get_time(void) { return (int64_t)now_ms * 1000; }
void vTaskDelay(TickType_t t) {}

/* the taps' queue: run from the main loop, as the taps' task does on the device */
typedef struct { void (*fn)(void *); void *arg; } sim_job_t;
static sim_job_t queue[32];
static int nqueue;
/* the taps' jobs are queue 1 (run in step()); any other queue is the sound's */
QueueHandle_t xQueueCreate(int n, int size) { return (QueueHandle_t)(intptr_t)(size == (int)sizeof(sim_job_t) ? 1 : 2); }
BaseType_t xQueueSend(QueueHandle_t q, const void *item, TickType_t t)
{
    if (q != (QueueHandle_t)1) return pdTRUE;   /* the sound's queue: nothing to play here */
    if (nqueue < 32) memcpy(&queue[nqueue++], item, sizeof(sim_job_t));
    return pdTRUE;
}
BaseType_t xQueueReceive(QueueHandle_t q, void *item, TickType_t t) { return pdFALSE; }

/* settings.c */
wall_settings_t S;
uint32_t VIEWS_OFF;
int sim_saves;
void settings_load(void) {}
void settings_save(void) { sim_saves++; }
void settings_save_views(void) { sim_saves++; }
void settings_forget_sign_in(void) {}
void settings_reset(void) {}

/* net.c */
net_state_t net_state(void) { return NET_UP; }
const char *net_ip(void) { return "192.168.1.57"; }
const char *net_why(void) { return ""; }
int net_scan(net_ap_t *out, int max) { return 0; }
void net_init(void) {}
void net_connect(const char *ssid, const char *pass) {}
bool clock_is_set(void) { return true; }
void clock_set_zone(const char *posix) {}

/* ota.c */
void bench_start(int after_ms) {}
bool bench_running(void) { return false; }
bool bench_fresh(void) { return false; }
const char *bench_result(void) { return sim_bench; }
void ota_start(void) {}
void ota_check_now(bool install) {}
ota_state_t ota_state(void) { return OTA_NONE; }
const char *ota_text(void) { return "Up to date (2.2)"; }
const char *wall_version(void) { return "2.2"; }

/* api.c: the start page's answers from files */
static char *slurp(const char *name, size_t *len)
{
    char path[256];
    snprintf(path, sizeof path, "data/%s", name);
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *b = malloc(n + 1);
    if (fread(b, 1, n, f) != (size_t)n) n = 0;
    b[n] = 0;
    fclose(f);
    *len = n;
    return b;
}

int sim_requests;
const char *sim_feed_file = "feed.json";
api_resp_t api_request_auth(const char *method, const char *path, const char *body, size_t max, const char *base, const char *authorization)
{
    api_resp_t r = {0};
    sim_requests++;
    char name[64] = "";
    if (!strncmp(path, "/api/wall/feed", 14)) strcpy(name, sim_feed_file);
    else if (!strncmp(path, "/api/wall/photo/", 16)) strcpy(name, "feed.json");   /* any bytes: the decoder here makes its own picture */
    else if (!strcmp(path, "/api/trmnl")) strcpy(name, "trmnl.json");
    else if (!strncmp(path, "/api/trmnl/", 11)) {
        snprintf(name, sizeof name, "%s", path + 11);
        char *q = strchr(name, '?');
        if (q) *q = 0;
        strcat(name, ".json");
    }
    if (!strcmp(method, "POST")) { r.status = 200; r.body = strdup("{}"); r.len = 2; return r; }
    r.body = name[0] ? slurp(name, &r.len) : NULL;
    r.status = r.body ? 200 : 404;
    if (!r.body) { r.body = strdup(""); strcpy(r.why, "The start page answered 404"); }
    return r;
}
api_resp_t api_request(const char *method, const char *path, const char *body, size_t max, const char *base)
{
    return api_request_auth(method, path, body, max, base, NULL);
}
void api_free(api_resp_t *r) { free(r->body); r->body = NULL; }
bool api_normalize(const char *in, char *out, size_t n) { snprintf(out, n, "http://%s", in); return true; }

/* the JPEG engine: a picture made here, bright at the top, dark below, with detail in it */
static int photo_no;
int jpeg_new_decoder_engine(const jpeg_decode_engine_cfg_t *c, jpeg_decoder_handle_t *h) { *h = (void *)1; return 0; }
void *jpeg_alloc_decoder_mem(size_t n, const jpeg_decode_memory_alloc_cfg_t *c, size_t *got) { *got = n; return malloc(n); }
int jpeg_decoder_get_info(const uint8_t *in, size_t n, jpeg_decode_picture_info_t *info) { info->width = WALL_W; info->height = WALL_H; return 0; }
int jpeg_decoder_process(jpeg_decoder_handle_t h, const jpeg_decode_cfg_t *c, const uint8_t *in, size_t n, uint8_t *out, size_t outn, uint32_t *got)
{
    int w = (WALL_W + 15) & ~15;
    uint16_t *p = (uint16_t *)out;
    photo_no++;
    for (int y = 0; y < WALL_H; y++) {
        for (int x = 0; x < w; x++) {
            int r = 40 + (x * 150 / w) + ((x / 37 + y / 29 + photo_no) % 5) * 8;
            int g = 150 - y * 110 / WALL_H + ((x / 53) % 3) * 12 + (photo_no % 3) * 20;
            int b = 190 - y * 150 / WALL_H + ((y / 41) % 4) * 9;
            r = r > 255 ? 255 : r; g = g < 0 ? 0 : g > 255 ? 255 : g; b = b < 0 ? 0 : b;
            p[(size_t)y * w + x] = (uint16_t)((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3));
        }
    }
    return 0;
}

/* the feed's own code, with its tasks left out: the script calls what they would */
#include "feed.c"

/* ------------------------------------------------------------------ the script's tools */

static void save(const char *name, const uint16_t *px)
{
    char path[256];
    snprintf(path, sizeof path, "out/%s.ppm", name);
    FILE *f = fopen(path, "wb");
    fprintf(f, "P6\n%d %d\n255\n", WALL_W, WALL_H);
    for (int i = 0; i < WALL_W * WALL_H; i++) {
        uint16_t p = px[i];
        uint8_t rgb[3] = {(uint8_t)((p >> 11) * 255 / 31), (uint8_t)(((p >> 5) & 63) * 255 / 63), (uint8_t)((p & 31) * 255 / 31)};
        fwrite(rgb, 1, 3, f);
    }
    fclose(f);
}

/* SIM_FRAMES=file: a line per frame drawn, the time and a sum over every pixel on the screen then, and the script
 * goes on with a few hundred touches all over the panels. Two runs that must show the same (run.sh check: a panel
 * with and without the picture it keeps of its rows, kit_panel) are compared by these lines; SIM_SHOT_AT=ms saves
 * the screen as it is at that time (out/at-<ms>.ppm), to look at a frame that differs. */
static FILE *frames_to;
static uint32_t shot_at;

static void frame_drawn(void)
{
    uint32_t h = 2166136261u;
    for (int i = 0; i < WALL_W * WALL_H; i++) h = (h ^ fb[i]) * 16777619u;
    fprintf(frames_to, "%u %08x\n", now_ms, h);
}

static int rnd(uint32_t *seed)
{
    *seed = *seed * 1664525u + 1013904223u;
    return (int)(*seed >> 8);
}

static void step(void)
{
    double t0 = cpu_now();
    not_lvgl = 0;
    int frames = C.frames;
    lv_timer_handler();
    double dt = cpu_now() - t0 - not_lvgl;
    C.cpu += dt;
    if (dt > C.worst) C.worst = dt;
    if (frames_to && C.frames != frames) frame_drawn();
    if (shot_at && now_ms >= shot_at) {
        char name[32];
        snprintf(name, sizeof name, "at-%u", now_ms);
        save(name, fb);
        shot_at = 0;
    }
    while (nqueue) {
        sim_job_t j = queue[0];
        memmove(queue, queue + 1, (size_t)(--nqueue) * sizeof j);
        j.fn(j.arg);
    }
    now_ms += 5;
}

static void run(int ms) { for (int i = 0; i < ms / 5; i++) step(); }

static void tap(int x, int y)
{
    touch_x = x; touch_y = y; touch_down = true;
    run(80);
    touch_down = false;
    run(60);
}

static void drag(int x0, int y0, int x1, int y1, int ms)
{
    int n = ms / 5;
    touch_x = x0; touch_y = y0; touch_down = true;
    run(40);
    for (int i = 1; i <= n; i++) {
        touch_x = x0 + (x1 - x0) * i / n;
        touch_y = y0 + (y1 - y0) * i / n;
        step();
    }
    run(40);
    touch_down = false;
}

static void shot(const char *name)
{
    save(name, fb);
    int bad = 0;
    for (int i = 0; i < WALL_W * WALL_H; i++) bad += fb[i] == 0xF81F;
    if (bad) printf("!!! %s: %d pixels were never drawn\n", name, bad);
}

static void reset(void) { memset(&C, 0, sizeof C); }

/* what the stretch since reset() cost: frames, and per frame the pixels touched as a share of the screen */
static void report(const char *what)
{
    double scr = (double)WALL_W * WALL_H;
    int f = C.frames ? C.frames : 1;
    printf("%-44s %4d frames  %7.1f ms (%5.2f a frame, worst %5.1f)  per frame: fill %5.2f  copy %5.2f  blend %5.2f  sent %5.2f screens\n",
           what, C.frames, C.cpu, C.cpu / f, C.worst, C.fill / scr / f, C.copy / scr / f, C.blend / scr / f, C.flushed / scr / f);
}

static lv_obj_t *find_in(lv_obj_t *o, const lv_obj_class_t *cls, int *skip)
{
    if (lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN)) return NULL;
    if (lv_obj_check_type(o, cls) && (*skip)-- == 0) return o;
    for (uint32_t i = 0; i < lv_obj_get_child_count(o); i++) {
        lv_obj_t *r = find_in(lv_obj_get_child(o, i), cls, skip);
        if (r) return r;
    }
    return NULL;
}

/* the nth object of a class on the screen or over it */
static lv_obj_t *find(const lv_obj_class_t *cls, int nth)
{
    int skip = nth;
    lv_obj_t *r = find_in(lv_screen_active(), cls, &skip);
    if (!r) r = find_in(lv_layer_top(), cls, &skip);
    return r;
}

static void center(lv_obj_t *o, int *x, int *y)
{
    lv_area_t a;
    lv_obj_get_coords(o, &a);
    *x = (a.x1 + a.x2) / 2;
    *y = (a.y1 + a.y2) / 2;
}

static void new_photo(void)
{
    wall_photo_t p = FEED->photos[photo_no % (FEED->nphotos ? FEED->nphotos : 1)];
    photo_setup();
    show_photo(&p);
}

/* ------------------------------------------------------------------ the script */

int main(int argc, char **argv)
{
    const char *only = argc > 1 ? argv[1] : "";
    verbose = !strcmp(only, "-v");
    if (getenv("SIM_LOG")) sim_quiet = 0;   /* the firmware's own log lines as well */
    if (getenv("SIM_FRAMES")) frames_to = fopen(getenv("SIM_FRAMES"), "w");
    if (getenv("SIM_SHOT_AT")) shot_at = (uint32_t)atoi(getenv("SIM_SHOT_AT"));
    if (getenv("SIM_KEEP")) kit_panel_keep(atoi(getenv("SIM_KEEP")) != 0);
    if (getenv("SIM_CULL")) kit_panel_cull(atoi(getenv("SIM_CULL")) != 0);
    if (getenv("SIM_BANDS")) kit_bands(atoi(getenv("SIM_BANDS")));
    lv_init();
    lv_tick_set_cb(tick);
    fb = calloc((size_t)WALL_W * WALL_H, 2);
    disp = lv_display_create(WALL_W, WALL_H);
    size_t bytes = (size_t)WALL_W * WALL_H * 2;
    lv_display_set_buffers(disp, malloc(bytes), malloc(bytes), bytes, LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush);
    lv_display_add_event_cb(disp, on_render, LV_EVENT_RENDER_START, NULL);
    indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, touch_read);

    memset(&S, 0, sizeof S);
    strcpy(S.ssid, "Home");
    strcpy(S.server, "https://start.example.net");
    strcpy(S.token, "x");
    strcpy(S.user, "morgan");
    S.night_from = S.night_to = 0;
    S.day_bright = 90; S.night_bright = 12; S.volume = 70; S.auto_update = true; S.snooze_min = 9;
    S.alarms[0] = (wall_alarm_t){.hour = 7, .minute = 0, .days = 0x3e, .on = true, .label = "Weekdays"};
    setenv("TZ", "EST5EDT,M3.2.0,M11.1.0", 1);
    tzset();

    feed_init();
    alarm_start();
    ui_start(disp);
    run(200);

    reset();
    fetch_once();
    views_poll();
    run(300);
    report("the first feed");
    reset();
    new_photo();
    run(1500);
    report("a photo fades in");
    shot("wall");

    reset();
    run(10000);
    report("the wall left alone, 10 s");

    reset();
    fetch_once();
    views_poll();
    run(300);
    report("the next feed, nothing new in it");

    /* the bar, then Settings */
    reset();
    tap(WALL_W / 2, WALL_H / 2 - P(160));
    run(300);
    report("a tap on the photo: the bar");
    shot("bar");
    reset();
    ui_show_settings();
    run(400);
    report("Settings opens");
    shot("settings");

    reset();
    run(5000);
    report("Settings left open, 5 s");

    int x, y;
    reset();
    drag(WALL_W / 2, WALL_H * 3 / 4, WALL_W / 2, WALL_H / 4, 400);
    run(1200);
    report("Settings scrolled up (a drag and its glide)");
    shot("settings-scrolled");
    reset();
    drag(WALL_W / 2, WALL_H / 4, WALL_W / 2, WALL_H * 3 / 4, 400);
    run(1200);
    report("Settings scrolled back");

    lv_obj_t *sl = find(&lv_slider_class, 0);
    if (sl) {
        lv_area_t a;
        lv_obj_get_coords(sl, &a);
        reset();
        drag(a.x1 + 40, (a.y1 + a.y2) / 2, a.x2 - 40, (a.y1 + a.y2) / 2, 600);
        run(200);
        report("the brightness slider dragged across");
    }
    lv_obj_t *sw = find(&lv_switch_class, 0);
    if (sw) {
        center(sw, &x, &y);
        reset();
        tap(x, y);
        run(400);
        report("the 24-hour switch tapped");
        tap(x, y);
        run(400);
    }
    reset();
    kit_close_panel();
    run(300);
    report("Settings closes");

    /* the other panels */
    reset();
    ui_open_alarms();
    run(300);
    report("Alarms opens");
    shot("alarms");
    kit_close_panel();
    reset();
    ui_open_timers();
    run(300);
    report("Timers opens");
    timer_add(300, "");
    reset();
    run(5000);
    report("Timers open with one running, 5 s");
    shot("timers");
    kit_close_panel();
    timer_cancel(0);
    run(1200);
    reset();
    ui_open_add();
    run(300);
    report("Add opens");
    lv_obj_t *kb = find(&lv_keyboard_class, 0);
    if (kb) {
        lv_area_t a;
        lv_obj_get_coords(kb, &a);
        reset();
        for (int i = 0; i < 8; i++) tap(a.x1 + (a.x2 - a.x1) * (2 + i) / 12, a.y1 + (a.y2 - a.y1) * 3 / 8);
        report("eight keys typed");
        touch_x = a.x1 + (a.x2 - a.x1) * 5 / 12; touch_y = a.y1 + (a.y2 - a.y1) * 3 / 8; touch_down = true;
        run(80);
        shot("add-key-down");
        touch_down = false;
        run(60);
    }
    shot("add");
    kit_close_panel();
    run(200);
    reset();
    ui_open_event(&FEED->today[1]);
    run(300);
    report("an event opens");
    shot("event");
    kit_close_panel();
    run(200);

    /* the views */
    views_poll();
    run(100);
    reset();
    drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
    run(1500);
    report("a swipe to the first view");
    shot("view-calendar");
    for (int i = 0; i < 5; i++) {
        reset();
        drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
        run(1500);
        char name[40];
        snprintf(name, sizeof name, "a swipe to view %d", i + 2);
        report(name);
        snprintf(name, sizeof name, "view-%d", i + 2);
        shot(name);
    }
    reset();
    fetch_once();
    views_poll();
    run(300);
    report("a feed while a view shows");
    reset();
    drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
    run(1500);
    report("a swipe back to the wall");
    shot("wall-again");

    reset();
    new_photo();
    run(1500);
    report("the next photo fades in");

    /* the week, and a task ticked */
    reset();
    lv_obj_t *l = NULL;
    for (int i = 0; (l = find(&lv_label_class, i)); i++) {
        if (!strcmp(lv_label_get_text(l), "Week")) break;
    }
    if (l) {
        center(l, &x, &y);
        tap(x, y);
        run(300);
        report("a tap on Week");
        shot("week");
        reset();
        drag(P(300), WALL_H - P(120), P(300), P(320), 300);
        run(1000);
        report("the week scrolled");
    }
    /* the corners: two photos in a row, no photo (the sky), a panel and a view over the sky, black */
    new_photo();
    run(300);
    new_photo();
    run(100);
    shot("edge-two-photos-fading");
    run(1500);
    shot("edge-two-photos");
    ui_lock();
    ui_wall_photo(NULL, "");
    has_shown = false;
    ui_unlock();
    run(300);
    shot("edge-sky");
    ui_show_settings();
    run(300);
    shot("edge-sky-settings");
    kit_close_panel();
    run(200);
    drag(WALL_W * 3 / 4, WALL_H / 2, WALL_W / 4, WALL_H / 2, 200);
    run(600);
    shot("edge-sky-view");
    new_photo();
    run(1500);
    shot("edge-view-photo");
    drag(WALL_W / 4, WALL_H / 2, WALL_W * 3 / 4, WALL_H / 2, 200);
    run(600);
    shot("edge-back-from-view");
    strcpy(FEED->bg, "black");
    ui_wall_photo(NULL, "");
    ui_wall_feed_changed();
    run(300);
    shot("edge-black");
    strcpy(FEED->bg, "photos");
    ui_wall_feed_changed();
    run(100);
    shot("edge-sky-again");
    new_photo();
    run(400);
    shot("edge-photo-over-sky-fading");
    run(1200);
    ui_show_settings();
    run(300);
    drag(WALL_W / 2, WALL_H * 3 / 4, WALL_W / 2, WALL_H / 4, 200);
    run(1500);
    lv_obj_scroll_to_y(lv_obj_get_child(lv_obj_get_child(kit_panel_layer(), 0), 1), 4000, LV_ANIM_OFF);
    run(1200);
    shot("settings-bottom");
    kit_close_panel();
    run(300);
    /* a photo that comes while Settings is open */
    ui_show_settings();
    run(300);
    reset();
    new_photo();
    run(1500);
    report("a photo comes while Settings is open");
    shot("settings-new-photo");
    kit_close_panel();
    run(300);
    /* a task ticked, a switch tapped: only their own parts */
    reset();
    FEED->tasks[0].done = true;
    ui_wall_feed_changed();
    run(200);
    report("a task ticked");
    reset();
    FEED->temp++;
    ui_wall_feed_changed();
    run(200);
    report("one degree warmer");
    shot("edge-end");
    /* a timer running on the wall, 5 s */
    timer_add(300, "Tea");
    run(1200);
    reset();
    run(5000);
    report("a timer running on the wall, 5 s");
    shot("edge-timer");
    /* a minute passes */
    reset();
    run(61000);
    report("a minute on the wall (61 s)");
    (void)only;
    if (!frames_to) return 0;

    /* the check's own part: the panels scrolled, dragged and tapped all over, a few hundred times; every frame of it
     * is compared in step() */
    uint32_t seed = 12345;
#define RND(n) (rnd(&seed) % (n))
    timer_add(900, "Eggs");
    for (int i = 0; i < 400; i++) {
        if (!kit_panel_open() || i % 80 == 0) {
            if (ui_views_showing()) ui_views_home();
            ui_show_wall();
            run(100);
            switch (i / 80 % 5) {
            case 0: ui_show_settings(); break;
            case 1: ui_open_timers(); break;
            case 2: ui_open_alarms(); break;
            case 3: ui_open_add(); break;
            default: ui_open_event(&FEED->today[1]); break;
            }
            run(200);
        }
        int kind = RND(10);
        int x0 = WALL_W / 8 + RND(WALL_W * 3 / 4), y0 = WALL_H / 5 + RND(WALL_H * 7 / 10);
        if (kind < 6) {          /* a scroll, short or long, slow or flicked, at times let go before it ends */
            int y1 = y0 + RND(WALL_H) - WALL_H / 2;
            drag(x0, y0, x0, y1 < 0 ? 0 : y1 >= WALL_H ? WALL_H - 1 : y1, 60 + RND(500));
            run(RND(4) ? 60 + RND(900) : 10);
        } else if (kind < 9) {   /* a tap wherever: a switch, a button, a chip, a field, nothing */
            tap(x0, y0);
            run(RND(600));
        } else {                 /* a drag sideways: a slider when on one */
            int x1 = x0 + RND(WALL_W / 2) - WALL_W / 4;
            drag(x0, y0, x1 < 0 ? 0 : x1 >= WALL_W ? WALL_W - 1 : x1, y0, 100 + RND(300));
            run(200);
        }
        if (i % 40 == 39) fetch_once();   /* and the minute's feed behind it */
    }
    fclose(frames_to);
    return 0;
}
