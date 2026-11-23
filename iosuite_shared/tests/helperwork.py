"""Functions the helper's tests send to it (module-level, so the helper can import them)."""
import ctypes
import logging
import os
import time

from iosuite_shared import helper


class Picky(Exception):
    """An error of the function's own: it comes back as it is."""


def add(a, b, times=1):
    return (a + b) * times


def pid():
    return os.getpid()


def fail():
    raise Picky("not this one")


def crash():
    ctypes.string_at(0)  # reads address 0: SIGSEGV, as a broken C library would


def sleep(s):
    time.sleep(s)
    return "woke"


def hog(mb):
    block = bytearray(mb * 1024 * 1024)
    for i in range(0, len(block), 4096):
        block[i] = 1
    time.sleep(5)
    return len(block)


def talk(n):
    logging.getLogger("iodocs.ocr").info("reading %d pages", n)
    for i in range(n):
        helper.emit(i)
    return n
