#!/usr/bin/env python3
"""Every asset served with a long cache must be referenced by a busting URL.

THE TRAP, which has now cost two sites:

  A `_headers` rule says /img/* or /covers/* is immutable for a year. The
  files under it keep their names when their bytes change. A deploy does NOT
  purge the Cloudflare zone cache, so the edge keeps serving the old bytes
  under the old name for the whole TTL, while origin, the repo, and every
  local gate are correct and green.

  hellopaintart 2026-08-07: the live slider served a two-day-old painting.
  Fixed there with a content-hash query, inside that repo's build.mjs.
  books.megan-warren.com 2026-08-29: the live hub served the pre-axis history
  covers for two days. Megan caught both, by eye, on the live site.

The second one happened because the first fix was a BUILD-SCRIPT HABIT and not
a GATE. A habit protects the code path it was written into and nothing else,
which is why hellopaintart stamped its kit photos correctly and left its own
og:image cards bare under the same immutable rule. This file is the law that
travels: drop it in tests/, point it at the built site, and any long-cached
reference without a buster fails.

    python3 tests/check_cache_busting.py             the repo root
    python3 tests/check_cache_busting.py --root _site  a build directory

A reference passes if its URL carries a query string (?v=<hash>) or its
filename already contains a content hash (name.a1b2c3d4.ext). Anything else
must be listed in cache-exempt.txt beside the _headers file, one glob per
line with a reason, so an exemption is a decision somebody wrote down rather
than a file nobody noticed. Fonts are the usual honest exemption: the bytes
behind schibsted-grotesk-400.woff2 do not change.

Exit 1 on any offender, and also on a vacuous pass: if _headers declares a
long cache and this script finds ZERO references to check, that is a broken
checker, not a clean site.
"""
import argparse
import os
import re
import sys

# A day. Below this a stale asset ages out before it can matter; at or above
# it, a wrong file is a wrong file for a long time.
LONG_SECONDS = 86400

HASHED_NAME = re.compile(r"[.-][0-9a-f]{8,}\.[a-z0-9]+$", re.I)
ATTR = re.compile(
    r'(?:src|href|content)\s*=\s*"([^"]+)"'
    r'|(?:src|href|content)\s*=\s*\'([^\']+)\''
    r'|url\(\s*["\']?([^"\')]+)["\']?\s*\)',
    re.I)
# srcset is a comma separated list of "url descriptor" pairs and holds the
# BIGGEST renditions, so leaving it out let the widest image on the page go
# stale while the gate stayed green. A mutation caught this on 2026-08-29.
SRCSET = re.compile(r'srcset\s*=\s*"([^"]+)"', re.I)
# JSON-LD carries og and schema image URLs that crawlers fetch. Same rule.
LDJSON = re.compile(r'<script[^>]+application/ld\+json[^>]*>([\s\S]*?)</script>', re.I)
LDURL = re.compile(r'"((?:https?://[^"\s]+|/[^"\s]+))"')


def long_cache_globs(headers_path):
    """Path patterns in a _headers file whose Cache-Control is long."""
    globs, current = [], None
    for raw in open(headers_path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = line.strip()
            continue
        if current is None:
            continue
        m = re.search(r"cache-control\s*:\s*(.+)", line, re.I)
        if not m:
            continue
        value = m.group(1).lower()
        age = re.search(r"max-age\s*=\s*(\d+)", value)
        if "immutable" in value or (age and int(age.group(1)) >= LONG_SECONDS):
            globs.append(current)
    return globs


def matches(glob, path):
    """The subset of Pages glob syntax that appears in these files."""
    if glob.startswith("/*."):                 # /*.png
        return path.endswith(glob[2:]) and path.count("/") == 1
    if glob.endswith("/*"):                    # /covers/*
        return path.startswith(glob[:-1])
    if glob == "/*":                           # every response; not an asset rule
        return False
    return path == glob


def exemptions(root, path=None):
    path = path or os.path.join(root, "cache-exempt.txt")
    if not os.path.exists(path):
        return []
    out = []
    for raw in open(path, encoding="utf-8"):
        line = raw.split("#")[0].strip()
        if line:
            out.append(line)
    return out


def busted(url):
    """Would a byte change under this URL reach a reader who has the old one?"""
    clean = url.split("#")[0]
    if "?" in clean and clean.split("?", 1)[1].strip():
        return True
    return bool(HASHED_NAME.search(clean))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    ap.add_argument("--quiet", action="store_true")
    # A generated site has its _headers inside the build directory while the
    # exemptions, being a human decision, belong in the repo next to the code.
    ap.add_argument("--exempt", default=None,
                    help="path to cache-exempt.txt (default: <root>/cache-exempt.txt)")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    headers = os.path.join(root, "_headers")
    if not os.path.exists(headers):
        print("  SKIP  cache busting: no _headers file, nothing declares a long cache")
        return 0

    globs = long_cache_globs(headers)
    if not globs:
        print("  PASS  cache busting: _headers declares no long-lived cache")
        return 0

    exempt = exemptions(root, args.exempt)
    pages, checked, bad = 0, 0, []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "node_modules", "__pycache__")]
        for name in filenames:
            if not name.endswith((".html", ".css")):
                continue
            full = os.path.join(dirpath, name)
            body = open(full, encoding="utf-8", errors="replace").read()
            pages += 1
            found = [next(g for g in m.groups() if g is not None)
                     for m in ATTR.finditer(body)]
            for m in SRCSET.finditer(body):
                for entry in m.group(1).split(","):
                    part = entry.strip().split()
                    if part:
                        found.append(part[0])
            for m in LDJSON.finditer(body):
                found.extend(LDURL.findall(m.group(1)))
            for url in found:
                # Same-origin only: another host's caching is not ours to fix.
                if url.startswith(("data:", "mailto:", "#", "//")):
                    continue
                path = url
                for origin in ("https://", "http://"):
                    if path.startswith(origin):
                        rest = path.split("//", 1)[1]
                        path = "/" + rest.split("/", 1)[1] if "/" in rest else "/"
                if not path.startswith("/"):
                    continue
                bare = path.split("?")[0].split("#")[0]
                if not any(matches(g, bare) for g in globs):
                    continue
                if any(matches(g, bare) for g in exempt):
                    continue
                checked += 1
                if not busted(path):
                    rel = os.path.relpath(full, root)
                    bad.append(f"{bare}  referenced bare in {rel}")

    if checked == 0:
        # A checker that inspects nothing must never look like a clean site.
        print(f"  FAIL  cache busting: {len(globs)} long-cache rule(s) in _headers "
              f"({', '.join(globs)}) and ZERO matching references found across "
              f"{pages} files. The checker is broken or pointed at the wrong root.")
        return 1

    if bad:
        print(f"  FAIL  cache busting: {len(set(bad))} long-cached asset(s) "
              f"referenced without a version stamp")
        for b in sorted(set(bad)):
            print(f"          {b}")
        print("          A deploy does not purge the edge cache. Stamp the URL "
              "(?v=<content hash>) or declare it in cache-exempt.txt.")
        return 1

    if not args.quiet:
        print(f"  PASS  every long-cached asset is busted  ({checked} references "
              f"across {pages} files, {len(globs)} cache rule(s)"
              f"{f', {len(exempt)} declared exemption(s)' if exempt else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
