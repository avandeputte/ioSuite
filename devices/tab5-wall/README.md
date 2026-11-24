# The wall on an ESP32-P4 touch screen

Firmware that puts the start page's wall (`#/wall`) on its own screen, on USB power and always on. For two boards
(the same firmware, built for each):

- [M5Stack Tab5](https://docs.m5stack.com/en/core/Tab5): 5 inch, 1280 × 720.
- [Waveshare ESP32-P4-WIFI6-Touch-LCD-7B](https://www.waveshare.com/esp32-p4-wifi6-touch-lcd-7b.htm): 7 inch,
  1024 × 600. The wall is laid out the same, at four fifths of the Tab5's sizes.

- **The wall:** clock and date, the weather now with the coming hours and days and a rain note, today's events
  with their places ("6:00 PM Dinner @ Nan Xiang Dumpling") and the week's (a tap on Week), birthdays,
  today's tasks, Home Assistant tiles, and ioPix photos behind it all (or a sky, or black: the start page's wall
  setting).
- **Views a swipe away:** swipe left or right on the wall for the calendar's coming days, today's tasks, money
  (the week's bills, accounts running low), health (steps, rings, sleep), the papers to renew and the weather, each
  over the photo, darkened. They are the start page's TRMNL screens (`/api/trmnl/<screen>`), so a view is there when
  the person signed in may see its app. Settings on the device chooses which are swiped to; a view left alone for
  three minutes goes back to the wall.
- **Touch:** tap an event for its details, tick a task done, tap a Home Assistant tile to switch it, tap the
  background for the next photo and the bar, whose Favorite makes the photo a favorite in ioPix. Add a task or an event with the
  on-screen keyboard.
- **Timers and an alarm clock** on the board's speaker (four of each; alarms by weekday or once, snooze).
- **Night:** dims from 22:00 to 06:00 by default (or turns the screen off); a touch lights it for 30 seconds.
  Hours and brightness are in Settings on the device.
- **On its battery** (Tab5): how full it is, beside the date, while the battery is in use (with a charge mark
  while USB power fills it). Settings › Power shows the readings as they are. The Waveshare board has nothing that
  measures its battery.
- **How quick it draws** is on the device: Settings › Screen counts the large redraws (a scroll, a panel, a
  photo) since Settings was opened and says how long they took, each and the slowest, and how much of that was
  drawing and how much sending what was drawn to the panel. **Measure** there scrolls Settings, drags a slider,
  swipes to a view and changes the photo by itself for half a minute and then lists what the frames of each took.
- **Updates itself** at 3 AM from the release `wall-latest` (Settings turns that off). A firmware that does not
  run for a minute is rolled back.

## Install it

From Chrome or Edge on a computer: **[iosuite.iothing.net/wall/](https://iosuite.iothing.net/wall/)**.

1. Connect the Tab5 with a USB-C cable that carries data.
2. Hold the reset button about two seconds, until the green light inside blinks fast (download mode).
3. Press Install, pick the port, wait about a minute, then press reset once.
4. On the Tab5: pick the Wi-Fi, type the start page's address (`192.168.1.20`, or `https://start.example.com`
   when no sign-in page such as Cloudflare Access stands in front of it), then let it in. Scan the QR code with
   your phone, or open the start page at `#/pair` and type the code. Or sign in on the Tab5 with your name and
   password. The Tab5 gets an app password of yours ("Wall display (Tab5)", in Settings › Account), so it sees what
   you see. Remove that password and the Tab5 goes back to setting up.

**The Waveshare board** installs from the same page: connect one of its USB-C ports (the one for USB to UART is the
easier), press the Install that fits its chip, and press RESET when it is done. If it cannot connect, hold BOOT,
press RESET, let go of BOOT, and try again. The board comes with an ESP32-P4 of revision 1 or, on newer boards, of
revision 3, and each runs only its own build: with the wrong one the screen stays dark, and you install the other.
Its app password is called "Wall display (Waveshare 7B)".

Without a browser that writes to USB: `esptool.py --chip esp32p4 write_flash 0x0 iowall-full.bin` with the file
from the [release](https://github.com/avandeputte/iosuite/releases/tag/wall-latest) (`iowall-waveshare7b-full.bin` or
`iowall-waveshare7b-rev3-full.bin` for the Waveshare board).

## Build it

ESP-IDF 5.4 (`.github/workflows/tab5-wall.yml` builds it with 5.4.4; 5.4.2 lacks what the USB host component the board package pulls in needs):

```sh
cd devices/tab5-wall
idf.py set-target esp32p4
idf.py build flash monitor

# the Waveshare board, in a build folder of its own (WALL_CHIP=rev3 as well for a revision 3 chip)
WALL_BOARD=waveshare7b idf.py -B build-7b -D SDKCONFIG=sdkconfig.7b build flash monitor
```

The board is `WALL_BOARD` when the build folder is first made (`tab5` when it is not set). It picks the board's
package (`main/idf_component.yml`), its settings (`sdkconfig.<board>` on top of `sdkconfig.defaults`) and what
`main/board.h` says of it: the screen's size, which way it turns, the name of its file in the release.

The components come from Espressif's registry (`main/idf_component.yml`): the board's package (Espressif's for the
Tab5, Waveshare's 1.0 for the 7B: the last that draws through esp_lvgl_port), LVGL 9.3, and ESP-Hosted 1.4 with
esp_wifi_remote for the Wi-Fi on the board's ESP32-C6. A build made by hand is version `dev` and
never updates itself; `WALL_VERSION=1.2 idf.py build` gives it a version.

| File | What |
|---|---|
| `main/main.c` | starts everything |
| `main/board.h` | what differs between the boards |
| `main/settings.c` | what is kept across restarts (NVS) |
| `main/net.c` | Wi-Fi, the clock (SNTP) |
| `main/api.c` | HTTP to the start page with the device's app password |
| `main/feed.c` | `/api/wall/feed` every minute, the photos (`/api/wall/photo/<id>.jpg`, the P4's JPEG decoder), taps |
| `main/ui_views.c` | the views beside the wall (`/api/trmnl/<screen>`) and the swipe between them |
| `main/ui.c`, `ui_wall.c`, `ui_setup.c`, `ui_panels.c` | the screens (LVGL), laid out for 1280 × 720; `P()` brings each size to the board's screen |
| `main/alarm.c` | timers, alarms, the sound |
| `main/power.c` | the battery's level (the Tab5's INA226) |
| `main/wall_blend.h` | see-through drawing: the loops LVGL uses in place of its own |
| `main/bench.c` | the screen measured on the board: Settings › Screen › Measure, and by itself on a pull request's build |
| `main/ota.c` | updates from the release `wall-latest` (each board its own file) |
| `main/icons.c` | the weather icons, made by `tools/make_icons.py` |
| `main/fonts/` | Inter (SIL Open Font License, `OFL.txt`) |
| `tools/sim/` | the screens on a PC: what each touch costs to draw, and pictures of every screen |

The server side is in the start page: `iostart/app/wall.py`.

## What keeps it quick

The screen is drawn in software, a whole area at a time, into memory that is slow for its size (on the 7B a screen
of pixels is filled in 8 ms and copied in 17); what a touch costs is how many pixels are drawn for it, and how. LVGL
draws, for every area that changed, the topmost thing that covers the area and all that is above it. What follows from
that, and is worth keeping when a screen is added or changed:

- **A panel is part of the screen it opens over** (`kit_panel`), not of LVGL's top layer: nothing on the top layer
  ever counts as covering, so a panel there had the photo and the whole wall drawn again under it at every frame of
  a scroll. What scrolls in a panel is a plain rectangle in the card's colour: round corners cover nothing.
- **A panel's rows are drawn once and kept as a picture** (`kit_panel` in `ui.c`), as wide and as tall as all of
  them. A frame of a scroll is then a copy of the part in view and the drawing of the strip that comes into view, not
  every text, slider and button a few pixels further up. A row that changes (a switch, a text, the cursor) is drawn
  again where it is: LVGL says which area is no longer right. Only the rows in view are kept right, and a picture
  there is no memory for is done without (the log says so). `kit_panel_keep(false)` draws every row each time, as
  before, to compare.
- **One layer behind the wall's text.** A photo's shades (darker where the text is, as dark as the photo is bright)
  are worked into its pixels once, when it is decoded (`wall_shade_photo`), on the photos' task. The sky and its two
  see-through shades are drawn only while no photo fills the screen.
- **Only what changed is made again.** The feed comes every minute and mostly says the same: the wall compares each
  part's share of it with what it drew (`ui_wall_feed_changed`) and leaves the rest alone, and a view does the same
  with its answer. A text or a colour set to what it already is still draws the thing again in LVGL, as does showing
  what is shown: `kit_set_text` and `kit_show` look first.
- **A text that changes every second has a width of its own** (a running timer): a label that grows by a pixel lays
  out and draws everything around it.
- **A key pressed draws that key**, not the keyboard (`kit_keyboard`).
- **Nothing slow on the screen's task:** settings are written to the flash by a task of their own, the network and
  the photos have theirs.
- **See-through drawing has loops of its own** (`main/wall_blend.h`, which LVGL's blending code includes: LVGL's
  hook for assembly). LVGL mixes two colours in a function it calls for every pixel: black at 3/4 over a photo, as
  under a view, took about 130 ms a screen on the board. The loops here draw the same to the bit: a view's and a
  panel's darkening, a photo fading in, every letter and every round corner.
- **The 7B's panel turns the picture itself** when the board is mounted the other way round (`screen_start` in
  `main.c`): its driver chip scans the other way on a command. The board package has the P4's pixel processor turn
  every frame instead, which took 27 ms a screen. The Tab5's panel stands on its side and cannot: there the pixel
  processor turns every frame by a quarter.

`tools/sim/run.sh` builds LVGL and the firmware's screens for a PC, goes through the wall, the panels and the views
with scripted touches, and prints for each step how many frames it took and how many screens' worth of pixels were
filled, copied and blended in them (`./run.sh 7b` for the Waveshare's size, `MAIN=… ./run.sh` for another copy of
`main/`, to compare). The pictures of what it passed are in `tools/sim/out/`. It counts work, not time: how long a
frame takes on the board is what Settings › Screen says. Its clock stands still at one day, so two runs draw the
same. `./run.sh 7b check` goes through the script and a few hundred touches more on every panel twice, with a panel's
rows kept as a picture and with every row drawn, and fails when a frame of the one is not, pixel for pixel, that of
the other: run it after a change to a panel or to `kit_panel`. It also draws every frame once more with LVGL's
own see-through drawing in place of `wall_blend.h`, and fails when the two differ. `SIM_LOG=1` shows the firmware's
own log lines.

On the board, `main/bench.c` does the same touches with a finger that is not there and times every frame: Settings ›
Screen › Measure, and its lines are in the log as well (`bench: Settings scrolled: 150 frames of 61%, …`). It
scrolls Settings three times over: as it is, with every row drawn each time, and with the screen turned around. A pull
request's build (version `pr…`) runs it by itself half a minute after it starts, so a board on a cable is measured
by restarting it and reading its log.
