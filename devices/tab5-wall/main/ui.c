/* What every screen shares: the lock, the fonts (Inter, drawn at any size by Tiny TTF, with LVGL's Montserrat behind
 * it for the symbols), the brightness and the night, the screen's turn, a toast, and times and dates as people read
 * them. */
#include <string.h>
#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "lvgl_private.h"   /* a panel draws its content into a picture of its own (kit_panel) */
#include "icons.h"
#include "wall.h"

extern const uint8_t inter_regular_start[] asm("_binary_Inter_Regular_ttf_start");
extern const uint8_t inter_regular_end[] asm("_binary_Inter_Regular_ttf_end");
extern const uint8_t inter_bold_start[] asm("_binary_Inter_SemiBold_ttf_start");
extern const uint8_t inter_bold_end[] asm("_binary_Inter_SemiBold_ttf_end");
extern const uint8_t inter_light_start[] asm("_binary_InterDisplay_Light_ttf_start");
extern const uint8_t inter_light_end[] asm("_binary_InterDisplay_Light_ttf_end");

static lv_display_t *DISP;

void ui_lock(void) { bsp_display_lock(0); }
void ui_unlock(void) { bsp_display_unlock(); }

/* ------------------------------------------------------------------ fonts */

typedef struct {
    int kind, px;
    lv_font_t *f;
} font_slot_t;

static font_slot_t fonts[48];   /* every size the screens ask for: one past the last would be made anew each time */
static int nfonts;

/* px: on this screen already */
static const lv_font_t *symbols_for(int px)
{
    if (px >= 44) return &lv_font_montserrat_48;
    if (px >= 32) return &lv_font_montserrat_36;
    if (px >= 26) return &lv_font_montserrat_28;
    if (px >= 22) return &lv_font_montserrat_24;
    if (px >= 18) return &lv_font_montserrat_20;
    return &lv_font_montserrat_16;
}

const lv_font_t *font_symbols(int px) { return symbols_for(P(px)); }

/* A symbol (LV_SYMBOL_…: Unicode's private use area) is not in Inter: sent straight on to the font behind it. Asked of
 * the TrueType font it is looked up in the font file, not found and logged, every time it is measured or drawn. */
static bool (*ttf_glyph_dsc)(const lv_font_t *, lv_font_glyph_dsc_t *, uint32_t, uint32_t);

static bool glyph_dsc(const lv_font_t *f, lv_font_glyph_dsc_t *out, uint32_t letter, uint32_t next)
{
    if (letter >= 0xE000 && letter <= 0xF8FF) return false;
    return ttf_glyph_dsc(f, out, letter, next);
}

static const lv_font_t *font_of(int kind, int px)
{
    px = P(px);
    for (int i = 0; i < nfonts; i++) {
        if (fonts[i].kind == kind && fonts[i].px == px) return fonts[i].f;
    }
    const uint8_t *a = kind == 0 ? inter_regular_start : kind == 1 ? inter_bold_start : inter_light_start;
    const uint8_t *b = kind == 0 ? inter_regular_end : kind == 1 ? inter_bold_end : inter_light_end;
    /* the clock's digits are few and large: a small glyph cache does; text gets more */
    lv_font_t *f = lv_tiny_ttf_create_data_ex(a, b - a, px, LV_FONT_KERNING_NONE, px > 100 ? 24 : 256);
    if (!f) {
        ESP_LOGE(TAG_WALL, "font %d at %d px could not be made", kind, px);
        return symbols_for(px);
    }
    f->fallback = symbols_for(px);
    ttf_glyph_dsc = f->get_glyph_dsc;   /* the same for every font Tiny TTF makes */
    f->get_glyph_dsc = glyph_dsc;
    if (nfonts < (int)(sizeof fonts / sizeof fonts[0])) {
        fonts[nfonts++] = (font_slot_t){kind, px, f};
    }
    return f;
}

const lv_font_t *font_text(int px) { return font_of(0, px); }
const lv_font_t *font_bold(int px) { return font_of(1, px); }
const lv_font_t *font_light(int px) { return font_of(2, px); }

lv_color_t color_hex(uint32_t rgb) { return lv_color_hex(rgb); }

/* ------------------------------------------------------------------ times and dates */

