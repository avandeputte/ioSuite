"""Medicines and allergies: each person's own, like every figure in ioHealth (nobody else sees them, admins neither).

A medicine has a name, a dose ("10 mg", "1 tablet"), what it is for, a note ("with food"), the times of day it is
taken (local "HH:MM", in the person's zone: webapi.zone_of) and the days of the week (Python's weekday digits,
"0123456" for every day). No times: taken when needed, and each one taken is written down as it happens. A medicine
can start and end on a date, and be stopped (it stays, with its history, under "Stopped").

Every dose that was due is a row in hlt_medicine_doses once it is ticked (taken) or skipped: (medicine, day, slot),
slot being the time it was due ("08:00"), or for one taken when needed the time it was taken ("14:32:10"). A dose
without a row was not ticked.

The reminder (push kind health_meds, Settings › Account › Notifications): at each due time, one notification for the
doses due then that are not ticked yet, with a "Taken" button where the device shows buttons (it ticks them all); a tap
opens the Medicines page. Sent once per time and day, and not after REMIND_WINDOW (a server that was off at 8 does not
remind of the 8 o'clock pills at noon).

Allergies: a name, what it does (the reaction), how bad (mild, moderate, severe) and a note. They and the medicines
marked "on the card" go on the emergency card (emergency.py).
"""
import datetime as dt
import logging
import re

from fastapi import APIRouter, HTTPException, Request
from iosuite_shared import push
from iosuite_shared.access import json_body
from iosuite_shared.errors import Invalid

from iohealth import access, db, webapi
from iohealth.auth import uid as uid_of

log = logging.getLogger("iohealth.meds")
router = APIRouter()
APP = "iohealth"
KIND = "health_meds"
REMIND_WINDOW = dt.timedelta(hours=2)
EVERY_DAY = "0123456"
SEVERITIES = ("mild", "moderate", "severe")
MAX_TIMES = 8
MAX_MEDICINES = 200
MAX_ALLERGIES = 200
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
HISTORY_DAYS = 90


# ------------------------------------------------------------------ reading and checking input

def _text(b: dict, key: str, n: int, required: bool = False) -> str:
    v = b.get(key)
    v = "" if v is None else str(v).strip()
    if required and not v:
        raise Invalid(f"{key.capitalize()} is needed")
    if len(v) > n:
        raise Invalid(f"{key.capitalize()} is at most {n} characters")
    return v


def _times(v) -> str:
    """"08:00,20:00" from a list or a comma list of times; sorted, each once."""
    if v is None or v == "":
        return ""
    items = v if isinstance(v, list) else str(v).split(",")
    out = set()
    for t in items:
        t = str(t).strip()
        if not t:
            continue
        m = TIME_RE.match(t)
        if not m:
            raise Invalid(f"{t} is not a time of day (HH:MM)")
        out.add(f"{int(m.group(1)):02d}:{m.group(2)}")
    if len(out) > MAX_TIMES:
        raise Invalid(f"At most {MAX_TIMES} times a day")
    return ",".join(sorted(out))


def _days(v) -> str:
    if v is None or v == "":
        return EVERY_DAY
    items = v if isinstance(v, list) else list(str(v))
    try:
        out = sorted({int(x) for x in items})
    except (TypeError, ValueError):
        raise Invalid("Days are the weekdays 0 (Monday) to 6 (Sunday)") from None
    if not out or out[0] < 0 or out[-1] > 6:
        raise Invalid("Days are the weekdays 0 (Monday) to 6 (Sunday)")
    return "".join(str(x) for x in out)


def _date(v, what: str):
    if v in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise Invalid(f"{what} is a date (YYYY-MM-DD)") from None


def _iso(d) -> str | None:
    return d.isoformat() if d else None


# ------------------------------------------------------------------ medicines

COLS = "id, name, dose, reason, note, times, days, start_on, end_on, remind, on_card, stopped_on, created_at"


def _row(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "dose": r["dose"], "reason": r["reason"], "note": r["note"],
            "times": [t for t in (r["times"] or "").split(",") if t], "days": [int(x) for x in r["days"] or EVERY_DAY],
            "asNeeded": not r["times"], "startOn": _iso(r["start_on"]), "endOn": _iso(r["end_on"]),
            "remind": bool(r["remind"]), "onCard": bool(r["on_card"]), "stoppedOn": _iso(r["stopped_on"])}


