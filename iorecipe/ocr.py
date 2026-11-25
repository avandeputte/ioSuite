"""The text on a photo of a recipe (a page of a cookbook, a handwritten card that is neat enough, a screenshot), read
on this server: the picture goes nowhere else. The reading itself is the suite's (iosuite_shared.ocr), with the
suite's two settings for the program and the languages; where no reader is installed, reading a photo is simply not
offered."""
from iosuite_shared import ocr as shared

TIMEOUT = 90  # seconds for one photo

available = shared.available
languages = shared.languages


def read(raw: bytes) -> str:
    """The text on the picture. Invalid when it is not a picture, when nothing can be read, or without a reader."""
    return shared.read(raw, timeout=TIMEOUT)
