#!/usr/bin/env python3
"""
seo_check.py - the SEO regression gate for megan-warren.com.

A sibling of the asktheturtle.com gate, with the same three design rules and
one addition that platform made impossible over there.

Every check runs against the LIVE public site. Nothing is read from a local
file, a cache, or a previous run, because the failures this exists to catch
(a title rewritten without its keywords, a page shipped without a meta
description, a JSON-LD block truncated mid-object) are all invisible in the
source and only show up in what the server actually serves.

Design rules, each one earned:

  * The page list comes from the live sitemap.xml. It is never hard-coded.
    A hard-coded list silently stops covering pages the moment someone adds
    one, and then reports green over the gap.

  * The gate fails loudly if it cannot run. A fetch error is a FAILURE, not a
    skip. Zero pages checked is a FAILURE. A gate that cannot reach the site
    must never print a passing summary.

  * Every skipped or unreachable page is named in the output. Silent
    truncation reads as "covered everything" when it did not.

The addition: this site is on Cloudflare Pages, which serves arbitrary files
from the repo root, so /llms.txt is a real file here and IS checked. The
turtle gate had to record it as an unfixable platform limit instead.

The fleet check (--fleet, on by default) exists because the eight public
subdomains are the only substantial off-site-shaped asset this site has, and
on 2026-08-13 three of them linked back with no anchor text at all while four
had no canonical. Those are silent regressions: everything still renders.

Usage:
    python3 tests/seo_check.py                 # everything, including fleet
    python3 tests/seo_check.py --no-fleet      # main site only, faster
    python3 tests/seo_check.py --only / /books/
    python3 tests/seo_check.py --quiet         # summary + failures only

Exit codes:  0 all checks passed
             1 one or more checks failed
             2 the gate itself could not run
"""

import argparse
import html
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from collections import OrderedDict

# The live site is the default and the only target that proves anything about
# search. --site exists so the same gate can run against a local preview
# BEFORE a deploy, which is the only way to avoid shipping a red gate. It does
# not replace the live run: fleet checks are skipped automatically when the
# target is not the live host, because localhost has no subdomains.
SITE = "https://megan-warren.com"
LIVE = SITE

# Pages that are live and indexable but absent from sitemap.xml. Empty today.
# Kept, and printed in the coverage line every run, because the turtle gate
# reported green three times over three pages the sitemap never listed.
ALSO_CHECK = []

# The eight public subdomains, checked for the things that silently rot:
# reachability, a canonical, a meta description, and a link home that carries
# real anchor text rather than a bare URL.
FLEET = [
    "https://probability.megan-warren.com",
    "https://derivatives.megan-warren.com",
    "https://integrals.megan-warren.com",
    "https://grouper.megan-warren.com",
    "https://wildcard.megan-warren.com",
    "https://color.megan-warren.com",
    "https://hellopaint.megan-warren.com",
]

# The three textbooks cannot carry a rel="canonical" and that is not neglect.
# Their build.js ends with an offline-rule gate that fails the build on ANY
# external resource reference, and a <link href="https://..."> trips it.
# Probed 2026-08-13: adding the canonical turned all three builds red with
# "FAIL: external resource reference detected."
#
# Weakening someone else's correctness gate to satisfy this one would be the
# wrong trade, and each book lives at exactly one URL with no query-string
# variants, so a canonical would earn close to nothing. Recorded as a known
# constraint instead of a standing red mark.
CANONICAL_EXEMPT = {
    "probability.megan-warren.com",
    "derivatives.megan-warren.com",
    "integrals.megan-warren.com",
}

# Anchor text that is technically a link and does no ranking work at all.
# "privacy" and "terms" are in here because a footer legal link genuinely does
# point at megan-warren.com, so counting it as a real backlink let all three
# textbooks pass while their only descriptive link home read "megan-warren.com".
DEAD_ANCHORS = {"megan-warren.com", "https://megan-warren.com",
                "megan-warren.com/", "here", "link", "site", "portfolio",
                "privacy", "privacy policy", "terms", "home", "back"}

