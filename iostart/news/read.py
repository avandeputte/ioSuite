"""Reading feeds: what a site publishes as RSS 2.0, RSS 1.0 (RDF), Atom or JSON Feed, as one shape; finding a site's
feed from its page; an article's HTML made safe to show; and OPML, the file readers exchange their lists of feeds in.

Nothing here asks the network or the database: bytes in, plain dicts out.

parse(data, url) -> {title, site, description, items: [item]}, item = {guid, title, link, author, published (epoch
seconds, or None), html (the article as the feed has it, cleaned), text (the same in plain words, cut short), image,
audio}. guid is the feed's own id for the item, else its link, else a hash of its title and date: what makes an item
the same one the next time the feed is read.
"""
import calendar
import datetime as dt
import hashlib
import html as htmllib
import json
import re
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.sax.saxutils import escape, quoteattr

from defusedxml import ElementTree as ET

MAX_ITEMS = 200        # of one feed, the newest as the feed orders them
MAX_HTML = 400_000     # of one article
TEXT_LEN = 400         # the plain words kept beside it (the lists' second line, the search)


class NotAFeed(ValueError):
    """The bytes are not a feed this reads."""


# ------------------------------------------------------------------ small things

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _ns(tag: str) -> str:
    return tag[1:].split("}", 1)[0].lower() if isinstance(tag, str) and tag.startswith("{") else ""


def _kids(el, name: str, ns: str | None = None):
    """el's children called name (whatever the namespace, or only those whose namespace contains ns)."""
    return [c for c in el if _local(c.tag) == name and (ns is None or ns in _ns(c.tag))]


def _first(el, name: str, ns: str | None = None):
    got = _kids(el, name, ns)
    return got[0] if got else None


