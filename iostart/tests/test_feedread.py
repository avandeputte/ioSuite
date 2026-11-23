from iostart import feedread as F

RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">
<channel><title>The &amp; Blog</title><link>https://blog.example/</link><description>Words</description>
<item><title>First &lt;b&gt;post&lt;/b&gt;</title><link>/a/1</link><guid isPermaLink="false">id-1</guid><pubDate>Mon, 23 Nov 2026 08:00:00 GMT</pubDate><dc:creator>Ann</dc:creator>
<description>short</description><content:encoded><![CDATA[<p onclick="x()">Hello <a href="/x" onmouseover="y">link</a><script>alert(1)</script><img src="pic.jpg" width="600"><img src="https://t.example/p.gif" width="1" height="1"><iframe src="https://evil"></iframe><a href="javascript:alert(1)">bad</a></p><div>tail]]></content:encoded>
<media:thumbnail url="https://blog.example/thumb.jpg"/></item>
<item><title>Podcast</title><guid>https://blog.example/a/2</guid><enclosure url="https://blog.example/e.mp3" type="audio/mpeg" length="1"/></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://atom.example/"><title type="html">Atom &amp;amp; Co</title><link rel="self" href="/feed"/><link href="/"/>
<entry><id>tag:1</id><title>One</title><link rel="alternate" type="text/html" href="one.html"/><updated>2026-11-22T10:00:00Z</updated><author><name>Bob</name></author>
<content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Para <em>em</em></p></div></content></entry>
<entry><id>tag:2</id><title>Two</title><summary type="html">&lt;p&gt;Sum&lt;/p&gt;</summary><published>2026-11-21</published></entry></feed>"""
JSONF = b'{"version":"https://jsonfeed.org/version/1.1","title":"J","home_page_url":"https://j.example","items":[{"id":"7","url":"https://j.example/7","content_text":"a\\nb","date_published":"2026-11-20T09:00:00-05:00","authors":[{"name":"Cy"}]}]}'


def test_rss():
    f = F.parse(RSS, "https://blog.example/feed")
    assert f["title"] == "The & Blog" and f["site"] == "https://blog.example/"
    a, b = f["items"]
    assert a["guid"] == "id-1" and a["title"] == "First post" and a["link"] == "https://blog.example/a/1" and a["author"] == "Ann" and a["published"] == 1795420800
    assert a["html"] == '<p>Hello <a href="https://blog.example/x" target="_blank" rel="noopener noreferrer nofollow">link</a><img src="https://blog.example/a/pic.jpg" width="600" loading="lazy" referrerpolicy="no-referrer">bad</p>tail'
    assert a["text"] == "Hello linkbad tail" and a["image"] == "https://blog.example/thumb.jpg"
    assert b["link"] == "https://blog.example/a/2" and b["audio"] == "https://blog.example/e.mp3" and b["published"] is None


def test_atom_and_json():
    f = F.parse(ATOM, "https://other.example/feed")
    assert f["title"] == "Atom & Co" and f["site"] == "https://atom.example/"
    one, two = f["items"]
    assert one["link"] == "https://atom.example/one.html" and one["author"] == "Bob" and one["html"] == "<p>Para <em>em</em></p>" and one["published"] == 1795341600
    assert two["html"] == "<p>Sum</p>" and two["guid"] == "tag:2" and two["published"] == 1795219200
    j = F.parse(JSONF, "https://j.example/feed.json")
    assert j["items"][0]["html"] == "a<br>b" and j["items"][0]["author"] == "Cy" and j["items"][0]["published"] == 1795183200


def test_not_feeds():
    import pytest
    for junk in (b"<html><body>hi</body></html>", b"plain", b'{"a":1}', b'<!DOCTYPE x [<!ENTITY a "b">]><rss><channel><title>&a;</title></channel></rss>'):
        with pytest.raises(F.NotAFeed):
            F.parse(junk)


def test_discover_and_opml():
    page = '<html><head><title>Site</title><link rel="alternate" type="application/rss+xml" title="Comments" href="/comments/feed"><link rel="alternate" type="application/atom+xml" href="atom.xml"><link rel="stylesheet" href="x.css"></head>'
    assert [f["url"] for f in F.discover(page, "https://s.example/blog/")] == ["https://s.example/blog/atom.xml", "https://s.example/comments/feed"]
    assert F.guesses("https://s.example/blog")[0] == "https://s.example/blog/feed" and "https://s.example/rss.xml" in F.guesses("https://s.example/blog")
    feeds = [{"url": "https://a.example/f", "title": 'A "q" & b', "site": "https://a.example", "folder": None}, {"url": "https://b.example/f", "title": "B", "site": None, "folder": "News <x>"}]
    assert F.opml_read(F.opml_write(feeds)) == feeds
    import pytest
    with pytest.raises(F.NotAFeed):
        F.opml_read(b"<rss/>")