def active_on(m: dict, day: dt.date) -> bool:
    """Whether a medicine (a row of _row) is being taken on `day`."""
    def d(k):
        return dt.date.fromisoformat(m[k]) if m.get(k) else None
    start, end, stopped = d("startOn"), d("endOn"), d("stoppedOn")
    return (not start or start <= day) and (not end or day <= end) and (not stopped or day < stopped)


def medicines(uid: int) -> list:
    return [_row(r) for r in db.qd(f"SELECT {COLS} FROM hlt_medicines WHERE user_id = %s ORDER BY name, id", (uid,))]


def medicine(uid: int, mid: int) -> dict:
    r = db.qd(f"SELECT {COLS} FROM hlt_medicines WHERE user_id = %s AND id = %s", (uid, int(mid)))
    if not r:
        raise HTTPException(404, "No such medicine of yours")
    return _row(r[0])


def _fields(b: dict, partial: bool) -> dict:
    """The columns a POST or PATCH body sets."""
    out = {}
    if not partial or "name" in b:
        out["name"] = _text(b, "name", 128, required=True)
    for key, col, n in (("dose", "dose", 64), ("reason", "reason", 128), ("note", "note", 255)):
        if not partial or key in b:
            out[col] = _text(b, key, n)
    if not partial or "times" in b:
        out["times"] = _times(b.get("times"))
    if not partial or "days" in b:
        out["days"] = _days(b.get("days"))
    for key, col in (("startOn", "start_on"), ("endOn", "end_on"), ("stoppedOn", "stopped_on")):
        if not partial or key in b:
            out[col] = _date(b.get(key), key)
    for key, col, default in (("remind", "remind", True), ("onCard", "on_card", True)):
        if not partial or key in b:
            out[col] = bool(b.get(key, default))
    if out.get("start_on") and out.get("end_on") and out["end_on"] < out["start_on"]:
        raise Invalid("It cannot end before it starts")
    return out


def add(uid: int, b: dict) -> dict:
    f = _fields(b, False)
    if db.one("SELECT count(*) FROM hlt_medicines WHERE user_id = %s", (uid,))[0] >= MAX_MEDICINES:
        raise Invalid(f"At most {MAX_MEDICINES} medicines")
    mid = db.ex(f"INSERT INTO hlt_medicines ({', '.join(f)}, user_id) VALUES ({', '.join(['%s'] * len(f))}, %s)", [*f.values(), uid])
    return medicine(uid, mid)


def change(uid: int, mid: int, b: dict) -> dict:
    old = medicine(uid, mid)
    f = _fields(b, True)
    start = f["start_on"] if "start_on" in f else _date(old["startOn"], "startOn")
    end = f["end_on"] if "end_on" in f else _date(old["endOn"], "endOn")
    if start and end and end < start:
        raise Invalid("It cannot end before it starts")
    if f:
        db.ex(f"UPDATE hlt_medicines SET {', '.join(f'{c} = %s' for c in f)} WHERE user_id = %s AND id = %s", [*f.values(), uid, int(mid)])
    return medicine(uid, mid)


def remove(uid: int, mid: int) -> None:
    medicine(uid, mid)
    with db.tx():
        db.ex("DELETE FROM hlt_medicine_doses WHERE user_id = %s AND medicine_id = %s", (uid, int(mid)))
        db.ex("DELETE FROM hlt_medicines WHERE user_id = %s AND id = %s", (uid, int(mid)))


# ------------------------------------------------------------------ doses

def _local_unix(day: dt.date, slot: str, loc) -> int:
    hh, mm = (int(x) for x in slot[:5].split(":"))
    return int(dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=loc).timestamp())


def _marks(uid: int, frm: dt.date, to: dt.date) -> dict:
    """{(medicine, day, slot): (taken_at as Unix seconds or None, skipped)} from frm to to (inclusive)."""
    return {(r[0], r[1], r[2]): (db.unix(r[3]), bool(r[4])) for r in db.q(
        "SELECT medicine_id, day, slot, taken_at, skipped FROM hlt_medicine_doses WHERE user_id = %s AND day BETWEEN %s AND %s",
        (uid, frm, to))}