UA = {"User-Agent": "megan-warren-seo-gate/1.0", "Cache-Control": "no-cache"}
CTX = ssl.create_default_context()
TIMEOUT = 40
RETRIES = 3

# The books are 12 to 16 MB single files, so the fleet check reads a prefix for
# the head (title, canonical, description) and, separately, a suffix by HTTP
# Range for the footer.
#
# Reading only the prefix was the first version and it was wrong: it reported
# "no link home with any anchor text" for all three textbooks, when the truth
# was that they link home with dead anchor text 12 MB further down. A gate that
# names the wrong defect is worse than one that stays quiet, so both ends of
# the document get read.
FLEET_BYTES = 300_000

# Google truncates around here. Under 15 means the title is almost certainly
# a placeholder rather than a real one.
TITLE_MIN, TITLE_MAX = 15, 65
DESC_MIN, DESC_MAX = 70, 205

# Every money page must name its own offer. This is the check that would have
# caught the state the site was in on 2026-08-13: a homepage title reading
# "Megan Warren, Educator and Creative", which spent its whole budget on a
# name four other people rank for and carried none of the words a buyer types.
MONEY_WORDS = {
    "/": ("commission", "software"),
    "/software/": ("custom software", "commission"),
    "/books/": ("textbook", "commission"),
    "/coaching/": ("ai coaching",),
    "/about/": ("commission", "boston"),
}
# Title keyword requirement, separate from body: the title is the ad.
TITLE_WORDS = {
    "/": ("commission",),
    "/software/": ("software",),
    "/books/": ("textbook",),
    "/coaching/": ("ai coaching",),
    "/about/": ("megan warren",),
}
# Pages that sell something and must say so in machine-readable form. Kept
# separate from MONEY_WORDS because /about/ carries the money words in prose
# but is a ProfilePage, not an offer, and requiring a Service node on it would
# be schema written for the gate rather than for the reader.
SERVICE_REQUIRED = {"/", "/software/", "/books/", "/coaching/"}

# Pages that have their own Open Graph card under their own directory, built by
# tools/make_og.py. /coaching/ already had one; /privacy/ deliberately shares
# the site-wide card, because a legal page needs no artwork of its own.
OWN_CARD = {"/software/", "/books/", "/about/", "/coaching/"}

GEO_WORDS = ("boston", "massachusetts", "new england")

# The privacy policy has no business talking about Boston, and padding it with
# geography would serve the gate rather than the reader.
GEO_EXEMPT = {"/privacy/"}
LEGAL_PAGES = {"/privacy/"}
THIN_OK = {"/privacy/"}
THIN_DEFAULT = 250

DASHES = ("—", "–")  # em, en. House rule: never, anywhere.

# Every profile that proves this Megan Warren is this Megan Warren. Four other
# people of the same name rank ahead of this site: an interior designer in the
# Bay Area, a changemaker coach in Geneva who publishes about AI, a wellness
# coach, and several unrelated LinkedIn profiles. sameAs is the machine-readable
# claim that ties the name to this site, so losing an entry here is a silent
# regression on the site's single biggest constraint, not a cosmetic one.
REQUIRED_SAMEAS = (
    "github.com/megwarren8",
    "linkedin.com/in/megan-warren-23a87835",
)


class Result:
    def __init__(self, url):
        self.url = url
        self.failures = []
        self.notes = []

    def fail(self, check, detail):
        self.failures.append((check, detail))

    def note(self, msg):
        self.notes.append(msg)

    @property
    def ok(self):
        return not self.failures


def fetch(url, max_bytes=None):
    """Return page text. Raises on failure: the caller must treat that as a
    test failure, never as a skip."""
    last = None
    for _ in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, context=CTX, timeout=TIMEOUT) as r:
                raw = r.read(max_bytes) if max_bytes else r.read()
                return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - any failure is a failure
            last = e
    raise RuntimeError("could not fetch %s after %d tries: %s"
                       % (url, RETRIES, last))


