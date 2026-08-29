#!/usr/bin/env python3
"""Regenerate /books/'s cover art FROM the book that owns it.

The commissions page sells book design, so it has to SHOW the books. Each
book's master art is its EPUB cover PNG, 1580x2528, living in that book's own
repo on this machine. This resizes to the two widths the page asks for and
records, per book, the source path, the source's sha256 and the output byte
sizes, so covers/provenance.json can never quietly describe art that is no
longer there.

The recorded sha256 is ALSO the cache-busting stamp printed into the page's
URLs, so new art is a new URL. That is not decoration: /books/covers/* ships
immutable for a year and a Cloudflare Pages deploy does not purge the zone,
which is exactly how books.megan-warren.com served pre-axis history covers for
two days in August 2026.

  python3 tools/covers.py            regenerate any cover whose source moved
  python3 tools/covers.py --all      regenerate all of them
  python3 tools/covers.py --check    change nothing; exit 1 if any is stale

Needs cwebp and sips, both already on this machine.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVERS = os.path.join(HERE, "books", "covers")
PROV = os.path.join(COVERS, "provenance.json")
WIDTHS = {320: 512, 640: 1024}          # the master is 1580x2528, ratio 0.625
QUALITY = 82

# id -> the repo that owns the master. Absolute, because these are her book
# repos and they are not vendored here.
SOURCES = {
    "trigonometry": "trig_textbook",
    "derivatives": "deriv_textbook",
    "integrals": "integrals_textbook",
    "discrete-math-and-linear-algebra": "probmat_textbook",
    "history-of-trigonometry": "trig_history_textbook",
    "history-of-calculus": "history_textbook",
    "history-of-discrete-math": "hdmla_history_textbook",
}
DOCS = os.path.expanduser("~/Documents")


def src_path(repo):
    return os.path.join(DOCS, repo, "tools", "epub", "assets", "cover.png")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def render(src, out, w, h):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        tmp = t.name
    try:
        subprocess.run(["sips", "-z", str(h), str(w), src, "--out", tmp],
                       check=True, capture_output=True)
        subprocess.run(["cwebp", "-q", str(QUALITY), "-quiet", tmp, "-o", out],
                       check=True, capture_output=True)
    finally:
        os.unlink(tmp)


def main():
    force = "--all" in sys.argv
    check = "--check" in sys.argv
    prov = json.load(open(PROV, encoding="utf-8")) if os.path.exists(PROV) else {}
    stale, done, absent = [], [], []

    for book, repo in SOURCES.items():
        src = src_path(repo)
        rec = prov.setdefault(book, {})
        if not os.path.exists(src):
            # CI has no book repos, and that is not a defect: the webp files
            # are committed artifacts. NOT CHECKED must never read as a pass.
            absent.append(book)
            continue
        now = sha256(src)
        moved = now != rec.get("srcSha256")
        missing = any(not os.path.exists(os.path.join(COVERS, f"{book}-{w}.webp"))
                      for w in WIDTHS)
        if not (moved or missing or force):
            continue
        if check:
            stale.append(f"{book}: source art has changed since these webp files "
                         f"were made (recorded {rec.get('srcSha256', '')[:12]}, "
                         f"on disk {now[:12]})" if moved
                         else f"{book}: a webp file is missing")
            continue
        for w, h in WIDTHS.items():
            out = os.path.join(COVERS, f"{book}-{w}.webp")
            render(src, out, w, h)
            rec[str(w)] = os.path.getsize(out)
        dims = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src],
                              capture_output=True, text=True).stdout.split()
        rec["srcSize"] = f"{dims[dims.index('pixelWidth:') + 1]}x{dims[dims.index('pixelHeight:') + 1]}"
        rec["source"] = src
        rec["srcSha256"] = now
        done.append(book)

    if check:
        for s in stale:
            print("  " + s)
        n = len(SOURCES) - len(absent)
        if stale:
            print("COVERS STALE")
        elif absent:
            print(f"COVERS NOT CHECKED: {len(absent)} of {len(SOURCES)} sources are not "
                  f"on this machine ({', '.join(sorted(absent))}); {n} checked and matching")
        else:
            print(f"COVERS OK: all {n} match the art they came from")
        return 1 if stale else 0

    if done:
        json.dump(prov, open(PROV, "w", encoding="utf-8"), indent=2)
        open(PROV, "a", encoding="utf-8").write("\n")
    for b in done:
        print(f"  regenerated {b}: {prov[b]['320']:,} and {prov[b]['640']:,} bytes")
    for b in absent:
        print(f"  not checked, source not on this machine: {b}")
    if not done:
        print("  nothing to do; every cover matches its source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