def due(meds: list, day: dt.date) -> list:
    """The scheduled doses of a day: [(medicine, slot)], by time."""
    out = [(m, t) for m in meds if m["times"] and active_on(m, day) and day.weekday() in m["days"] for t in m["times"]]
    return sorted(out, key=lambda x: (x[1], x[0]["name"].lower()))


def day_doses(uid: int, day: dt.date, loc, meds: list = None) -> dict:
    """{date, doses: [{medicine, name, dose, note, slot, at, taken, skipped}], asNeeded: [{medicine, name, dose, taken: [...]}]}."""
    meds = medicines(uid) if meds is None else meds
    marks = _marks(uid, day, day)
    doses = []
    for m, slot in due(meds, day):
        taken, skipped = marks.get((m["id"], day, slot), (None, False))
        doses.append({"medicine": m["id"], "name": m["name"], "dose": m["dose"], "note": m["note"], "slot": slot,
                      "at": _local_unix(day, slot, loc), "taken": taken, "skipped": skipped})
    extra = []
    for m in meds:
        if not m["times"] and active_on(m, day):
            taken = sorted(((s, t) for (mid, d, s), (t, _sk) in marks.items() if mid == m["id"] and t), key=lambda x: x[0])
            extra.append({"medicine": m["id"], "name": m["name"], "dose": m["dose"], "note": m["note"],
                          "taken": [{"slot": s, "at": t} for s, t in taken]})
    return {"date": day.isoformat(), "doses": doses, "asNeeded": extra}


def mark(uid: int, mid: int, day: dt.date, slot: str | None, taken: bool = True, skipped: bool = False, loc=None) -> dict:
    """Tick a dose taken (or skipped), or untick it (neither). No slot: one taken now, of a medicine taken when needed."""
    m = medicine(uid, mid)
    loc = loc or webapi.zone_of(uid)
    now = dt.datetime.now(loc)
    if slot is None or slot == "":
        if m["times"]:
            raise Invalid("Say which dose: this medicine has set times")
        day, slot = now.date(), now.strftime("%H:%M:%S")
        taken, skipped = True, False
    else:
        slot = str(slot)
        if not (TIME_RE.match(slot) or re.match(r"^\d\d:\d\d:\d\d$", slot)):
            raise Invalid("A dose is named by its time (HH:MM)")
        if day > now.date() + dt.timedelta(days=1) or day < now.date() - dt.timedelta(days=HISTORY_DAYS):
            raise Invalid("That day is too far off")
    if not taken and not skipped:
        db.ex("DELETE FROM hlt_medicine_doses WHERE user_id = %s AND medicine_id = %s AND day = %s AND slot = %s", (uid, mid, day, slot))
        return {"medicine": mid, "day": day.isoformat(), "slot": slot, "taken": None, "skipped": False}
    at = db.naive(now) if taken else None
    db.ex("INSERT INTO hlt_medicine_doses (medicine_id, day, slot, taken_at, skipped, user_id) VALUES (%s, %s, %s, %s, %s, %s) "
          "ON DUPLICATE KEY UPDATE taken_at = VALUES(taken_at), skipped = VALUES(skipped)",
          (mid, day, slot, at, bool(skipped) and not taken, uid))
    return {"medicine": mid, "day": day.isoformat(), "slot": slot, "taken": db.unix(at), "skipped": bool(skipped) and not taken}


def take_all(uid: int, day: dt.date, slot: str) -> int:
    """Every dose due at `slot` on `day` that is not ticked yet, ticked taken (the reminder's Taken button)."""
    marks = _marks(uid, day, day)
    n = 0
    for m, s in due(medicines(uid), day):
        if s == slot and (m["id"], day, s) not in marks:
            mark(uid, m["id"], day, s)
            n += 1
    return n


def history(uid: int, days: int, loc) -> dict:
    """The last `days` days of the scheduled doses: per day and medicine, how many were due, taken and skipped."""
    days = max(1, min(int(days), HISTORY_DAYS))
    today = dt.datetime.now(loc).date()
    frm = today - dt.timedelta(days=days - 1)
    meds = medicines(uid)
    marks = _marks(uid, frm, today)
    out = []
    for i in range(days):
        d = frm + dt.timedelta(days=i)
        per: dict = {}
        for m, slot in due(meds, d):
            p = per.setdefault(m["id"], {"medicine": m["id"], "due": 0, "taken": 0, "skipped": 0})
            p["due"] += 1
            taken, skipped = marks.get((m["id"], d, slot), (None, False))
            p["taken"] += 1 if taken else 0
            p["skipped"] += 1 if skipped else 0
        out.append({"date": d.isoformat(), "medicines": list(per.values())})
    return {"from": frm.isoformat(), "to": today.isoformat(), "days": out,
            "names": {m["id"]: m["name"] for m in meds}}