def fetch_tail(url, nbytes):
    """Last nbytes of a document, via a Range request. Falls back to the whole
    body if the server ignores Range, which is correct but slower."""
    last = None
    for _ in range(RETRIES):
        try:
            headers = dict(UA)
            headers["Range"] = "bytes=-%d" % nbytes
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=CTX, timeout=TIMEOUT) as r:
                raw = r.read()
                partial = r.getcode() == 206
                return raw.decode("utf-8", "replace"), partial
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError("could not fetch the tail of %s after %d tries: %s"
                       % (url, RETRIES, last))


def discover_pages():
    """Page list from the live sitemap. Never hard-coded."""
    xml = fetch(SITE + "/sitemap.xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    paths = []
    for loc in locs:
        p = loc.split(".com", 1)[-1] or "/"
        p = p.split("?")[0]
        if not p.startswith("/"):
            p = "/" + p
        if p not in paths:
            paths.append(p)
    if not paths:
        raise RuntimeError("sitemap.xml parsed to zero URLs; gate cannot run")
    from_sitemap = len(paths)
    added = [p for p in ALSO_CHECK if p not in paths]
    paths.extend(added)
    return paths, from_sitemap, added


def first(pattern, text, group=1):
    m = re.search(pattern, text, re.S)
    return html.unescape(m.group(group)).strip() if m else None


def check_page(path, doc):
    r = Result(path)

    # ---- title -------------------------------------------------------------
    title = first(r"<title>([^<]*)</title>", doc)
    if not title:
        r.fail("title", "missing entirely")
    else:
        n = len(title)
        if n < TITLE_MIN:
            r.fail("title", "only %d chars: %r" % (n, title))
        elif n > TITLE_MAX:
            r.fail("title", "%d chars, will truncate in results: %r" % (n, title))
        if any(d in title for d in DASHES):
            r.fail("title-dash", "contains an em or en dash: %r" % title)
        low = title.lower()
        want = TITLE_WORDS.get(path)
        if want and path not in LEGAL_PAGES:
            missing = [w for w in want if w not in low]
            if missing:
                r.fail("title-keywords",
                       "title is missing %s: %r" % (", ".join(missing), title))

    # ---- meta description --------------------------------------------------
    desc = first(r'<meta name="description" content="([^"]*)"', doc)
    if not desc:
        r.fail("meta-description", "missing entirely")
    else:
        n = len(desc)
        if n < DESC_MIN:
            r.fail("meta-description", "only %d chars, too thin" % n)
        elif n > DESC_MAX:
            r.fail("meta-description", "%d chars, will truncate" % n)
        if any(d in desc for d in DASHES):
            r.fail("meta-dash", "contains an em or en dash")

    # ---- exactly one H1 ----------------------------------------------------
    markup = re.sub(r"<script[\s\S]*?</script>", " ", doc)
    h1s = re.findall(r"<h1[^>]*>([\s\S]*?)</h1>", markup)
    if len(h1s) == 0:
        r.fail("h1", "no H1 on the page")
    elif len(h1s) > 1:
        r.fail("h1", "%d H1s; there should be exactly one" % len(h1s))

    # ---- canonical ---------------------------------------------------------
    if not re.search(r'<link[^>]+rel="canonical"', doc):
        r.fail("canonical", "no canonical link")

    # ---- the link preview --------------------------------------------------
    # A card that 404s renders as a blank grey box in every chat app, and one
    # that belongs to a different page shows the wrong words to someone who has
    # not clicked yet. /software/, /books/ and /about/ each shipped pointing at
    # the site-wide card, whose artwork says "Educator and Creative".
    og = first(r'<meta property="og:image" content="([^"]*)"', doc)
    if not og:
        r.fail("og-image", "no og:image")
    else:
        target = og.replace(LIVE, SITE) if SITE != LIVE else og
        try:
            fetch(target, max_bytes=64)
        except Exception:  # noqa: BLE001
            r.fail("og-image", "og:image does not load: %s" % og)
        if path in OWN_CARD and og.rstrip("/").endswith("/og-image.png") \
                and path.strip("/") not in og:
            r.fail("og-image", "uses the site-wide card, not its own: %s" % og)
    if not first(r'<meta property="og:image:alt" content="([^"]*)"', doc):
        r.fail("og-image-alt", "no og:image:alt")

    # ---- structured data ---------------------------------------------------
    blocks = re.findall(
        r'<script type="application/ld\+json">([\s\S]*?)</script>', doc)
    types = set()
    same_as = []
    if not blocks:
        if path not in LEGAL_PAGES:
            r.fail("json-ld", "no structured data at all")
    for b in blocks:
        try:
            data = json.loads(b)
        except Exception as e:  # noqa: BLE001
            r.fail("json-ld", "a block does not parse: %s" % e)
            continue
        for node in (data.get("@graph") or [data]):
            t = node.get("@type")
            if isinstance(t, list):
                types.update(t)
            elif t:
                types.add(t)
            if t == "Person":
                sa = node.get("sameAs") or []
                same_as.extend([sa] if isinstance(sa, str) else sa)
    if blocks:
        if "Person" not in types:
            r.fail("schema-org", "no Person node; found %s"
                   % (", ".join(sorted(types)) or "nothing"))
        # A page that sells something should say so in machine-readable form.
        if path in SERVICE_REQUIRED and "Service" not in types:
            r.fail("schema-org", "money page with no Service node; found %s"
                   % ", ".join(sorted(types)))
        if "Person" in types:
            joined = " ".join(same_as)
            missing = [p for p in REQUIRED_SAMEAS if p not in joined]
            if missing:
                r.fail("sameas",
                       "Person.sameAs is missing %s; with four other Megan "
                       "Warrens ranking ahead, this is the entity claim"
                       % ", ".join(missing))
            else:
                r.note("sameAs: %d profiles" % len(same_as))
        r.note("schema: " + (", ".join(sorted(types)) or "none"))

    # ---- body content ------------------------------------------------------
    i = doc.find("<main")
    j = doc.find("<footer", i) if i >= 0 else -1
    body = doc[i:j] if i >= 0 and j > i else doc
    body = re.sub(r"<script[\s\S]*?</script>", " ", body)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    words = len(text.split())
    if words < THIN_DEFAULT and path not in THIN_OK:
        r.fail("thin-content", "only %d words in <main>, floor is %d"
               % (words, THIN_DEFAULT))

    low = text.lower()

    # ---- the words a buyer actually types ----------------------------------
    want = MONEY_WORDS.get(path)
    if want:
        missing = [w for w in want if w not in low]
        if missing:
            r.fail("money-words", "body never says: %s" % ", ".join(missing))

    if path not in GEO_EXEMPT and not any(w in low for w in GEO_WORDS):
        r.fail("geo", "body never says Boston, Massachusetts or New England")

    # ---- the house dash rule, on the whole rendered page --------------------
    if any(d in text for d in DASHES):
        r.fail("body-dash", "body text contains an em or en dash")

    r.note("%d words" % words)
    return r


# Nav links allowed to stay visible under 860px. Everything else in the nav
# must be named in shared.css's mobile hide rule.
MOBILE_NAV_KEEP = {"/software/", "/books/", "/coaching/"}


def check_mobile_nav(pages_html):
    """The nav hides links on mobile by matching exact hrefs in a CSS rule.
    That list is a hard-coded work list, and hard-coded work lists exclude
    silently: adding /software/, /books/ and /about/ to the nav on 2026-08-13
    left all three visible under 860px, and the nav overflowed the header on
    every page at 375 and 480 px. Nothing errored and nothing looked broken in
    the markup.

    This cannot measure layout over HTTP, so it checks the invariant instead:
    every nav href is either hidden by the rule or explicitly allowed to stay.
    """
    r = Result("/(mobile nav rule)")
    try:
        css = fetch(SITE + "/shared.css")
    except Exception as e:  # noqa: BLE001
        r.fail("mobile-nav", "could not fetch shared.css: %s" % e)
        return r

    # A nav item can be hidden by its href OR by a class it carries, and the
    # rules live in more than one max-width block. Collecting only href
    # selectors was the first version of this check and it produced a false
    # failure on the "Message me" button, which is hidden as .btn--ghost.
    hidden_hrefs, hidden_classes = set(), set()
    for mq in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", css):
        start = mq.end() - 1
        depth, i = 0, start
        while i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = css[start:i + 1]
        for sel, body in re.findall(r"([^{}]*)\{([^{}]*)\}", block):
            if ".top-links" not in sel or "display:none" not in body.replace(" ", ""):
                continue
            hidden_hrefs |= set(re.findall(r'a\[href(?:\$)?="([^"]+)"\]', sel))
            hidden_classes |= set(re.findall(r"\.top-links\s+\.([A-Za-z0-9_-]+)", sel))

    if not hidden_hrefs and not hidden_classes:
        r.fail("mobile-nav", "no mobile hide rule found for .top-links")
        return r

    items = {}  # href -> set of classes seen on it
    for doc in pages_html.values():
        nav = re.search(r'<nav class="top-links">(.*?)</nav>', doc, re.S)
        if not nav:
            continue
        for tag in re.findall(r"<a[^>]*>", nav.group(1)):
            href = re.search(r'href="([^"]+)"', tag)
            if not href:
                continue
            cls = re.search(r'class="([^"]*)"', tag)
            items.setdefault(href.group(1), set()).update(
                cls.group(1).split() if cls else [])

    if not items:
        r.fail("mobile-nav", "no nav links found to check")
        return r

    stray = []
    for h, classes in sorted(items.items()):
        if h in MOBILE_NAV_KEEP:
            continue
        if h in hidden_hrefs or any(h.endswith(x) for x in hidden_hrefs):
            continue
        if classes & hidden_classes:
            continue
        stray.append(h)
    if stray:
        r.fail("mobile-nav",
               "nav links neither hidden on mobile nor in MOBILE_NAV_KEEP, "
               "so they will overflow the header: %s" % ", ".join(stray))
    r.note("%d nav hrefs, %d kept, %d hidden by href, %d by class"
           % (len(items), len(MOBILE_NAV_KEEP), len(hidden_hrefs), len(hidden_classes)))
    return r


def check_site():
    """Site-level files. Returns a list of Results."""
    out = []
    # llms.txt is checked here and NOT on the turtle site, because Cloudflare
    # Pages serves arbitrary root files and Squarespace strips the dot from a
    # slug. Same convention, different platform, different verdict.
    for path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
        r = Result(path)
        try:
            body = fetch(SITE + path)
            if len(body) < 10:
                r.fail("site-file", "served but effectively empty")
            if any(d in body for d in DASHES):
                r.fail("site-file-dash", "contains an em or en dash")
            r.note("%d bytes" % len(body))
        except Exception as e:  # noqa: BLE001
            r.fail("site-file", str(e))
        out.append(r)

    # A 404 that returns 200 makes every typo a soft-404 in the index.
    r = Result("/(404 handling)")
    try:
        req = urllib.request.Request(
            SITE + "/this-page-does-not-exist-seo-gate", headers=UA)
        code = 0
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=TIMEOUT) as h:
                code = h.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        if code != 404:
            r.fail("404", "a missing page returned HTTP %d, not 404" % code)
        r.note("HTTP %d" % code)
    except Exception as e:  # noqa: BLE001
        r.fail("404", str(e))
    out.append(r)
    return out