static const char *WEEKDAYS[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
static const char *MONTHS[] = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"};

void fmt_clock(char *out, size_t n, int hour, int minute)
{
    if (S.clock24) {
        snprintf(out, n, "%d:%02d", hour, minute);
    } else {
        int h = hour % 12;
        snprintf(out, n, "%d:%02d %s", h ? h : 12, minute, hour < 12 ? "AM" : "PM");
    }
}

void fmt_time(char *out, size_t n, time_t t)
{
    struct tm tm;
    localtime_r(&t, &tm);
    fmt_clock(out, n, tm.tm_hour, tm.tm_min);
}

void fmt_hour(char *out, size_t n, time_t t)
{
    struct tm tm;
    localtime_r(&t, &tm);
    if (S.clock24) {
        snprintf(out, n, "%d:00", tm.tm_hour);
    } else {
        int h = tm.tm_hour % 12;
        snprintf(out, n, "%d %s", h ? h : 12, tm.tm_hour < 12 ? "AM" : "PM");
    }
}

static int days_from_today(const char *date)
{
    int y, m, d;
    if (sscanf(date, "%d-%d-%d", &y, &m, &d) != 3) return 99;
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    struct tm a = {.tm_year = y - 1900, .tm_mon = m - 1, .tm_mday = d, .tm_hour = 12};
    struct tm b = {.tm_year = t.tm_year, .tm_mon = t.tm_mon, .tm_mday = t.tm_mday, .tm_hour = 12};
    return (int)((mktime(&a) - mktime(&b) + 43200) / 86400);
}

void fmt_day_head(char *out, size_t n, const char *date)
{
    int in = days_from_today(date);
    int y, m, d;
    if (in == 0) { strlcpy(out, "Today", n); return; }
    if (in == 1) { strlcpy(out, "Tomorrow", n); return; }
    if (sscanf(date, "%d-%d-%d", &y, &m, &d) != 3) { strlcpy(out, date, n); return; }
    struct tm a = {.tm_year = y - 1900, .tm_mon = m - 1, .tm_mday = d, .tm_hour = 12};
    mktime(&a);
    if (in > 1 && in < 7) snprintf(out, n, "%s", WEEKDAYS[a.tm_wday]);
    else snprintf(out, n, "%.3s %d %s", WEEKDAYS[a.tm_wday], d, MONTHS[m - 1]);
}

void fmt_event_when(char *out, size_t n, const wall_event_t *e)
{
    if (e->all_day) {
        strlcpy(out, "All day", n);
    } else {
        fmt_time(out, n, e->s);
    }
}

/* ------------------------------------------------------------------ brightness, the night, the turn */

static int64_t woken_until;  /* a touch at night: full brightness till then (µs) */

static bool night_now(void)
{
    if (S.night_from == S.night_to || !clock_is_set()) return false;
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    int h = t.tm_hour;
    return S.night_from < S.night_to ? (h >= S.night_from && h < S.night_to) : (h >= S.night_from || h < S.night_to);
}

static int bright_shown = -1;

void ui_apply_brightness(void)
{
    int want = S.day_bright;
    if (night_now() && esp_timer_get_time() > woken_until && !alarm_ringing()) {
        want = S.night_bright;
    }
    if (want < 0) want = 0;
    if (want > 100) want = 100;
    if (want == bright_shown) return;
    if (want == 0) {
        bsp_display_backlight_off();
    } else {
        if (bright_shown == 0) bsp_display_backlight_on();
        bsp_display_brightness_set(want);
    }
    bright_shown = want;
}

bool ui_screen_dark(void)
{
    return bright_shown == 0;
}

void ui_wake(void)
{
    woken_until = esp_timer_get_time() + 30LL * 1000000;
    ui_apply_brightness();
}

void ui_apply_rotation(void)
{
    bsp_display_rotate(DISP, BOARD_ROTATION(S.flip));
}

/* ------------------------------------------------------------------ a toast */

static lv_obj_t *toast;
static lv_timer_t *toast_timer;

static void toast_gone(lv_timer_t *t)
{
    if (toast) lv_obj_add_flag(toast, LV_OBJ_FLAG_HIDDEN);
    toast_timer = NULL;
}

void ui_toast(const char *text)
{
    if (!toast) {
        toast = lv_label_create(lv_layer_top());
        lv_obj_set_style_bg_color(toast, lv_color_hex(0x202020), 0);
        lv_obj_set_style_bg_opa(toast, LV_OPA_90, 0);
        lv_obj_set_style_text_color(toast, lv_color_white(), 0);
        lv_obj_set_style_text_font(toast, font_text(26), 0);
        lv_obj_set_style_pad_hor(toast, P(28), 0);
        lv_obj_set_style_pad_ver(toast, P(16), 0);
        lv_obj_set_style_radius(toast, P(32), 0);
        lv_obj_set_style_max_width(toast, P(1000), 0);
        lv_label_set_long_mode(toast, LV_LABEL_LONG_WRAP);
        lv_obj_align(toast, LV_ALIGN_BOTTOM_MID, 0, -P(40));
    }
    lv_label_set_text(toast, text);
    lv_obj_remove_flag(toast, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(toast);
    lv_obj_align(toast, LV_ALIGN_BOTTOM_MID, 0, -P(40));
    if (toast_timer) lv_timer_delete(toast_timer);
    toast_timer = lv_timer_create(toast_gone, 3500, NULL);
    lv_timer_set_repeat_count(toast_timer, 1);
}

/* ------------------------------------------------------------------ the second's tick */

static void tick(lv_timer_t *t)
{
    alarm_tick();
    ui_wall_tick();
    static int n;
    if (++n % 10 == 0) {
        ui_apply_brightness();
        power_tick();
    }
}

/* any touch: the night's dim screen lights up; the first touch on a dark screen does nothing else */
static void on_any_press(lv_event_t *e)
{
    bool was_dark = ui_screen_dark();
    ui_wake();
    if (was_dark) {
        lv_indev_t *in = lv_indev_active();
        if (in) lv_indev_wait_release(in);
    }
}

static void on_frame(lv_event_t *e);
static void on_keep_display(lv_event_t *e);
static void on_cull(lv_event_t *e);
static void on_bands(lv_event_t *e);

/* A touch at the very edge of the glass is reported one past the last pixel (the touch driver mirrors a coordinate
 * as "the size minus it", and 0 becomes the size). LVGL writes a warning to the log for every reading of such a
 * point, and goes on reading it after the finger is gone: some 66 lines a second until the next touch elsewhere.
 * Measured on the board, writing them was three quarters of what the screen's task did. A swipe that runs off the
 * screen is enough to start it. So what the panel reports is brought onto the screen first. */
static void touch_read(lv_indev_t *in, lv_indev_data_t *d)
{
    lv_indev_read_cb_t read = (lv_indev_read_cb_t)lv_indev_get_user_data(in);
    lv_display_t *disp = lv_indev_get_display(in);
    read(in, d);
    if (!disp) return;
    d->point.x = LV_CLAMP(0, d->point.x, lv_display_get_original_horizontal_resolution(disp) - 1);
    d->point.y = LV_CLAMP(0, d->point.y, lv_display_get_original_vertical_resolution(disp) - 1);
}

void ui_start(lv_display_t *disp)
{
    DISP = disp;
    ui_apply_rotation();
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    lv_indev_t *in = bsp_display_get_input_dev();
    if (in) lv_indev_add_event_cb(in, on_any_press, LV_EVENT_PRESSED, NULL);
    if (in && lv_indev_get_type(in) == LV_INDEV_TYPE_POINTER && lv_indev_get_read_cb(in) != touch_read) {
        lv_indev_set_user_data(in, (void *)lv_indev_get_read_cb(in));
        lv_indev_set_read_cb(in, touch_read);
    }
    static const lv_event_code_t timed[] = {LV_EVENT_REFR_START, LV_EVENT_RENDER_START, LV_EVENT_FLUSH_START,
                                            LV_EVENT_FLUSH_FINISH, LV_EVENT_FLUSH_WAIT_START, LV_EVENT_FLUSH_WAIT_FINISH,
                                            LV_EVENT_REFR_READY};
    for (size_t i = 0; i < sizeof timed / sizeof *timed; i++) lv_display_add_event_cb(disp, on_frame, timed[i], NULL);
    /* a panel's picture of its content (kit_panel) is brought up to date as a frame begins, within its time */
    lv_display_add_event_cb(disp, on_keep_display, LV_EVENT_INVALIDATE_AREA, NULL);
    lv_display_add_event_cb(disp, on_keep_display, LV_EVENT_REFR_START, NULL);
    lv_display_add_event_cb(disp, on_keep_display, LV_EVENT_REFR_READY, NULL);
    lv_display_add_event_cb(disp, on_cull, LV_EVENT_REFR_START, NULL);
    lv_display_add_event_cb(disp, on_bands, LV_EVENT_REFR_START, NULL);
    lv_timer_create(tick, 1000, NULL);
    ui_apply_brightness();
    if (S.server[0] && S.token[0]) {
        ui_show_wall();
    } else {
        ui_show_setup();
    }
}

/* ------------------------------------------------------------------ the parts the screens and panels are made of */

lv_obj_t *kit_label(lv_obj_t *p, const lv_font_t *f, lv_color_t c, const char *t)
{
    lv_obj_t *l = lv_label_create(p);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, c, 0);
    lv_label_set_text(l, t ? t : "");
    return l;
}

void kit_set_text(lv_obj_t *l, const char *t)
{
    if (strcmp(lv_label_get_text(l), t)) lv_label_set_text(l, t);
}

void kit_show(lv_obj_t *o, bool on)
{
    if (lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN) == !on) return;
    if (on) lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}