# ------------------------------------------------------------------ allergies

def _allergy(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "reaction": r["reaction"], "severity": r["severity"], "note": r["note"]}


def allergies(uid: int) -> list:
    order = "FIELD(severity, 'severe', 'moderate', 'mild', ''), name"
    return [_allergy(r) for r in db.qd(f"SELECT id, name, reaction, severity, note FROM hlt_allergies WHERE user_id = %s ORDER BY {order}", (uid,))]


def _allergy_fields(b: dict, partial: bool) -> dict:
    out = {}
    if not partial or "name" in b:
        out["name"] = _text(b, "name", 128, required=True)
    for key, n in (("reaction", 255), ("note", 255)):
        if not partial or key in b:
            out[key] = _text(b, key, n)
    if not partial or "severity" in b:
        s = _text(b, "severity", 16).lower()
        if s and s not in SEVERITIES:
            raise Invalid("Severity is mild, moderate or severe")
        out["severity"] = s
    return out


def allergy(uid: int, aid: int) -> dict:
    r = db.qd("SELECT id, name, reaction, severity, note FROM hlt_allergies WHERE user_id = %s AND id = %s", (uid, int(aid)))
    if not r:
        raise HTTPException(404, "No such allergy of yours")
    return _allergy(r[0])


# ------------------------------------------------------------------ the reminder

def reminders(now: dt.datetime = None) -> int:
    """At each due time, in each person's zone: the doses due then and not ticked, in one notification (run every
    minute by the app)."""
    sent = 0
    for u in push.recipients(KIND):
        uid = u["id"]
        try:
            sent += remind(uid, now)
        except Exception:  # noqa: BLE001 - one person's medicines never stop the others' reminders
            log.exception("medicine reminders of account %s", uid)
    return sent


def remind(uid: int, now: dt.datetime = None) -> int:
    loc = webapi.zone_of(uid)
    local = (now or dt.datetime.now(loc)).astimezone(loc)
    day = local.date()
    meds = [m for m in medicines(uid) if m["remind"]]
    if not meds:
        return 0
    marks = _marks(uid, day, day)
    by_slot: dict = {}
    for m, slot in due(meds, day):
        at = dt.datetime.fromtimestamp(_local_unix(day, slot, loc), loc)
        if at <= local < at + REMIND_WINDOW and (m["id"], day, slot) not in marks:
            by_slot.setdefault(slot, []).append(m)
    sent = 0
    for slot, ms in by_slot.items():
        key = f"health:meds:{day}:{slot}"
        if push.was_sent(uid, key):
            continue
        names = [m["name"] for m in ms]
        title = f"Time for {names[0]}" if len(names) == 1 else f"Time for {', '.join(names[:-1])} and {names[-1]}"
        body = "\n".join(" · ".join(x for x in (m["name"] if len(ms) > 1 else "", m["dose"], m["note"]) if x) for m in ms).strip()
        post = push.link(APP, "api/medicines/taken")
        actions = [{"action": "taken", "title": "Taken", "post": post, "body": {"day": day.isoformat(), "slot": slot}}] if post else None
        sent += push.notify(uid, KIND, title[:120], body or f"Due at {slot}", url=push.link(APP, "#/medicines"),
                            once=key, tag=f"meds-{slot}", actions=actions)
    return sent


# ------------------------------------------------------------------ routes

def _day_param(request: Request, loc) -> dt.date:
    v = request.query_params.get("date")
    return _date(v, "date") if v else dt.datetime.now(loc).date()


@router.get("/api/medicines", dependencies=[access.signed_in])
def get_medicines(request: Request):
    """Your medicines, your allergies and the doses of a day (date, as left out: today), tz. {medicines, allergies,
    day: {date, doses, asNeeded}}."""
    uid, loc = uid_of(request), webapi.location(request)
    meds = medicines(uid)
    return {"medicines": meds, "allergies": allergies(uid), "day": day_doses(uid, _day_param(request, loc), loc, meds)}