def _str(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def http_url(url: str, base: str = "") -> str | None:
    """url against base, when that is an http(s) address; else None (javascript:, data:, mailto: lead nowhere here)."""
    if not (url or "").strip():
        return None
    try:
        full = urljoin(base, url.strip())
        parts = urlsplit(full)
    except ValueError:
        return None
    return full[:2000] if parts.scheme in ("http", "https") and parts.netloc else None


def when(s: str) -> int | None:
    """A feed's date as epoch seconds: RFC 822 ("Mon, 23 Nov 2026 08:00:00 GMT") or ISO 8601; None when it is neither.
    A date without a zone counts as UTC."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
            if not m:
                return None
            try:
                d = dt.datetime(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    try:
        t = calendar.timegm(d.utctimetuple())
    except (OverflowError, ValueError):
        return None
    return t if 0 < t < 4_102_444_800 else None  # 1970 .. 2100: anything else is a feed's mistake


# ------------------------------------------------------------------ an article's HTML, safe to show

# what stays, and of each its attributes; everything else goes, its text stays (a <div>'s words are kept, the div is not)
_KEEP = {"p": (), "br": (), "hr": (), "a": ("href", "title"), "img": ("src", "alt", "title", "width", "height"),
         "ul": (), "ol": (), "li": (), "blockquote": (), "pre": (), "code": (), "em": (), "strong": (), "b": (), "i": (),
         "u": (), "s": (), "sub": (), "sup": (), "h1": (), "h2": (), "h3": (), "h4": (), "h5": (), "h6": (),
         "figure": (), "figcaption": (), "table": (), "thead": (), "tbody": (), "tr": (), "th": (), "td": (),
         "dl": (), "dt": (), "dd": (), "small": (), "cite": (), "q": (), "abbr": ("title",), "time": (),
         "video": ("src", "poster", "controls"), "audio": ("src", "controls"), "source": ("src", "type")}
_VOID = {"br", "hr", "img", "source"}
_DROP = {"script", "style", "iframe", "object", "embed", "form", "noscript", "template", "svg", "math", "head", "title",
         "select", "textarea", "button"}  # these go with all they hold
_BLOCK = {"p", "br", "hr", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "figure", "figcaption", "tr",
          "div", "section", "article", "dt", "dd", "table", "ul", "ol"}
_URLS = {"href", "src", "poster"}


class _Clean(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.out, self.words, self.open, self.skip, self.image, self.size = base, [], [], [], 0, None, 0

    def _put(self, s: str) -> None:
        if self.size < MAX_HTML:
            self.out.append(s)
            self.size += len(s)

    def handle_starttag(self, tag, attrs):
        if tag in _DROP:
            self.skip += tag not in _VOID
            return
        if self.skip:
            return
        if tag in _BLOCK:
            self.words.append(" ")
        if tag not in _KEEP:
            return
        keep = []
        for k, v in attrs:
            if k not in _KEEP[tag] or v is None and k != "controls":
                continue
            if k in _URLS:
                v = http_url(v, self.base)
                if not v:
                    continue
            elif k in ("width", "height"):
                if not re.fullmatch(r"\d{1,5}", v.strip()):
                    continue
                v = v.strip()
            keep.append((k, v or ""))
        have = dict(keep)
        if tag == "img":
            if "src" not in have:  # a tracking pixel's data: address, or none at all
                return
            if {have.get("width"), have.get("height")} & {"0", "1"}:  # a counter, not a picture
                return
            if not self.image:
                self.image = have["src"]
            keep += [("loading", "lazy"), ("referrerpolicy", "no-referrer")]  # the picture's site is not told which page shows it
        if tag == "a":
            if "href" not in have:
                return self.open.append(None)  # its closing tag is dropped with it
            keep += [("target", "_blank"), ("rel", "noopener noreferrer nofollow")]
        if tag in ("video", "audio"):
            keep = [kv for kv in keep if kv[0] != "controls"] + [("controls", ""), ("preload", "none")]
        self._put("<" + tag + "".join(f" {k}={quoteattr(v)}" if v != "" or k not in ("controls",) else f" {k}" for k, v in keep) + ">")
        if tag not in _VOID:
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and tag in _KEEP and not self.skip:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in _DROP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _BLOCK:
            self.words.append(" ")
        if tag == "a" and self.open and self.open[-1] is None:
            self.open.pop()
            return
        if tag not in _KEEP or tag in _VOID or tag not in self.open:
            return
        while self.open:  # what was left open inside it closes with it
            t = self.open.pop()
            if t is not None:
                self._put(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if self.skip:
            return
        self._put(escape(data))
        if "figcaption" not in self.open:  # a picture's caption is not how the article begins
            self.words.append(data)

    def done(self) -> tuple[str, str, str | None]:
        self.close()
        while self.open:
            t = self.open.pop()
            if t is not None:
                self.out.append(f"</{t}>")
        return "".join(self.out).strip(), " ".join("".join(self.words).split()), self.image


def clean(markup: str, base: str = "") -> tuple[str, str, str | None]:
    """(html, text, image): markup with only the tags and attributes an article needs (no scripts, frames, styles,
    forms, handlers; links and pictures only to http(s), relative ones made whole against base; links open in a new
    tab), its plain words, and its first picture's address."""
    p = _Clean(base)
    try:
        p.feed(markup or "")
    except Exception:  # noqa: BLE001  a page HTMLParser gives up on: what it had so far
        pass
    return p.done()


def plain(markup: str) -> str:
    """A title or a name as plain words (feeds put <b> and &amp; in them)."""
    return clean(markup or "")[1] if "<" in (markup or "") or "&" in (markup or "") else " ".join((markup or "").split())


# ------------------------------------------------------------------ the feeds

def _item(guid, title, link, author, published, markup, base, image=None, audio=None) -> dict | None:
    body, text, first = clean(markup, link or base)
    title = plain(title)[:500]
    if not title and not text and not link:
        return None
    guid = (guid or link or "").strip()
    if not guid:
        guid = "h:" + hashlib.sha256(f"{title}\n{published}\n{text[:200]}".encode()).hexdigest()[:32]
    if len(guid) > 500:
        guid = "h:" + hashlib.sha256(guid.encode()).hexdigest()[:32]
    return {"guid": guid, "title": title or text[:80] or "(no title)", "link": link, "author": plain(author)[:200] or None, "published": published,
            "html": body, "text": text[:TEXT_LEN], "image": http_url(image or "", base) or first, "audio": http_url(audio or "", base)}


def _media(el, base: str) -> tuple[str | None, str | None]:
    """(image, audio) from an item's enclosure and media: elements."""
    image = audio = None
    for c in el.iter():
        name, a = _local(c.tag), c.attrib
        kind, url = (a.get("type") or "").lower(), a.get("url") or a.get("href") or ""
        if name == "enclosure" or (name == "link" and a.get("rel") == "enclosure") or (name == "content" and "search.yahoo.com/mrss" in _ns(c.tag)):
            if kind.startswith("image/") or (a.get("medium") == "image") or (not kind and re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", url, re.I)):
                image = image or url
            elif kind.startswith("audio/"):
                audio = audio or url
        elif name == "thumbnail" and "search.yahoo.com/mrss" in _ns(c.tag):
            image = image or url
        elif name == "image" and "itunes" in _ns(c.tag):
            image = image or a.get("href")
    return image, audio


def _rss(root, url: str) -> dict:
    ch = _first(root, "channel")
    if ch is None:
        raise NotAFeed("No channel in the feed")
    site = http_url(next((_str(c) for c in _kids(ch, "link") if not _ns(c.tag) or "rss" in _ns(c.tag) or "purl.org" in _ns(c.tag)), ""), url)
    nodes = _kids(ch, "item") or _kids(root, "item")  # RSS 1.0 keeps its items beside the channel
    items = []
    for it in nodes[:MAX_ITEMS]:
        link = http_url(next((_str(c) for c in _kids(it, "link") if _str(c)), ""), site or url)
        g = _first(it, "guid")
        if not link and g is not None and g.attrib.get("isPermaLink", "true") != "false":
            link = http_url(_str(g), site or url)
        body = _str(_first(it, "encoded")) or _str(_first(it, "description")) or _str(_first(it, "summary"))
        image, audio = _media(it, site or url)
        got = _item(_str(g) or it.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"), _str(_first(it, "title")), link,
                    _str(_first(it, "creator")) or _str(_first(it, "author")), when(_str(_first(it, "pubdate")) or _str(_first(it, "date"))), body, site or url, image, audio)
        if got:
            items.append(got)
    return {"title": plain(_str(_first(ch, "title")))[:300], "site": site, "description": plain(_str(_first(ch, "description")))[:500], "items": items}


def _xml_html(el) -> str:
    """An XHTML element as HTML text, by its local names (the cleaner takes it from there)."""
    name = _local(el.tag)
    if not name:  # a comment, a processing instruction
        return escape(el.tail or "")
    attrs = "".join(f" {_local(k)}={quoteattr(v)}" for k, v in el.attrib.items())
    return f"<{name}{attrs}>{escape(el.text or '')}{''.join(_xml_html(c) for c in el)}</{name}>{escape(el.tail or '')}"


def _atom_text(el) -> str:
    """An Atom text construct as HTML: type html (escaped inside), xhtml (elements inside), or text."""
    if el is None:
        return ""
    kind = (el.attrib.get("type") or "text").lower()
    if kind == "xhtml":
        return escape(el.text or "") + "".join(_xml_html(c) for c in el)
    return (el.text or "") if kind in ("html", "text/html") else escape(el.text or "")


def _atom_link(el, base: str, rel: str = "alternate") -> str | None:
    links = _kids(el, "link")
    for c in links:
        if (c.attrib.get("rel") or "alternate") == rel and (rel != "alternate" or (c.attrib.get("type") or "text/html").startswith(("text/html", "application/xhtml"))):
            return http_url(c.attrib.get("href") or "", base)
    return next((http_url(c.attrib.get("href") or "", base) for c in links if (c.attrib.get("rel") or "alternate") == rel), None)


def _atom(root, url: str) -> dict:
    base = http_url(root.attrib.get("{http://www.w3.org/XML/1998/namespace}base") or "", url) or url
    site = _atom_link(root, base)
    items = []
    for e in _kids(root, "entry")[:MAX_ITEMS]:
        link = _atom_link(e, base)
        body = _atom_text(_first(e, "content")) or _atom_text(_first(e, "summary")) or _str(_first(e, "description"))  # media:description (YouTube)
        if not body:
            group = _first(e, "group")
            body = escape(_str(_first(group, "description"))).replace("\n", "<br>") if group is not None else ""
        author = _first(e, "author")
        image, audio = _media(e, base)
        got = _item(_str(_first(e, "id")), plain(_atom_text(_first(e, "title"))), link, _str(_first(author, "name")) if author is not None else "",
                    when(_str(_first(e, "published")) or _str(_first(e, "updated"))), body, base, image, audio)
        if got:
            items.append(got)
    return {"title": plain(_atom_text(_first(root, "title")))[:300], "site": site, "description": plain(_atom_text(_first(root, "subtitle")))[:500], "items": items}


def _json(doc: dict, url: str) -> dict:
    if not isinstance(doc, dict) or "jsonfeed.org/version" not in str(doc.get("version", "")) or not isinstance(doc.get("items"), list):
        raise NotAFeed("Not a JSON Feed")
    site = http_url(str(doc.get("home_page_url") or ""), url)
    items = []
    for it in doc["items"][:MAX_ITEMS]:
        if not isinstance(it, dict):
            continue
        authors = it.get("authors") or ([it["author"]] if isinstance(it.get("author"), dict) else []) or doc.get("authors") or []
        author = next((str(a.get("name")) for a in authors if isinstance(a, dict) and a.get("name")), "")
        body = it.get("content_html") or (escape(str(it.get("content_text") or it.get("summary") or "")).replace("\n", "<br>"))
        audio = next((a.get("url") for a in it.get("attachments") or [] if isinstance(a, dict) and str(a.get("mime_type", "")).startswith("audio/")), None)
        got = _item(str(it.get("id") or ""), escape(str(it.get("title") or "")), http_url(str(it.get("url") or it.get("external_url") or ""), site or url), escape(author),
                    when(str(it.get("date_published") or it.get("date_modified") or "")), str(body), site or url, it.get("image") or it.get("banner_image"), audio)
        if got:
            items.append(got)
    return {"title": plain(escape(str(doc.get("title") or "")))[:300], "site": site, "description": plain(escape(str(doc.get("description") or "")))[:500], "items": items}


def parse(data: bytes, url: str = "") -> dict:
    """The feed in data (read from url), whichever of the four kinds it is. NotAFeed when it is none (a web page, say)."""
    head = data[:600].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head[:1] == b"{":
        try:
            return _json(json.loads(data.decode("utf-8", "replace")), url)
        except ValueError as e:
            raise NotAFeed(f"Not a feed: {e}")
    try:
        root = ET.fromstring(data.lstrip(b"\xef\xbb\xbf \t\r\n"))
    except Exception as e:  # noqa: BLE001  not XML (a page), or XML this may not read (entities)
        raise NotAFeed(f"Not a feed ({type(e).__name__})")
    name = _local(root.tag)
    if name in ("rss", "rdf"):
        return _rss(root, url)
    if name == "feed":
        return _atom(root, url)
    raise NotAFeed(f"Not a feed (a <{name}> document)")


# ------------------------------------------------------------------ a site's feed, from its page

_FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json", "application/json", "application/rdf+xml", "text/xml", "application/xml")
GUESSES = ("feed", "rss", "feed.xml", "rss.xml", "atom.xml", "index.xml", "feed/", "blog/feed")


class _Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found, self.title, self._in = [], "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title" and not self.title:
            self._in = True
        if tag == "link" and "alternate" in (a.get("rel") or "").lower().split() and (a.get("type") or "").lower().split(";")[0].strip() in _FEED_TYPES and a.get("href"):
            self.found.append((a["href"], a.get("title") or ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in = False

    def handle_data(self, data):
        if self._in:
            self.title += data


def discover(page: str, url: str) -> list[dict]:
    """The feeds a web page names in its head (<link rel="alternate" type="application/rss+xml" ...>), in its order:
    [{url, title}]. A site's comments feed comes last."""
    p = _Head()
    try:
        p.feed(page[:600_000])
    except Exception:  # noqa: BLE001
        pass
    out, seen = [], set()
    for href, title in p.found:
        full = http_url(href, url)
        if full and full not in seen:
            seen.add(full)
            out.append({"url": full, "title": " ".join(title.split())[:200]})
    out.sort(key=lambda f: "comment" in (f["title"] + f["url"]).lower())
    return out


def guesses(url: str) -> list[str]:
    """Where a site that names no feed often has one all the same, the likeliest first."""
    parts = urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}/"
    here = url if url.endswith("/") else url + "/"
    out = []
    for base in dict.fromkeys([here, root]):
        out += [urljoin(base, g) for g in GUESSES]
    yt = re.match(r"https?://(?:www\.)?youtube\.com/channel/(UC[\w-]{20,})", url)
    if yt:
        out.insert(0, f"https://www.youtube.com/feeds/videos.xml?channel_id={yt[1]}")
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ OPML: a list of feeds, as readers exchange it

def opml_read(data: bytes) -> list[dict]:
    """[{url, title, site, folder}] of an OPML file: every outline with an xmlUrl, under the name of the outline it sits
    in (the first level only: a folder in a folder counts as the outer one)."""
    try:
        root = ET.fromstring(data.lstrip(b"\xef\xbb\xbf \t\r\n"))
    except Exception as e:  # noqa: BLE001
        raise NotAFeed(f"Not an OPML file ({type(e).__name__})")
    body = _first(root, "body")
    if _local(root.tag) != "opml" or body is None:
        raise NotAFeed("Not an OPML file")
    out, seen = [], set()

    def walk(el, folder):
        for o in _kids(el, "outline"):
            a = {k.lower(): v for k, v in o.attrib.items()}
            name = " ".join((a.get("title") or a.get("text") or "").split())[:200]
            url = http_url(a.get("xmlurl") or "")
            if url:
                if url not in seen:
                    seen.add(url)
                    out.append({"url": url, "title": name, "site": http_url(a.get("htmlurl") or ""), "folder": folder})
            else:
                walk(o, folder or name or None)
    walk(body, None)
    return out


def opml_write(feeds: list[dict], title: str = "Feeds") -> bytes:
    """An OPML file of [{url, title, site, folder}], the folders in the order they first come."""
    def line(f, pad):
        site = f" htmlUrl={quoteattr(f['site'])}" if f.get("site") else ""
        return f'{pad}<outline type="rss" text={quoteattr(f.get("title") or f["url"])} title={quoteattr(f.get("title") or f["url"])} xmlUrl={quoteattr(f["url"])}{site}/>'
    folders: dict = {}
    for f in feeds:
        folders.setdefault(f.get("folder") or "", []).append(f)
    rows = [line(f, "    ") for f in folders.pop("", [])]
    for name, fs in folders.items():
        rows += [f"    <outline text={quoteattr(name)} title={quoteattr(name)}>", *[line(f, "      ") for f in fs], "    </outline>"]
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<opml version=\"2.0\">\n  <head><title>" + htmllib.escape(title) + "</title></head>\n  <body>\n"
            + "\n".join(rows) + "\n  </body>\n</opml>\n").encode()