/* The weather's icons are drawn (tools/make_icons.py) 112 and 52 pixels wide, as the Tab5 shows them. The 7B shows
 * them at four fifths of that, and both show the hours' at half; LVGL resized such an icon at every redraw of it,
 * through a picture of its own made and thrown away each time: on the 7B a sixth of the time the wall took to draw,
 * with the hours on it. Here an icon is made at each size once, every pixel the mean of what it covers of the drawn
 * one, and shown as it is. */
const lv_image_dsc_t *kit_icon(int kind, int px)
{
    static lv_image_dsc_t *made[ICON_COUNT][4];
    if (kind < 0 || kind >= ICON_COUNT) kind = ICON_CLOUD;
    const lv_image_dsc_t *from = px > 52 ? icons_big[kind] : icons_small[kind];
    int sw = from->header.w, sh = from->header.h;
    if (px == sw || px < 4) return from;
    lv_image_dsc_t **at = made[kind];
    for (int i = 0; i < 4; i++, at++) {
        if (!*at) break;
        if ((*at)->header.w == px) return *at;
    }
    if (at == made[kind] + 4) return from;   /* more sizes than the screens ask for */
    int ph = px * sh / sw;
    lv_image_dsc_t *im = heap_caps_malloc(sizeof *im + (size_t)px * ph, MALLOC_CAP_SPIRAM);
    if (!im) return from;
    uint8_t *out = (uint8_t *)(im + 1);
    *im = *from;
    im->header.w = px;
    im->header.h = ph;
    im->header.stride = px;
    im->data_size = (uint32_t)(px * ph);
    im->data = out;
    /* what a pixel covers of the drawn icon, in 256ths of its pixels */
    for (int y = 0; y < ph; y++) {
        uint32_t y0 = (uint32_t)y * sh * 256 / ph, y1 = (uint32_t)(y + 1) * sh * 256 / ph;
        for (int x = 0; x < px; x++) {
            uint32_t x0 = (uint32_t)x * sw * 256 / px, x1 = (uint32_t)(x + 1) * sw * 256 / px;
            uint64_t sum = 0;
            for (uint32_t sy = y0 >> 8; sy << 8 < y1; sy++) {
                uint32_t wy = LV_MIN(y1, (sy + 1) << 8) - LV_MAX(y0, sy << 8);
                const uint8_t *row = from->data + (size_t)sy * from->header.stride;
                for (uint32_t sx = x0 >> 8; sx << 8 < x1; sx++) {
                    sum += (uint64_t)row[sx] * wy * (LV_MIN(x1, (sx + 1) << 8) - LV_MAX(x0, sx << 8));
                }
            }
            uint64_t all = (uint64_t)(y1 - y0) * (x1 - x0);
            out[y * px + x] = (uint8_t)((sum + all / 2) / all);
        }
    }
    *at = im;
    return im;
}

lv_obj_t *kit_button(lv_obj_t *p, const char *text, lv_event_cb_t cb, void *ud, bool primary)
{
    lv_obj_t *b = lv_button_create(p);
    lv_obj_set_height(b, P(76));
    lv_obj_set_style_pad_hor(b, P(34), 0);
    lv_obj_set_style_radius(b, P(38), 0);
    lv_obj_set_style_shadow_width(b, 0, 0);
    lv_obj_set_style_bg_color(b, primary ? lv_color_hex(0x3f86c9) : lv_color_hex(0x33363d), 0);
    lv_obj_set_style_bg_color(b, primary ? lv_color_hex(0x2c6aa6) : lv_color_hex(0x4a4e57), LV_STATE_PRESSED);
    lv_obj_t *l = kit_label(b, font_bold(28), lv_color_white(), text);
    lv_obj_center(l);
    if (cb) lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
    return b;
}