@router.post("/api/medicines", dependencies=[access.signed_in])
async def post_medicine(request: Request):
    """{name, dose?, reason?, note?, times?: ["08:00", ...] (none: taken when needed), days?: [0..6] (Monday 0; as left
    out: every day), startOn?, endOn?, stoppedOn?, remind? (true), onCard? (true)}."""
    return add(uid_of(request), await json_body(request))


@router.patch("/api/medicines/{mid}", dependencies=[access.signed_in])
async def patch_medicine(mid: int, request: Request):
    """Change the fields given (as POST /api/medicines). stoppedOn: a date stops it from that day (null: taken again)."""
    return change(uid_of(request), mid, await json_body(request))


@router.delete("/api/medicines/{mid}", dependencies=[access.signed_in])
def delete_medicine(mid: int, request: Request):
    """The medicine goes, with its history. Stop it instead to keep that (stoppedOn)."""
    remove(uid_of(request), mid)
    return {"ok": True}


@router.post("/api/medicines/taken", dependencies=[access.signed_in])
async def post_taken(request: Request):
    """{day, slot}: every dose due then that is not ticked yet, taken (the reminder's Taken button). {ticked: n}."""
    b = await json_body(request)
    day = _date(b.get("day"), "day")
    slot = _times(b.get("slot"))
    if not day or not slot or "," in slot:
        raise Invalid("Say the day and the time of the doses")
    return {"ticked": take_all(uid_of(request), day, slot)}


@router.post("/api/medicines/{mid}/doses", dependencies=[access.signed_in])
async def post_dose(mid: int, request: Request):
    """{day?, slot?, taken? (true), skipped? (false)}: tick the dose due at slot on day (as left out: today) taken or
    skipped; taken and skipped both false unticks it. Without slot, for a medicine taken when needed: one taken now.
    tz."""
    b = await json_body(request)
    uid, loc = uid_of(request), webapi.location(request)
    day = _date(b.get("day"), "day") or dt.datetime.now(loc).date()
    return mark(uid, mid, day, b.get("slot"), bool(b.get("taken", True)), bool(b.get("skipped", False)), loc)


@router.get("/api/medicines/history", dependencies=[access.signed_in])
def get_history(request: Request, days: int = 30):
    """The last days (30; at most 90) of your scheduled doses: {from, to, days: [{date, medicines: [{medicine, due,
    taken, skipped}]}], names: {id: name}}. tz."""
    return history(uid_of(request), days, webapi.location(request))


@router.get("/api/allergies", dependencies=[access.signed_in])
def get_allergies(request: Request):
    """Your allergies, the severe ones first."""
    return {"items": allergies(uid_of(request))}


@router.post("/api/allergies", dependencies=[access.signed_in])
async def post_allergy(request: Request):
    """{name, reaction?, severity? (mild, moderate or severe), note?}."""
    uid = uid_of(request)
    f = _allergy_fields(await json_body(request), False)
    if db.one("SELECT count(*) FROM hlt_allergies WHERE user_id = %s", (uid,))[0] >= MAX_ALLERGIES:
        raise Invalid(f"At most {MAX_ALLERGIES} allergies")
    aid = db.ex(f"INSERT INTO hlt_allergies ({', '.join(f)}, user_id) VALUES ({', '.join(['%s'] * len(f))}, %s)", [*f.values(), uid])
    return allergy(uid, aid)


@router.patch("/api/allergies/{aid}", dependencies=[access.signed_in])
async def patch_allergy(aid: int, request: Request):
    uid = uid_of(request)
    allergy(uid, aid)
    f = _allergy_fields(await json_body(request), True)
    if f:
        db.ex(f"UPDATE hlt_allergies SET {', '.join(f'{c} = %s' for c in f)} WHERE user_id = %s AND id = %s", [*f.values(), uid, int(aid)])
    return allergy(uid, aid)


@router.delete("/api/allergies/{aid}", dependencies=[access.signed_in])
def delete_allergy(aid: int, request: Request):
    uid = uid_of(request)
    allergy(uid, aid)
    db.ex("DELETE FROM hlt_allergies WHERE user_id = %s AND id = %s", (uid, int(aid)))
    return {"ok": True}
