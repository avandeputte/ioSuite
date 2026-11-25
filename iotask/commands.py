"""ioTask's own commands from a shell, beside the migrate and check every app has (iosuite_shared.appcli):

    iosuite iotask import 3 tasks.ics      tasks (VTODOs) from an .ics file into a list
"""
from pathlib import Path


def add(sub) -> None:
    p = sub.add_parser("import", help="tasks (VTODOs) from an .ics file into a list")
    p.add_argument("list", type=int, help="the list's id")
    p.add_argument("file")
    p.set_defaults(run=_import)


def _import(a) -> None:
    from iotask import model
    print(model.import_text(a.list, Path(a.file).read_text(encoding="utf-8", errors="replace")))