lv_obj_t *kit_textarea(lv_obj_t *p, const char *placeholder, bool password)
{
    lv_obj_t *ta = lv_textarea_create(p);
    lv_textarea_set_one_line(ta, true);
    lv_textarea_set_password_mode(ta, password);
    lv_textarea_set_placeholder_text(ta, placeholder);
    lv_obj_set_width(ta, lv_pct(100));
    lv_obj_set_style_text_font(ta, font_text(30), 0);
    lv_obj_set_style_bg_color(ta, lv_color_hex(0x1b1d22), 0);
    lv_obj_set_style_text_color(ta, lv_color_white(), 0);
    lv_obj_set_style_border_color(ta, lv_color_hex(0x4a4e57), 0);
    lv_obj_set_style_border_color(ta, lv_color_hex(0x3f86c9), LV_STATE_FOCUSED);
    lv_obj_set_style_radius(ta, P(14), 0);
    lv_obj_set_style_pad_all(ta, P(16), 0);
    lv_obj_set_style_text_color(ta, lv_color_hex(0x8a8f98), LV_PART_TEXTAREA_PLACEHOLDER);
    return ta;
}

/* the key under the finger, lighter: the keyboard's own look for it is taken out (kit_keyboard) */
static void on_key_draw(lv_event_t *e)
{
    lv_draw_task_t *t = lv_event_get_draw_task(e);
    lv_draw_fill_dsc_t *fill = lv_draw_task_get_fill_dsc(t);
    if (!fill || fill->base.part != LV_PART_ITEMS) return;
    lv_obj_t *kb = lv_event_get_target(e);
    if (lv_obj_has_state(kb, LV_STATE_PRESSED) && fill->base.id1 == lv_buttonmatrix_get_selected_button(kb)) {
        fill->color = lv_color_hex(0x565a64);
    }
}

lv_obj_t *kit_keyboard(lv_obj_t *p, lv_obj_t *ta, lv_event_cb_t on_ready, void *ud)
{
    lv_obj_t *kb = lv_keyboard_create(p);
    lv_obj_set_size(kb, WALL_W, P(330));
    lv_obj_align(kb, LV_ALIGN_BOTTOM_MID, 0, 0);
    /* A key pressed or let go draws that key and not all of them. LVGL draws a whole widget again when its pressed
     * state has a look of its own, and the theme gives the keys one; without it the keyboard draws only the key
     * (which it does by itself), and the key's pressed colour is put in as it is drawn. */
    lv_obj_remove_style(kb, NULL, LV_PART_ITEMS | LV_STATE_PRESSED);
    lv_obj_add_flag(kb, LV_OBJ_FLAG_SEND_DRAW_TASK_EVENTS);
    lv_obj_add_event_cb(kb, on_key_draw, LV_EVENT_DRAW_TASK_ADDED, NULL);
    /* the built-in font: it needs no rasterizing */
    lv_obj_set_style_text_font(kb, font_symbols(28), 0);
    lv_obj_set_style_text_font(kb, font_symbols(28), LV_PART_ITEMS);
    lv_obj_set_style_bg_color(kb, lv_color_hex(0x111215), 0);
    lv_obj_set_style_bg_color(kb, lv_color_hex(0x2a2c31), LV_PART_ITEMS);
    lv_obj_set_style_text_color(kb, lv_color_white(), LV_PART_ITEMS);
    lv_keyboard_set_textarea(kb, ta);
    if (on_ready) lv_obj_add_event_cb(kb, on_ready, LV_EVENT_READY, ud);
    return kb;
}

static lv_obj_t *panel, *panel_card;

/* ---- what scrolls in a panel is kept as drawn
 *
 * Drawing a panel's rows (text, sliders, round buttons) is what a frame of a scroll was made of: the same rows, a few
 * pixels further up, drawn anew every time. So the rows are drawn once, into a picture of their own that is as wide
 * and as tall as all of them, and the screen gets the picture: a copy of the part in view. A scroll then draws the
 * strip that comes into view and no more; a switch that moves, a line that says something else or a blinking cursor
 * is drawn again where it is (LVGL says which area of the screen is no longer right: LV_EVENT_INVALIDATE_AREA).
 *
 * Only the rows in view are kept right: LVGL reports nothing about what changes out of sight, so what comes back
 * into view is always drawn. The body draws the picture itself and says it covers its area; while LVGL then goes
 * through the body's children, the rows are marked hidden behind its back so that they are not drawn a second time
 * (to touches, to the layout and to the scroll bar they are there as ever: adding the flag the proper way would
 * upset all three). */
#define KEEP_MAX (12 * 1024 * 1024)   /* no picture larger than this (bytes): the rows are then drawn as before */

static bool keeps = true;
static uint32_t keep_us;   /* µs this frame's rows took to draw into the picture, for the frame's own account */

static struct {
    lv_obj_t *body, *content;
    lv_color_t ground;
    lv_draw_buf_t *buf;       /* the rows as drawn; NULL: not kept */
    int32_t no_w, no_h;       /* a size there was no memory for: not asked for again at every frame */
    int32_t y0, y1;           /* the rows of it that are as the content is now (y1 not among them) */
    lv_area_t dirty[8];       /* parts of them to draw again, in the content's own coordinates */
    int ndirty;
    bool scrolled;            /* the body's next invalidation is its own scroll: nothing in it changed */
    bool ready;               /* the picture is right for the frame now drawn */
    bool hidden;              /* the content is marked hidden while the body's children are gone through */
} keep;

