#!/usr/bin/env python3
"""The structure gate for every page in this repo, read from the files.

seo_check.py proves what the live server sends. This proves the files are
right BEFORE they ship, so a missing canonical or an unsized image is caught
on the push that adds it instead of a day later in Search Console. It needs
nothing beyond the standard library, so it runs on the deploy runner as is.

Per page (every index.html, plus 404.html):
  head       lang, a title and description in range, canonical, Open Graph
             and Twitter tags with an absolute 1200x630 image that exists
  robots     indexable pages carry no noindex; the 404 carries it
  schema     every JSON-LD block parses; Person on every indexable page,
             ProfessionalService on home, Service on the other pages
  headings   exactly one H1 and no skipped level
  images     alt, width, height and loading on every <img>, a real file
             behind every src, and no data: URI images (the 1.09 MB lesson)
  links      every internal href lands on a page that exists here
  words      no em or en dash anywhere in the file, comments included
  private    no private hostnames or local paths in anything served
  classes    every class in the markup has a rule in the page's stylesheets
             (web-ship-check Law #2: an unstyled class passes every other
             gate and still renders at browser defaults)

Site-wide: sitemap.xml lists exactly the indexable pages, and robots.txt
points at it.

    python3 tests/check_site.py

Exit 1 on any failure, and on a vacuous pass (no pages found).
"""
import html
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://megan-warren.com"
SKIP_DIRS = {".git", ".github", "worker", "tools", "tests", "node_modules",
             "_site", ".claude", ".wrangler"}
TITLE_MIN, TITLE_MAX = 15, 65
DESC_MIN, DESC_MAX = 70, 160
DASHES = ("—", "–")
# Never in a served file. prospects.* is a private, login-gated tool: the site
# describes it and must never point at it.
PRIVATE = ("prospects.megan-warren.com", "/Users/", "~/Projects",
           "~/Documents", "scratchpad", "lane job")
# Classes set only by script, or that exist for a machine rather than a rule.
# KaTeX tags every math atom with its TeX class (mord, mbin, mrel, ...) for
# spacing logic at render time; katex.css styles only some of them, and the
# rest render correctly with no rule. They appear only inside .katex markup.
CLASS_ALLOW = {"mbin", "mclose", "minner", "mop", "mopen", "mord", "mpunct",
               "mrel", "mtight", "text"}


def pages():
    out = []
    for d, dirs, files in os.walk(HERE):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f == "index.html" or (f == "404.html" and d == HERE):
                out.append(os.path.join(d, f))
    return sorted(out)


def url_path(path):
    rel = os.path.relpath(path, HERE).replace(os.sep, "/")
    if rel == "404.html":
        return "/404"
    return "/" + rel[: -len("index.html")]


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def meta(doc, attr, name):
    m = re.search(r'<meta %s="%s" content="([^"]*)"' % (attr, re.escape(name)), doc)
    return html.unescape(m.group(1)) if m else None


def css_classes(paths):
    names = set()
    for p in paths:
        css = open(p, encoding="utf-8").read()
        css = re.sub(r"/\*[\s\S]*?\*/", " ", css)
        # Selectors only: drop declaration bodies, keep what precedes each {.
        for sel in re.findall(r"([^{}]+)\{", css):
            names |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", sel))
    return names


def stylesheets(doc):
    out = []
    for href in re.findall(r'<link rel="stylesheet" href="([^"?]+)', doc):
        if href.startswith("/"):
            out.append(os.path.join(HERE, href.lstrip("/")))
    return out


def internal_target(href):
    href = href.split("#")[0].split("?")[0]
    if not href or not href.startswith("/") or href.startswith("//"):
        return None
    p = os.path.join(HERE, href.lstrip("/"))
    if href.endswith("/"):
        p = os.path.join(p, "index.html")
    return p


