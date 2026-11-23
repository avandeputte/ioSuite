#!/bin/bash
# The wall display's screens on a PC (sim.c): builds LVGL and the firmware's own screens with gcc, runs the script in
# sim.c and prints what each step of it cost; the screens it passes are in out/*.ppm.
#
#   ./run.sh                    the Tab5's screen (1280 x 720)
#   ./run.sh 7b                 the Waveshare 7B's (1024 x 600)
#   ./run.sh tab5 -v            every area sent to the panel as well
#   MAIN=/path/to/other/main ./run.sh    another copy of the firmware (the one before a change, to compare)
#   ./run.sh 7b check           a panel keeps a picture of its rows (kit_panel): the script and a few hundred touches
#                               more, once with and once without, and every frame of the two must be the same
#   SIM_RUN="valgrind --tool=callgrind --dump-before=report --callgrind-out-file=out/cg" ./run.sh 7b
#                               under a tool: here the instructions each step took, one file per step, by function
#
# Needs gcc, git and binutils. LVGL 9.3.0 and cJSON are fetched once into .src/ (SIM_SRC to keep them elsewhere).
set -e
cd "$(dirname "$0")"
HERE=$PWD
BOARD=${1:-tab5}
[ $# -gt 0 ] && shift
MAIN=${MAIN:-$HERE/../../main}
SRC=${SIM_SRC:-$HERE/.src}
mkdir -p "$SRC" out
[ -d "$SRC/lvgl" ] || git clone -q --depth 1 --branch v9.3.0 https://github.com/lvgl/lvgl.git "$SRC/lvgl"
[ -d "$SRC/cJSON" ] || git clone -q --depth 1 --branch v1.7.18 https://github.com/DaveGamble/cJSON.git "$SRC/cJSON"
LV=$SRC/lvgl
DEFS="-DLV_CONF_INCLUDE_SIMPLE -I$HERE/stub"
if [ ! -f "$SRC/lvgl.a" ]; then
    echo "building LVGL (once)…" >&2
    rm -rf "$SRC/obj" && mkdir -p "$SRC/obj"
    find "$LV/src" -name '*.c' | grep -v -E "/drivers/|/draw/(nxp|renesas|vg_lite|sdl|opengles|nema_gfx|espressif|dma2d)/" |
        xargs -P "$(nproc)" -I{} sh -c 'gcc -O2 -w -c "$1" -I"$2" -I"$2/src" $3 -o "$4/$(echo "$1" | md5sum | cut -c1-12).o"' _ {} "$LV" "$DEFS" "$SRC/obj"
    ar rcs "$SRC/lvgl.a" "$SRC"/obj/*.o
fi
B=$(mktemp -d)
trap 'rm -rf "$B"' EXIT
CF="-O2 -g -Wall -Wno-format-truncation -D_GNU_SOURCE -include stdlib.h -include assert.h -I$MAIN -I$HERE/stub -I$LV -I$LV/src -I$SRC/cJSON $DEFS"
[ "$BOARD" = 7b ] && CF="$CF -DWALL_BOARD_WAVESHARE7B"
(cd "$MAIN/fonts" && for f in Inter-Regular.ttf Inter-SemiBold.ttf InterDisplay-Light.ttf; do ld -r -b binary -z noexecstack -o "$B/$f.o" "$f"; done)
for s in ui.c ui_wall.c ui_views.c ui_panels.c ui_setup.c icons.c alarm.c power.c; do gcc $CF -c "$MAIN/$s" -o "$B/$s.o" & done
gcc $CF -c sim.c -o "$B/sim.o" &
gcc $CF -w -c "$SRC/cJSON/cJSON.c" -o "$B/cJSON.o" &
wait
gcc -o "$B/sim" "$B"/*.o "$SRC/lvgl.a" -lm -Wl,--wrap=lv_draw_sw_blend
if [ "$1" = check ]; then
    SIM_FRAMES=out/frames-kept.txt SIM_KEEP=1 "$B/sim" > /dev/null
    SIM_FRAMES=out/frames-drawn.txt SIM_KEEP=0 "$B/sim" > /dev/null
    if cmp -s out/frames-kept.txt out/frames-drawn.txt; then
        echo "$(wc -l < out/frames-kept.txt) frames, each the same with the picture kept as with every row drawn"
    else
        at=$(diff out/frames-kept.txt out/frames-drawn.txt | sed -n 's/^< \([0-9]*\) .*/\1/p' | head -1)
        echo "the frames differ, first at ${at:-?} ms (SIM_SHOT_AT=$at SIM_KEEP=1 and =0 save that screen to compare)"
        exit 1
    fi
    exit 0
fi
$SIM_RUN "$B/sim" "$@"