/* draws part of the content (in its own coordinates) into the picture */
static void keep_draw_part(int32_t x1, int32_t y1, int32_t x2, int32_t y2)
{
    lv_obj_t *c = keep.content;
    lv_area_t a = {x1 + c->coords.x1, y1 + c->coords.y1, x2 + c->coords.x1, y2 + c->coords.y1};
    lv_layer_t layer;
    lv_layer_init(&layer);
    layer.draw_buf = keep.buf;
    layer.buf_area = c->coords;
    layer.color_format = LV_COLOR_FORMAT_RGB565;
    layer._clip_area = a;
    layer.phy_clip_area = a;
    lv_display_t *disp = lv_obj_get_display(c), *was = lv_refr_get_disp_refreshing();
    lv_layer_t *head = disp->layer_head;
    disp->layer_head = &layer;
    lv_refr_set_disp_refreshing(disp);
    lv_draw_fill_dsc_t fill;
    lv_draw_fill_dsc_init(&fill);
    fill.color = keep.ground;
    lv_draw_fill(&layer, &fill, &a);
    lv_obj_redraw(&layer, c);
    while (layer.draw_task_head) {
        lv_draw_dispatch_wait_for_request();
        lv_draw_dispatch();
    }
    disp->layer_head = head;
    lv_refr_set_disp_refreshing(was);
}

static int32_t keep_strip;   /* the rows are drawn in strips of so many (0: in one piece) */

static void keep_draw(int32_t x1, int32_t y1, int32_t x2, int32_t y2)
{
    int32_t rows = keep_strip > 0 ? keep_strip : y2 - y1 + 1;
    for (int32_t y = y1; y <= y2; y += rows) keep_draw_part(x1, y, x2, LV_MIN(y2, y + rows - 1));
}

uint32_t kit_panel_rows_us(int strip)
{
    if (!keep.buf || keep.y0 >= keep.y1) return 0;
    int32_t was = keep_strip;
    keep_strip = strip;
    int64_t t0 = esp_timer_get_time();
    keep_draw(0, keep.y0, (int32_t)keep.buf->header.w - 1, keep.y1 - 1);
    keep_strip = was;
    return (uint32_t)(esp_timer_get_time() - t0);
}

static void keep_drop(void)
{
    if (keep.buf) {
        lv_image_cache_drop(keep.buf);
        lv_draw_buf_destroy(keep.buf);
        keep.buf = NULL;
    }
    keep.y0 = keep.y1 = keep.ndirty = 0;
}

/* before a frame: the picture is brought to what the content is now, where it is in view */
static void keep_ready(void)
{
    lv_obj_t *c = keep.content;
    if (!keeps) return;
    lv_obj_update_layout(c);
    int32_t w = lv_obj_get_width(c), h = lv_obj_get_height(c);
    keep.scrolled = false;   /* a scroll whose invalidation never came is not waited for any longer */
    if (!keep.buf ? (w != keep.no_w || h != keep.no_h) : (keep.buf->header.w != w || keep.buf->header.h != h)) {
        keep_drop();
        if (w > 0 && h > 0 && (int64_t)w * h * 2 <= KEEP_MAX) keep.buf = lv_draw_buf_create(w, h, LV_COLOR_FORMAT_RGB565, 0);
        keep.no_w = keep.buf ? 0 : w;
        keep.no_h = keep.buf ? 0 : h;
        if (keep.buf) ESP_LOGI(TAG_WALL, "a panel's rows are kept as a picture of %d x %d", (int)w, (int)h);
        else if (w > 0 && h > 0) ESP_LOGW(TAG_WALL, "no picture of %d x %d for a panel's rows: they are drawn each time", (int)w, (int)h);
    }
    lv_area_t seen;
    if (!keep.buf || !lv_area_intersect(&seen, &keep.body->coords, &c->coords)) {
        keep.y0 = keep.y1 = keep.ndirty = 0;
        return;
    }
    int32_t v0 = seen.y1 - c->coords.y1, v1 = seen.y2 - c->coords.y1 + 1;
    if (keep.y0 >= keep.y1 || v0 >= keep.y1 || v1 <= keep.y0) {
        keep_draw(0, v0, w - 1, v1 - 1);
    } else {
        if (v0 < keep.y0) keep_draw(0, v0, w - 1, keep.y0 - 1);
        if (v1 > keep.y1) keep_draw(0, keep.y1, w - 1, v1 - 1);
        int32_t k0 = LV_MAX(v0, keep.y0), k1 = LV_MIN(v1, keep.y1);
        for (int i = 0; i < keep.ndirty; i++) {
            lv_area_t *d = &keep.dirty[i];
            int32_t d0 = LV_MAX(d->y1, k0), d1 = LV_MIN(d->y2, k1 - 1);
            if (d0 <= d1) keep_draw(d->x1, d0, d->x2, d1);
        }
    }
    keep.y0 = v0;
    keep.y1 = v1;
    keep.ndirty = 0;
    keep.ready = true;
}

