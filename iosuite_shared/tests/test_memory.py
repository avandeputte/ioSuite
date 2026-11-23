"""How the server's memory is read (iosuite_shared.memory), for the helper and ioPix's job process: the smallest limit
that applies, what is in use without the caches, and what a process and its children hold."""
import os
from pathlib import Path

import pytest

from iosuite_shared import memory

pytestmark = pytest.mark.skipif(os.name != "posix" or not Path("/proc/self/statm").exists(), reason="memory is read from /proc")


def test_this_machine_can_be_read():
    assert memory.limit() and memory.used() is not None and memory.used() <= memory.limit()
    assert memory.tree(os.getpid()) > 10 * memory.MB
    assert memory.tree(2 ** 30) == 0  # no such process
    assert memory.gb(3 * 1024 ** 3 + 200 * memory.MB) == "3.2 GB"


def test_the_smallest_cgroup_limit_applies_and_the_caches_are_not_in_use(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    leaf = root / "lxc" / "system.slice" / "iosuite.service"
    leaf.mkdir(parents=True)
    (leaf / "memory.max").write_text("max\n")
    (root / "lxc" / "memory.max").write_text(str(2 * 1024 ** 3) + "\n")
    (root / "lxc" / "memory.current").write_text(str(1024 ** 3) + "\n")
    (root / "lxc" / "memory.stat").write_text(f"anon 1\ninactive_file {200 * memory.MB}\nactive_file {100 * memory.MB}\nslab_reclaimable {24 * memory.MB}\n")
    monkeypatch.setattr(memory, "CGROUP", root)
    monkeypatch.setattr(memory, "_cgroup_dirs", lambda: [leaf, leaf.parent, root / "lxc", root])
    monkeypatch.setattr(memory, "_meminfo", lambda: {"MemTotal": 64 * 1024 ** 3, "MemAvailable": 60 * 1024 ** 3})
    assert memory.limit() == 2 * 1024 ** 3
    assert memory.used() == 1024 ** 3 - 324 * memory.MB  # the file cache and reclaimable slab are not "in use"


def test_without_a_cgroup_the_machine_s_own_numbers_count(monkeypatch):
    monkeypatch.setattr(memory, "_cgroup_dirs", lambda: [])
    monkeypatch.setattr(memory, "_meminfo", lambda: {"MemTotal": 8 * 1024 ** 3, "MemAvailable": 5 * 1024 ** 3})
    assert memory.limit() == 8 * 1024 ** 3 and memory.used() == 3 * 1024 ** 3
    monkeypatch.setattr(memory, "_meminfo", lambda: {})
    assert memory.limit() is None and memory.used() is None  # not Linux: nothing is known, nothing is limited
