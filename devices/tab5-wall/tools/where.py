#!/usr/bin/env python3
"""Where a measuring run on the board spent its time, by function.

A pull request's build measures the screen by itself half a minute after it starts (main/bench.c) and, after each
scene's line, logs where a timer found the screen's task two thousand times a second: "where:" lines of
<program counter>:<return address>*<times>. This names those places from the build's list of symbols (the .sym file
beside the .bin in the run's artifact) and prints, for each scene, the functions the samples fell in.

    tools/where.py serial.log iowall-waveshare7b.sym            the 20 functions most met in each scene
    tools/where.py serial.log iowall-waveshare7b.sym 40         the 40 most met

Under a function met in 4% of the samples or more are the functions its return addresses were in: for one that
calls nothing (memcpy, a lock let go) that is who called it; for others it may be whoever they last came back from.
A function drawn into the one that calls it (inline) counts as that one.
"""
import bisect
import collections
import re
import sys


def symbols(path):
    out = []
    for line in open(path, errors="replace"):
        f = line.split()
        if len(f) == 4 and f[2] in "tTwWaA":
            out.append((int(f[0], 16), int(f[1], 16), f[3]))
        elif len(f) == 3 and f[1] in "tTwWaA":
            out.append((int(f[0], 16), 0, f[2]))
    out.sort()
    return out


def name(syms, starts, at):
    i = bisect.bisect_right(starts, at) - 1
    while i >= 0:
        start, size, what = syms[i]
        if at - start > 0x10000:
            break
        if not size or at < start + size:
            return what
        i -= 1
    return "0x%x.. (not in the list: the chip's ROM, memcpy for one)" % (at & ~0xFF)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    syms = symbols(sys.argv[2])
    starts = [s[0] for s in syms]
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    scene, places, head = None, [], ""

    def say():
        if scene is None or not places:
            return
        n = sum(k for _, _, k in places)
        by, callers = collections.Counter(), collections.defaultdict(collections.Counter)
        for pc, ra, k in places:
            fn = name(syms, starts, pc)
            by[fn] += k
            callers[fn][name(syms, starts, ra)] += k
        print("\n%s\n  %s" % (scene, head))
        for fn, k in by.most_common(top):
            print("  %5.1f%%  %s" % (100.0 * k / n, fn))
            if k * 25 >= n:
                for who, c in callers[fn].most_common(5):
                    if who != fn:
                        print("            %5.1f%%  return address in %s" % (100.0 * c / n, who))

    last = None
    for line in open(sys.argv[1], errors="replace"):
        m = re.search(r"bench: (.*)", line)
        if not m:
            continue
        text = m.group(1).rstrip()
        if re.match(r"where: \d+ places", text):
            head = text[7:]
            scene, places = last, []
        elif text.startswith("where:"):
            for pc, ra, k in re.findall(r"([0-9a-f]+):([0-9a-f]+)\*(\d+)", text):
                places.append((int(pc, 16), int(ra, 16), int(k)))
        else:
            say()
            scene, places, last = None, [], text
    say()


if __name__ == "__main__":
    main()