static void on_keep_display(lv_event_t *e)
{
    if (lv_event_get_code(e) == LV_EVENT_REFR_START) keep_us = 0;
    if (!keep.body || !keeps) return;
    switch (lv_event_get_code(e)) {
    case LV_EVENT_INVALIDATE_AREA: {
        const lv_area_t *a = lv_event_get_param(e);
        lv_area_t seen, d;
        if (!keep.buf || !a || !lv_area_intersect(&seen, &keep.body->coords, &keep.content->coords)) break;
        if (keep.scrolled && lv_area_is_in(&seen, a, 0)) {
            keep.scrolled = false;
            break;
        }
        if (!lv_area_intersect(&d, a, &seen)) break;
        lv_area_move(&d, -keep.content->coords.x1, -keep.content->coords.y1);
        int n = 0;   /* the same area is often reported several times over, or within a larger one */
        for (int i = 0; i < keep.ndirty; i++) {
            if (lv_area_is_in(&d, &keep.dirty[i], 0)) return;
            if (!lv_area_is_in(&keep.dirty[i], &d, 0)) keep.dirty[n++] = keep.dirty[i];
        }
        keep.ndirty = n;
        if (keep.ndirty == (int)(sizeof keep.dirty / sizeof *keep.dirty)) {   /* no room: one area around them all */
            for (int i = 1; i < keep.ndirty; i++) lv_area_join(&keep.dirty[0], &keep.dirty[0], &keep.dirty[i]);
            keep.ndirty = 1;
        }
        keep.dirty[keep.ndirty++] = d;
        break;
    }
    case LV_EVENT_REFR_START: {
        uint8_t was = ui_phase;
        int64_t t0 = esp_timer_get_time();
        ui_phase = UI_ROWS;
        keep_ready();
        ui_phase = was;
        keep_us = (uint32_t)(esp_timer_get_time() - t0);
        break;
    }
    case LV_EVENT_REFR_READY:
        keep.ready = false;
        break;
    default:
        break;
    }
}

/* Under an open panel's card nothing is drawn that the card hides.
 *
 * LVGL draws an area that changed from the topmost thing that covers all of it: a row that changes in a panel has
 * the panel drawn and not the wall under it. But an area that reaches past the card (the whole screen when a panel
 * opens, or when the next photo comes behind it) is covered by nothing, and the photo, the wall's texts and the
 * panel's shade over them were drawn for all of it, four fifths of it only to be painted over by the card. So before
 * a frame is drawn such an area is cut in five: what lies within the card, where LVGL then begins at the card, and
 * the four strips around it. The picture is the same to the pixel (tools/sim's check draws both). */
static bool culls = true;

void kit_panel_cull(bool on)
{
    culls = on;
}

static void on_cull(lv_event_t *e)
{
    lv_display_t *d = lv_event_get_target(e);
    if (!culls || !panel_card || lv_obj_has_flag(panel, LV_OBJ_FLAG_HIDDEN) || lv_obj_get_screen(panel) != lv_display_get_screen_active(d)) return;
    lv_obj_update_layout(panel);   /* where the card is, when it was made just now */
    /* within the card's round corners: a rectangle this far in has its own corners inside them */
    int32_t round = lv_obj_get_style_radius(panel_card, 0), in = round * 3 / 10 + 2;
    lv_area_t card = panel_card->coords;
    lv_area_increase(&card, -in, -in);
    if (lv_area_get_width(&card) < 8 || lv_area_get_height(&card) < 8) return;
    uint32_t n = d->inv_p;
    for (uint32_t i = 0; i < n; i++) {
        lv_area_t a = d->inv_areas[i], mid;
        /* an area the card covers, round corners and all, is drawn from the card or from what is in it as it is (a
         * scroll's reaches to the card's edge, and is drawn from what scrolls) */
        if (d->inv_area_joined[i] || lv_area_is_in(&a, &panel_card->coords, round) || !lv_area_intersect(&mid, &a, &card)) continue;
        /* worth five areas to send in place of one: a good part of the screen is saved */
        if (lv_area_get_size(&mid) < (uint32_t)(WALL_W * WALL_H / 6) || d->inv_p + 4 > LV_INV_BUF_SIZE) continue;
        d->inv_areas[i] = mid;
        lv_area_t around[4] = {
            {a.x1, a.y1, a.x2, mid.y1 - 1},            /* above */
            {a.x1, mid.y2 + 1, a.x2, a.y2},            /* below */
            {a.x1, mid.y1, mid.x1 - 1, mid.y2},        /* left */
            {mid.x2 + 1, mid.y1, a.x2, mid.y2},        /* right */
        };
        for (int k = 0; k < 4; k++) {
            if (around[k].x1 > around[k].x2 || around[k].y1 > around[k].y2) continue;
            d->inv_area_joined[d->inv_p] = 0;
            d->inv_areas[d->inv_p++] = around[k];
        }
    }
}

/* A large area drawn in strips.
 *
 * LVGL draws an area thing by thing: the photo over all of it, then each text and each see-through panel over that.
 * The area is far larger than what the processor keeps at hand of the PSRAM (the cache, 256 KB: a fifth of a screen),
 * so by the time a text is drawn the photo's pixels under it are fetched from the PSRAM again. Cut into strips that
 * fit, everything on a strip is drawn while its pixels are still at hand. Whether that is faster on the board is
 * what the measuring asks (bench.c): until it says so, an area is drawn in one piece. */
static int32_t band_bytes;

void kit_bands(int bytes)
{
    band_bytes = bytes;
}

static void on_bands(lv_event_t *e)
{
    lv_display_t *d = lv_event_get_target(e);
    if (band_bytes <= 0) return;
    /* what the layout still has to call changed is called so first: an area that comes after the strips are cut
     * would be drawn besides them, not within them */
    lv_obj_update_layout(lv_display_get_screen_active(d));
    lv_obj_update_layout(lv_display_get_layer_top(d));
    lv_obj_update_layout(lv_display_get_layer_sys(d));
    uint32_t n = d->inv_p;
    for (uint32_t i = 0; i < n; i++) {
        lv_area_t a = d->inv_areas[i];
        int32_t w = lv_area_get_width(&a), h = lv_area_get_height(&a);
        int32_t rows = LV_MAX(16, band_bytes / (w * 2)), room = (int32_t)LV_INV_BUF_SIZE - (int32_t)d->inv_p;
        if (d->inv_area_joined[i] || h < rows * 2 || room < 1) continue;
        int32_t parts = LV_MIN((h + rows - 1) / rows, room + 1);
        rows = (h + parts - 1) / parts;
        d->inv_areas[i].y2 = a.y1 + rows - 1;
        for (int32_t y = a.y1 + rows; y <= a.y2; y += rows) {
            d->inv_area_joined[d->inv_p] = 0;
            d->inv_areas[d->inv_p++] = (lv_area_t){a.x1, y, a.x2, LV_MIN(a.y2, y + rows - 1)};
        }
    }
}