def check(path, fails):
    doc = open(path, encoding="utf-8").read()
    up = url_path(path)
    is404 = up == "/404"

    def fail(what):
        fails.append("%s: %s" % (up, what))

    if not re.search(r'<html lang="en"', doc):
        fail("no <html lang=\"en\">")
    t = re.search(r"<title>([^<]*)</title>", doc)
    if not t:
        fail("no title")
    elif not TITLE_MIN <= len(html.unescape(t.group(1))) <= TITLE_MAX:
        fail("title is %d chars" % len(html.unescape(t.group(1))))
    d = meta(doc, "name", "description")
    if not d or not DESC_MIN <= len(d) <= DESC_MAX:
        fail("description missing or %s chars" % (len(d) if d else 0))
    noindex = bool(re.search(r'<meta name="robots" content="[^"]*noindex', doc))
    if is404 != noindex:
        fail("noindex is %s on this page" % ("present" if noindex else "missing"))

    if not is404:
        c = re.search(r'<link rel="canonical" href="([^"]+)"', doc)
        if not c or c.group(1) != SITE + up:
            fail("canonical should be %s%s, is %s" % (SITE, up, c and c.group(1)))
        for prop in ("og:title", "og:description", "og:url", "og:type",
                     "og:image", "og:image:alt", "og:image:width",
                     "og:image:height"):
            if not meta(doc, "property", prop):
                fail("no %s" % prop)
        if meta(doc, "property", "og:url") != SITE + up:
            fail("og:url does not match the canonical")
        for name in ("twitter:card", "twitter:title", "twitter:description",
                     "twitter:image", "twitter:image:alt"):
            if not meta(doc, "name", name):
                fail("no %s" % name)
        if meta(doc, "name", "twitter:card") != "summary_large_image":
            fail("twitter:card is not summary_large_image")
        og = meta(doc, "property", "og:image") or ""
        if not og.startswith(SITE + "/"):
            fail("og:image is not an absolute URL on this site: %r" % og)
        else:
            f = os.path.join(HERE, og[len(SITE) + 1:].split("?")[0])
            if not os.path.exists(f):
                fail("og:image file is missing: %s" % og)
            elif png_size(f) != (1200, 630):
                fail("og:image is %s, not 1200x630" % (png_size(f),))
        if meta(doc, "name", "twitter:image") != og:
            fail("twitter:image differs from og:image")

        types = set()
        for b in re.findall(r'<script type="application/ld\+json">([\s\S]*?)</script>', doc):
            try:
                data = json.loads(b)
            except ValueError as e:
                fail("JSON-LD does not parse: %s" % e)
                continue
            for node in data.get("@graph") or [data]:
                tt = node.get("@type")
                types.update(tt if isinstance(tt, list) else [tt])
        need = {"Person", "ProfessionalService" if up == "/" else "Service"}
        if not need <= types:
            fail("JSON-LD needs %s, has %s" % (sorted(need), sorted(t for t in types if t)))

    markup = re.sub(r"<!--[\s\S]*?-->", " ", doc)
    markup = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", markup)
    levels = [int(h) for h in re.findall(r"<h([1-6])[\s>]", markup)]
    if levels.count(1) != 1:
        fail("%d H1s" % levels.count(1))
    for a, b in zip(levels, levels[1:]):
        if b > a + 1:
            fail("heading jumps from h%d to h%d" % (a, b))
            break

    for tag in re.findall(r"<img\b[^>]*>", markup):
        src = re.search(r'\ssrc="([^"]*)"', tag)
        label = src.group(1)[:60] if src else tag[:60]
        for attr in ("alt", "width", "height", "loading"):
            if not re.search(r"\s%s=\"" % attr, tag):
                fail("img %s has no %s" % (label, attr))
        if src and src.group(1).startswith("data:"):
            fail("img uses a data: URI; move it to img/")
        elif src:
            p = internal_target(src.group(1))
            if p and not os.path.exists(p):
                fail("img file is missing: %s" % src.group(1))
    if re.search(r"""url\(\s*['"]?data:image""", doc):
        fail("a data: URI image in inline CSS")

    for href in re.findall(r'\shref="([^"]+)"', markup):
        p = internal_target(href)
        if p and not os.path.exists(p):
            fail("internal link goes nowhere: %s" % href)

    if any(x in doc for x in DASHES):
        fail("an em or en dash in the file")
    for x in PRIVATE:
        if x in doc:
            fail("private string in a served file: %r" % x)

    sheets = stylesheets(doc)
    defined = css_classes(sheets)
    inline = re.findall(r"<style>([\s\S]*?)</style>", doc)
    for block in inline:
        for sel in re.findall(r"([^{}]+)\{", re.sub(r"/\*[\s\S]*?\*/", " ", block)):
            defined |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", sel))
    used = set()
    for cls in re.findall(r'\sclass="([^"]*)"', markup):
        used |= set(cls.split())
    dead = sorted(used - defined - CLASS_ALLOW)
    if dead:
        fail("classes with no CSS rule: %s" % ", ".join(dead))

    return None if (is404 or noindex) else up


def main():
    found = pages()
    if not found:
        print("  FAIL  no pages found; the gate is pointed at the wrong place")
        return 1
    fails, indexable = [], []
    for p in found:
        up = check(p, fails)
        if up:
            indexable.append(up)

    sm = open(os.path.join(HERE, "sitemap.xml"), encoding="utf-8").read()
    listed = sorted(u[len(SITE):] for u in re.findall(r"<loc>([^<]+)</loc>", sm))
    if listed != sorted(indexable):
        fails.append("sitemap.xml lists %s; the indexable pages are %s"
                     % (listed, sorted(indexable)))
    robots = open(os.path.join(HERE, "robots.txt"), encoding="utf-8").read()
    if "Sitemap: %s/sitemap.xml" % SITE not in robots:
        fails.append("robots.txt does not point at the sitemap")
    # Every book, game, Lesson Studio and the teacher hub link
    # https://megan-warren.com/privacy and depend on this 301 to the books
    # hub's privacy page (coordinator 27, 2026-10-29). Moving it moves the
    # whole fleet's links, so it is a gate, not a habit.
    redirects = open(os.path.join(HERE, "_redirects"), encoding="utf-8").read()
    for src in ("/privacy", "/privacy/"):
        rule = "%s https://books.megan-warren.com/privacy/ 301" % src
        if not any(line.split() == rule.split() for line in redirects.splitlines()):
            fails.append("_redirects lost the fleet's privacy rule: %s" % rule)
    for f in ("sitemap.xml", "robots.txt", "llms.txt", "_redirects", "_headers"):
        body = open(os.path.join(HERE, f), encoding="utf-8").read()
        if any(x in body for x in DASHES):
            fails.append("%s contains an em or en dash" % f)
        for x in PRIVATE:
            if x in body:
                fails.append("%s contains a private string %r" % (f, x))

    for f in fails:
        print("  FAIL  " + f)
    print("  %s  site structure: %d pages, %d indexable, %d failure(s)"
          % ("PASS" if not fails else "FAIL", len(found), len(indexable), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