def check_fleet():
    """The public subdomains: reachable, canonical, described, and linking
    home with anchor text that does ranking work."""
    out = []
    for base in FLEET:
        host = base.split("//", 1)[-1]
        r = Result(host)
        try:
            doc = fetch(base + "/", max_bytes=FLEET_BYTES)
        except Exception as e:  # noqa: BLE001
            r.fail("fetch", str(e))
            out.append(r)
            continue

        if host in CANONICAL_EXEMPT:
            r.note("canonical exempt: offline build gate")
        elif not re.search(r'<link[^>]+rel="canonical"', doc):
            r.fail("canonical", "no canonical link")
        desc = first(r'<meta name="description" content="([^"]*)"', doc)
        if not desc:
            r.fail("meta-description", "missing entirely")

        # The footer sits at the end of the file, which on the textbooks is
        # 12 MB past the prefix above.
        try:
            tail, partial = fetch_tail(base + "/", FLEET_BYTES)
            if partial:
                r.note("tail read by Range")
        except Exception as e:  # noqa: BLE001
            r.fail("fetch-tail", str(e))
            out.append(r)
            continue
        scan = doc + tail

        anchors = re.findall(
            r'<a[^>]+href="[^"]*megan-warren\.com[^"]*"[^>]*>([\s\S]*?)</a>', scan)
        texts = [re.sub(r"<[^>]+>", "", a).strip() for a in anchors]
        texts = [t for t in texts if t]
        if not texts:
            r.fail("backlink", "no link home with any anchor text")
        else:
            useful = [t for t in texts
                      if t.lower().strip("/ ") not in DEAD_ANCHORS]
            if not useful:
                r.fail("backlink-anchor",
                       "links home only as bare text: %s"
                       % ", ".join(repr(t) for t in texts[:3]))
            else:
                r.note("anchor: %r" % useful[0][:40])
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None,
                    help="check just these paths")
    ap.add_argument("--no-fleet", action="store_true",
                    help="skip the subdomain checks")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--site", default=None,
                    help="target another origin (a local preview) instead of "
                         "the live site")
    args = ap.parse_args()

    global SITE
    if args.site:
        SITE = args.site.rstrip("/")
    if SITE != LIVE and not args.no_fleet:
        args.no_fleet = True

    print("SEO gate for %s" % SITE)
    if SITE != LIVE:
        print("NOT THE LIVE SITE. Canonical URLs and the fleet are not proven "
              "by this run.")
    print("=" * 78)

    from_sitemap, added = None, []
    try:
        if args.only:
            pages = args.only
        else:
            pages, from_sitemap, added = discover_pages()
    except Exception as e:  # noqa: BLE001
        print("GATE COULD NOT RUN: %s" % e)
        return 2

    if args.only:
        print("restricted by --only to: %s" % ", ".join(pages))
    else:
        print("coverage: %d from sitemap.xml + %d from ALSO_CHECK = %d targets"
              % (from_sitemap, len(added), len(pages)))
        if added:
            print("          not in the sitemap, checked anyway: %s"
                  % ", ".join(added))
        if args.no_fleet:
            print("          FLEET SKIPPED by --no-fleet: %d subdomains not "
                  "checked" % len(FLEET))
        else:
            print("          plus %d fleet subdomains" % len(FLEET))
    print()

    results = OrderedDict()
    unreachable = []
    docs = {}
    for p in pages:
        try:
            doc = fetch(SITE + p)
        except Exception as e:  # noqa: BLE001
            r = Result(p)
            r.fail("fetch", str(e))
            results[p] = r
            unreachable.append(p)
            continue
        docs[p] = doc
        results[p] = check_page(p, doc)

    for r in check_site():
        results[r.url] = r
    nav = check_mobile_nav(docs)
    results[nav.url] = nav
    if not args.only and not args.no_fleet:
        for r in check_fleet():
            results[r.url] = r
            if any(c == "fetch" for c, _ in r.failures):
                unreachable.append(r.url)

    checked = len(results)
    failed = [r for r in results.values() if not r.ok]

    if not args.quiet:
        for path, r in results.items():
            mark = "PASS" if r.ok else "FAIL"
            extra = ("  (%s)" % "; ".join(r.notes)) if r.notes else ""
            print("%-4s %-34s%s" % (mark, path, extra))
            for check, detail in r.failures:
                print("       %-18s %s" % (check, detail))
        print()

    print("=" * 78)
    if checked == 0:
        print("GATE COULD NOT RUN: zero pages checked")
        return 2
    if unreachable:
        print("UNREACHABLE (counted as failures): %s" % ", ".join(unreachable))
    print("checked %d targets, %d passed, %d failed"
          % (checked, checked - len(failed), len(failed)))
    if failed:
        print()
        print("failing checks by type:")
        tally = {}
        for r in failed:
            for check, _ in r.failures:
                tally[check] = tally.get(check, 0) + 1
        for check, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print("   %-20s %d" % (check, n))
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