void kit_panel_keep(bool on)
{
    keeps = on;
    keep.y0 = keep.y1 = keep.ndirty = 0;   /* what changed while it was off was not followed */
    if (keep.body) lv_obj_invalidate(keep.body);
}

static void on_keep_body(lv_event_t *e)
{
    lv_obj_t *body = lv_event_get_target(e);
    switch (lv_event_get_code(e)) {
    case LV_EVENT_SCROLL:
        keep.scrolled = true;
        break;
    case LV_EVENT_COVER_CHECK: {
        /* every pixel of the body is drawn below, the picture or the ground */
        lv_cover_check_info_t *info = lv_event_get_param(e);
        if (info->res != LV_COVER_RES_MASKED) info->res = LV_COVER_RES_COVER;
        break;
    }
    case LV_EVENT_DRAW_MAIN: {
        lv_layer_t *layer = lv_event_get_layer(e);
        lv_obj_t *c = keep.content;
        lv_draw_fill_dsc_t fill;
        lv_draw_fill_dsc_init(&fill);
        fill.color = keep.ground;
        if (!keep.ready) {   /* not kept: the ground, and the rows draw themselves on it */
            lv_draw_fill(layer, &fill, &body->coords);
            break;
        }
        lv_area_t a = body->coords;
        if (c->coords.y1 > a.y1) {   /* pulled down past its top */
            a.y2 = LV_MIN(a.y2, c->coords.y1 - 1);
            lv_draw_fill(layer, &fill, &a);
        }
        a = body->coords;
        if (c->coords.y2 < a.y2) {   /* shorter than the body, or pulled up past its end */
            a.y1 = LV_MAX(a.y1, c->coords.y2 + 1);
            lv_draw_fill(layer, &fill, &a);
        }
        lv_draw_image_dsc_t img;
        lv_draw_image_dsc_init(&img);
        img.src = keep.buf;
        lv_draw_image(layer, &img, &c->coords);
        c->flags |= LV_OBJ_FLAG_HIDDEN;   /* until the children have been gone through: just below */
        keep.hidden = true;
        break;
    }
    case LV_EVENT_DRAW_POST_BEGIN:
        if (keep.hidden) {
            keep.content->flags &= ~LV_OBJ_FLAG_HIDDEN;
            keep.hidden = false;
        }
        break;
    case LV_EVENT_DELETE:
        keep_drop();
        memset(&keep, 0, sizeof keep);
        break;
    default:
        break;
    }
}

static void on_panel_close(lv_event_t *e)
{
    kit_close_panel();
}

void kit_close_panel(void)
{
    if (panel) {
        lv_obj_delete(panel);
        panel = panel_card = NULL;
    }
}

bool kit_panel_open(void)
{
    return panel != NULL;
}

lv_obj_t *kit_panel_layer(void)
{
    return panel;
}

lv_obj_t *kit_panel_card(void)
{
    return panel_card;
}

/* A panel is drawn on the screen it opens over, as its last part, and not on LVGL's top layer. LVGL looks for the
 * topmost thing that covers what changed and draws from there up, but only among the screen's own parts: a panel on
 * the top layer had the photo, its shades and the whole wall drawn again under it at every frame of a scroll, a
 * slider or a key. For the same reason what scrolls is a plain rectangle inside the card, in the card's colour: the
 * card's round corners cover nothing in LVGL's eyes. */
