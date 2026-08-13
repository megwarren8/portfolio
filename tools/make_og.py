#!/usr/bin/env python3
"""
make_og.py - generate the Open Graph cards for the commission and about pages.

Why this exists: /software/, /books/ and /about/ shipped pointing at the
site-wide og-image.png, whose artwork has "Educator and Creative: software you
can just open." baked into it. That is right for the homepage and wrong for a
page about book commissions, and a link preview is the one place a visitor sees
the wrong words before they see the page.

Fonts are read straight out of shared.css rather than from the system, because
they are already embedded there as base64 and that guarantees the card uses the
same typeface the page does. No network, no font install, no drift.

Usage:
    python3 tools/make_og.py            # write all cards
    python3 tools/make_og.py --check    # verify they exist and are 1200x630
"""

import argparse
import base64
import io
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSS = os.path.join(ROOT, "shared.css")

W, H = 1200, 630
VOID = (14, 10, 24)          # #0E0A18, the Developer page floor
TEXT_HI = (242, 238, 250)    # #F2EEFA
TEXT_MID = (173, 162, 200)   # #ADA2C8
TEAL = (87, 230, 210)        # #57E6D2

# The signature gradient, teal at the crown to lavender at the feet.
GRADIENT = [
    (0.00, (107, 244, 224)),
    (0.16, (49, 217, 201)),
    (0.42, (58, 42, 140)),
    (0.64, (92, 61, 190)),
    (1.00, (183, 156, 242)),
]

CARDS = [
    {
        "out": "software/og-image.png",
        "eyebrow": "MEGAN WARREN  ·  CUSTOM SOFTWARE COMMISSIONS",
        "head": ["Commission a tool", "that does one thing well."],
        "sub": "Small, focused web tools for classrooms, nonprofits and small brands."
               "  Fixed price, $1,500 to $10,000.",
    },
    {
        "out": "books/og-image.png",
        "eyebrow": "MEGAN WARREN  ·  BOOK COMMISSIONS",
        "head": ["Commission a book that", "does more than a PDF can."],
        "sub": "Interactive textbooks, study guides and training manuals."
               "  One offline file, student and answer-key editions.",
    },
    {
        "out": "about/og-image.png",
        "eyebrow": "MEGAN WARREN  ·  ABOUT",
        "head": ["A teacher who got tired", "of waiting for the tools."],
        "sub": "Twelve years teaching math in Boston, now designing and building"
               " the software, books and brand systems.",
    },
]


def load_fonts():
    """Pull Schibsted Grotesk and Crimson Pro out of shared.css."""
    css = open(CSS, encoding="utf-8").read()
    found = {}
    for m in re.finditer(r"@font-face\s*\{(.*?)\}", css, re.S):
        blk = m.group(1)
        fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", blk)
        wt = re.search(r"font-weight:\s*(\d+)", blk)
        b64 = re.search(r"base64,([A-Za-z0-9+/=]+)", blk)
        if not (fam and wt and b64):
            continue
        key = (fam.group(1).strip(), int(wt.group(1)))
        found.setdefault(key, base64.b64decode(b64.group(1)))
    if not found:
        sys.exit("no @font-face payloads found in shared.css; cannot draw a card")
    return found


def font(found, family, weight, size):
    data = found.get((family, weight))
    if data is None:  # fall back to the nearest weight of the same family
        same = [k for k in found if k[0] == family]
        if not same:
            sys.exit("shared.css has no %s; cannot draw a card" % family)
        key = min(same, key=lambda k: abs(k[1] - weight))
        data = found[key]
    return ImageFont.truetype(io.BytesIO(data), size)


def gradient_at(t):
    """Sample the signature gradient at 0..1."""
    for i in range(len(GRADIENT) - 1):
        p0, c0 = GRADIENT[i]
        p1, c1 = GRADIENT[i + 1]
        if p0 <= t <= p1:
            f = 0 if p1 == p0 else (t - p0) / (p1 - p0)
            return tuple(round(c0[j] + (c1[j] - c0[j]) * f) for j in range(3))
    return GRADIENT[-1][1]


def draw_sigma(img, x, y, size):
    """The MW stacked sigma, stroked in the vertical gradient."""
    scale = size / 120.0
    pts = [(25, 20), (60, 47), (95, 20), (95, 97), (60, 70), (25, 97)]
    pts = [(x + px * scale, y + py * scale) for px, py in pts]
    stroke = max(2, round(13 * scale))
    # Stroke into a mask, then paint the gradient through it, so the gradient
    # follows the mark's height rather than the whole canvas.
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    md.line(pts + [pts[0]], fill=255, width=stroke, joint="curve")
    for px, py in pts:
        md.ellipse([px - stroke / 2, py - stroke / 2,
                    px + stroke / 2, py + stroke / 2], fill=255)
    grad = Image.new("RGB", img.size, VOID)
    gp = grad.load()
    top, bot = y, y + size
    for row in range(img.size[1]):
        t = 0.0 if bot == top else min(1.0, max(0.0, (row - top) / (bot - top)))
        c = gradient_at(t)
        for col in range(img.size[0]):
            gp[col, row] = c
    img.paste(grad, (0, 0), mask)


def make(card, found):
    img = Image.new("RGB", (W, H), VOID)
    d = ImageDraw.Draw(img)

    # A hairline of the gradient along the top edge, the one brand flourish.
    for col in range(W):
        d.line([(col, 0), (col, 5)], fill=gradient_at(col / (W - 1)))

    draw_sigma(img, 72, 66, 96)

    f_eyebrow = font(found, "Schibsted Grotesk", 600, 22)
    f_head = font(found, "Schibsted Grotesk", 700, 66)
    f_sub = font(found, "Crimson Pro", 400, 30)

    d.text((72, 210), card["eyebrow"], font=f_eyebrow, fill=TEAL)

    y = 258
    for line in card["head"]:
        d.text((72, y), line, font=f_head, fill=TEXT_HI)
        y += 78

    y += 14
    for line in wrap(card["sub"], f_sub, W - 144, d):
        d.text((72, y), line, font=f_sub, fill=TEXT_MID)
        y += 40

    d.text((72, H - 60), "megan-warren.com", font=f_eyebrow, fill=TEXT_MID)

    out = os.path.join(ROOT, card["out"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out, os.path.getsize(out)


def wrap(text, f, maxw, d):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= maxw:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        bad = 0
        for c in CARDS:
            p = os.path.join(ROOT, c["out"])
            if not os.path.exists(p):
                print("MISSING %s" % c["out"])
                bad += 1
                continue
            im = Image.open(p)
            ok = im.size == (W, H)
            print("%-4s %-26s %sx%s" % ("OK" if ok else "FAIL",
                                        c["out"], im.size[0], im.size[1]))
            bad += 0 if ok else 1
        return 1 if bad else 0

    found = load_fonts()
    for c in CARDS:
        out, n = make(c, found)
        print("wrote %-30s %6.1f KB" % (c["out"], n / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
