#!/usr/bin/env python3
"""
extract_fonts.py - lift the base64 fonts out of shared.css into real files.

Measured 2026-08-14, before this ran:

    shared.css               251 KB raw  ->  180 KB gzipped, RENDER BLOCKING
      embedded base64 fonts  228 KB      ->  90.9% of the file
      actual CSS rules        23 KB      ->   9.1%

A browser paints nothing until a render-blocking stylesheet has fully arrived,
so every first-time visitor waited for all eight font weights before seeing a
single word. Two things made that worse than it looks:

  * base64 inflates binary about a third, and woff2 is ALREADY compressed, so
    gzip barely recovers anything. The whole file only squeezed 251 -> 180 KB,
    where the CSS alone gzips to about 6 KB.
  * `font-display: swap` was already set on all eight faces and could not do
    anything, because a font embedded in the stylesheet arrives WITH the
    stylesheet. There is no earlier moment for it to swap from.

After this runs the blocking payload is about 6 KB and the fonts load in
parallel, non-blocking, with swap finally meaning something.

The script is idempotent: run it again after any change to shared.css and it
extracts whatever is still inline, or reports that there is nothing to do.

    python3 tools/extract_fonts.py            # extract
    python3 tools/extract_fonts.py --check    # exit 1 if any font is inline

Every write is byte-verified: the file on disk is decoded back and compared to
the bytes that came out of the stylesheet before the CSS is rewritten.
"""

import base64
import hashlib
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
CSS = HERE / "shared.css"
FONTDIR = HERE / "fonts"

# Only these render above the fold on every page: the sans carries the nav,
# the h1 and the body; the serif carries the standfirst paragraph directly
# under every h1. Preloading more than the hero needs would recreate the
# problem this script exists to solve.
PRELOAD = ["schibsted-grotesk-400", "schibsted-grotesk-700", "crimson-pro-400"]

FACE_RE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
# Consume any trailing format() too. The first version of this script did
# not, and emitted "format('woff2') format('woff2')" because the source
# already carried one. That is invalid, so EVERY @font-face was dropped and
# the whole site silently fell back to system fonts. It looked almost right:
# the page rendered, the files downloaded, and only a width comparison
# against a fallback face gave it away.
DATA_RE = re.compile(
    r"url\(\s*[\"']?data:font/woff2;base64,([A-Za-z0-9+/=]+)[\"']?\s*\)"
    r"(\s*format\(\s*[\"']?[^)\"']+[\"']?\s*\))?")


def slug(family, weight, style):
    base = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    return "%s-%s%s" % (base, weight, "-italic" if style == "italic" else "")


def faces(css):
    """Every @font-face still carrying an inline font, with its identity."""
    out = []
    for m in FACE_RE.finditer(css):
        block = m.group(1)
        d = DATA_RE.search(block)
        if not d:
            continue
        fam = re.search(r"font-family:\s*[\"']?([^;\"']+)", block)
        w = re.search(r"font-weight:\s*(\d{3})", block)
        st = re.search(r"font-style:\s*(\w+)", block)
        out.append({
            "family": fam.group(1).strip() if fam else "unknown",
            "weight": w.group(1) if w else "400",
            "style": st.group(1) if st else "normal",
            "b64": d.group(1),
            "url_text": d.group(0),
        })
    return out


def main():
    if not CSS.exists():
        print("FAIL: no shared.css at %s" % CSS, file=sys.stderr)
        return 2
    css = CSS.read_text(encoding="utf-8")
    found = faces(css)
    check = "--check" in sys.argv

    if not found:
        print("No inline fonts in shared.css. Nothing to extract.")
        missing = [p for p in PRELOAD if not (FONTDIR / (p + ".woff2")).exists()]
        if missing:
            print("WARNING: preload list names files that do not exist: %s"
                  % ", ".join(missing))
            return 1
        return 0

    if check:
        print("FAIL: %d font(s) still embedded in shared.css; run "
              "python3 tools/extract_fonts.py" % len(found))
        return 1

    FONTDIR.mkdir(exist_ok=True)
    before = len(css.encode())
    written = []
    for f in found:
        raw = base64.b64decode(f["b64"])
        name = slug(f["family"], f["weight"], f["style"]) + ".woff2"
        path = FONTDIR / name
        path.write_bytes(raw)

        # Byte-verify before touching the stylesheet. A truncated font is a
        # silent failure: the page still renders, in a fallback face.
        back = path.read_bytes()
        if back != raw or hashlib.sha256(back).hexdigest() != hashlib.sha256(raw).hexdigest():
            print("FAIL: %s did not round-trip" % name, file=sys.stderr)
            return 2
        if not back.startswith(b"wOF2"):
            print("FAIL: %s is not a woff2 file (bad magic)" % name, file=sys.stderr)
            return 2

        css = css.replace(f["url_text"], "url('/fonts/%s') format('woff2')" % name, 1)
        written.append((name, len(raw)))
        print("  %-34s %7d bytes" % (name, len(raw)))

    left = faces(css)
    if left:
        print("FAIL: %d font(s) still inline after the rewrite" % len(left), file=sys.stderr)
        return 2

    # Validate every rewritten src BEFORE writing, because a malformed one is
    # invisible: the CSS still parses as a file, the page still renders, and
    # the browser just drops that @font-face and uses a system font. Only a
    # width comparison against a fallback catches it after the fact.
    for block in FACE_RE.findall(css):
        src = re.search(r"src:\s*([^;}]+)", block)
        if not src:
            print("FAIL: an @font-face has no src after the rewrite", file=sys.stderr)
            return 2
        text = src.group(1)
        if len(re.findall(r"format\(", text)) != 1:
            print("FAIL: malformed src, expected exactly one format(): %r"
                  % text.strip(), file=sys.stderr)
            return 2
        if not re.fullmatch(r"url\('/fonts/[a-z0-9.-]+\.woff2'\)\s*format\('woff2'\)",
                            text.strip()):
            print("FAIL: src does not match the expected shape: %r"
                  % text.strip(), file=sys.stderr)
            return 2

    import gzip
    gz_before = len(gzip.compress(CSS.read_bytes(), 9))
    CSS.write_text(css, encoding="utf-8")
    after = len(css.encode())
    gz_after = len(gzip.compress(css.encode(), 9))
    print()
    print("shared.css raw     : %7d -> %7d bytes  (%.0f KB -> %.0f KB)"
          % (before, after, before / 1024, after / 1024))
    print("render-blocking gz : %7d -> %7d bytes  (%.0f KB -> %.1f KB, %.1f%% smaller)"
          % (gz_before, gz_after, gz_before / 1024, gz_after / 1024,
             100 * (1 - gz_after / gz_before)))
    print("%d font files written to %s/" % (len(written), FONTDIR.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