lv_obj_t *kit_panel(const char *title, int w, int h)
{
    const lv_color_t ground = lv_color_hex(0x16181c);
    kit_close_panel();
    panel = lv_obj_create(lv_screen_active());
    lv_obj_remove_style_all(panel);
    lv_obj_set_size(panel, WALL_W, WALL_H);
    lv_obj_remove_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(panel, LV_OBJ_FLAG_GESTURE_BUBBLE);   /* a swipe in a panel is not a swipe on the wall under it */
    lv_obj_set_style_bg_color(panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_60, 0);
    lv_obj_add_flag(panel, LV_OBJ_FLAG_CLICKABLE);  /* a tap beside the card closes it */
    lv_obj_add_event_cb(panel, on_panel_close, LV_EVENT_SHORT_CLICKED, NULL);
    lv_obj_t *card = panel_card = lv_obj_create(panel);
    lv_obj_remove_style_all(card);
    lv_obj_set_size(card, w, h);
    lv_obj_center(card);
    lv_obj_remove_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);   /* a tap on the card itself does not close it */
    lv_obj_set_style_bg_color(card, ground, 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(card, P(28), 0);
    /* the body under the title reaches nearly to the card's right and bottom edges, and stays just inside the round
     * of its corners: its own are square */
    lv_obj_set_style_pad_left(card, P(30), 0);
    lv_obj_set_style_pad_top(card, P(30), 0);
    lv_obj_set_style_pad_right(card, P(8), 0);
    lv_obj_set_style_pad_bottom(card, P(10), 0);
    lv_obj_set_style_pad_row(card, P(16), 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_t *top = lv_obj_create(card);
    lv_obj_remove_style_all(top);
    lv_obj_set_size(top, w - 2 * P(30), LV_SIZE_CONTENT);
    lv_obj_remove_flag(top, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *t = kit_label(top, font_bold(36), lv_color_white(), title);
    lv_label_set_long_mode(t, LV_LABEL_LONG_DOT);
    lv_obj_set_size(t, w - P(160), lv_font_get_line_height(font_bold(36)));
    lv_obj_align(t, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_t *x = lv_button_create(top);
    lv_obj_set_size(x, P(64), P(64));
    lv_obj_set_style_radius(x, P(32), 0);
    lv_obj_set_style_bg_color(x, lv_color_hex(0x33363d), 0);
    lv_obj_set_style_shadow_width(x, 0, 0);
    lv_obj_align(x, LV_ALIGN_RIGHT_MID, 0, 0);
    lv_obj_t *xl = kit_label(x, font_symbols(28), lv_color_white(), LV_SYMBOL_CLOSE);
    lv_obj_center(xl);
    lv_obj_add_event_cb(x, on_panel_close, LV_EVENT_CLICKED, NULL);
    /* the body: the window on what the panel shows, which scrolls in it when it is longer than the card. The body
     * reaches nearly to the card's right edge, so its scroll bar is in the margin. It has no ground of its own: it
     * draws the picture kept of its content (above). */
    lv_obj_t *body = lv_obj_create(card);
    lv_obj_set_width(body, lv_pct(100));
    lv_obj_set_flex_grow(body, 1);
    lv_obj_set_style_bg_opa(body, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(body, 0, 0);
    lv_obj_set_style_radius(body, 0, 0);
    lv_obj_set_style_pad_all(body, 0, 0);
    lv_obj_set_scroll_dir(body, LV_DIR_VER);
    /* the scroll bar looks the same whether the body is being scrolled or not: the theme lights it up while it is,
     * step by step, and every step of that has LVGL call the whole body changed */
    lv_obj_remove_style(body, NULL, LV_PART_SCROLLBAR | LV_STATE_SCROLLED);
    lv_obj_t *c = lv_obj_create(body);
    lv_obj_remove_style_all(c);
    lv_obj_set_size(c, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_remove_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_pad_right(c, P(22), 0);
    lv_obj_set_style_pad_bottom(c, P(20), 0);
    lv_obj_set_style_pad_row(c, P(16), 0);
    lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
    memset(&keep, 0, sizeof keep);
    keep.body = body;
    keep.content = c;
    keep.ground = ground;
    lv_obj_add_event_cb(body, on_keep_body, LV_EVENT_ALL, NULL);
    return c;
}

/* ------------------------------------------------------------------ how long the screen takes to draw */

/* A frame is drawn by LVGL (into its own buffer, in the PSRAM), then sent: turned by the pixel processor where the
 * screen is turned, and handed to the copy into the panel's frame. The two are told apart here, since which of them
 * a slow frame is made of decides what would make it fast. */
static struct {
    int64_t started, mark;   /* when the frame began, and the sending or waiting now going on (µs) */
    uint32_t px;             /* what the frame sent to the panel so far */
    uint32_t sending;        /* µs of the frame spent sending, waits for the frame before included */
    uint32_t layout;         /* µs from the frame's start to its first pixel: layout, and a panel's rows redrawn */
    uint32_t from;           /* frames that sent this many pixels or more are counted */
    ui_frames_t sum;         /* those since the last reset: times in µs, added up */
} frames = {.from = WALL_W * WALL_H / 4};

volatile uint8_t ui_phase;

static void on_frame(lv_event_t *e)
{
    int64_t now = esp_timer_get_time();
    switch (lv_event_get_code(e)) {
    case LV_EVENT_REFR_START:
        frames.started = now;
        frames.px = frames.sending = frames.layout = 0;
        ui_phase = UI_LAYING_OUT;
        break;
    case LV_EVENT_RENDER_START:
        frames.layout = (uint32_t)(now - frames.started);
        ui_phase = UI_DRAWING;
        break;
    case LV_EVENT_FLUSH_START: {
        const lv_area_t *a = lv_event_get_param(e);
        if (a) frames.px += (uint32_t)lv_area_get_size(a);
        frames.mark = now;
        ui_phase = UI_SENDING;
        break;
    }
    case LV_EVENT_FLUSH_WAIT_START:
        frames.mark = now;
        ui_phase = UI_SENDING;
        break;
    case LV_EVENT_FLUSH_FINISH:
    case LV_EVENT_FLUSH_WAIT_FINISH:
        frames.sending += (uint32_t)(now - frames.mark);
        ui_phase = UI_DRAWING;
        break;
    case LV_EVENT_REFR_READY:
        ui_phase = UI_BETWEEN;
        if (frames.px && frames.px >= frames.from) {
            uint32_t us = (uint32_t)(now - frames.started);
            frames.sum.n++;
            frames.sum.all += us;
            frames.sum.rows += keep_us;
            frames.sum.layout += frames.layout > keep_us ? frames.layout - keep_us : 0;
            frames.sum.sending += frames.sending;
            frames.sum.px += frames.px;
            if (us > frames.sum.worst) frames.sum.worst = us;
        }
        break;
    default:
        break;
    }
}

void ui_frames_reset(uint32_t from_px)
{
    memset(&frames.sum, 0, sizeof frames.sum);
    /* by default a quarter of the screen or more: a scroll, a panel, a photo; not the clock's minute */
    frames.from = from_px ? from_px : (uint32_t)(WALL_W * WALL_H / 4);
}

void ui_frames_get(ui_frames_t *out)
{
    *out = frames.sum;
}

void ui_frames_beside(uint32_t us, uint32_t px)
{
    if (px >= frames.from) frames.sum.beside += us;
}

void ui_frames_text(char *out, size_t n)
{
    const ui_frames_t *f = &frames.sum;
    if (!f->n) {
        strlcpy(out, "Nothing large drawn yet", n);
        return;
    }
    unsigned all = (f->all / f->n + 500) / 1000, sending = (f->sending / f->n + 500) / 1000;
    snprintf(out, n, "%u large redraws · %u ms each (%u drawing, %u sending) · the slowest %u ms", (unsigned)f->n, all,
             all > sending ? all - sending : 0, sending, (unsigned)((f->worst + 500) / 1000));
}
