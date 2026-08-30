#!/usr/bin/env python3
"""UK spellings must not reach the page, unless somebody actually said them.

Megan's standing ruling is US spelling in shipping copy. It was gated for hello
paint after "centred" shipped live in seven Etsy descriptions while a gate that
held the single word "colour" reported clean: a rule that matches one instance
of a class is not a rule about the class.

This is that rule, ported to the books fleet, where three had survived every
other gate: "unlabelled", "The maths is typeset properly", and "colour
contrast", all on the front page of books.megan-warren.com.

TWO THINGS IT MUST NOT DO, and both are the reason it reads visible text
rather than raw source:

1. **aria-labelledby is not a spelling mistake.** It is a W3C attribute name,
   spelled that way by the specification, and "correcting" it silently breaks
   the accessible name of the section it points at. There are 8 of them on the
   hub's index alone. Every attribute is stripped before matching, so the
   checker never sees them. Same reasoning as the `cancelled` wire-value
   exemption in hello paint's rule: if a machine reads it, it is not copy.
   The word-boundary form protects these twice over, since "labelledby" and
   "labelledMath" have no boundary after "labelled".

2. **A direct quote is somebody's own words.** Megan's ruling, 2026-08-30:
   fix UK spellings "unless in a direct quote from someone where it should be
   kept". Changing a quotation misquotes a person, which is worse than a
   dialect slip. So anything inside <blockquote>, <q>, <cite>, or between
   typographic curly quotes is exempt. Straight ASCII quotes are NOT treated
   as quotation, because they are how HTML writes every attribute in the file
   and honouring them would exempt the whole document.

    python3 tests/check_wording.py [--root DIR]

Exit 1 on any violation, and exit 1 on a vacuous pass: if it finds no
prose at all to check, that is a broken checker, not a clean site.
"""
import argparse
import html
import os
import re
import sys

# The class, not one member of it. Word-bounded so an identifier fragment or a
# hex value cannot trip it. Kept deliberately in step with hello paint's
# tools/retired_wording.json; add here when you add there.
UK = re.compile(
    r"\b(colour\w*|centred|centres?|catalogues?|labell(?:ed|ing)|unlabell(?:ed|ing)"
    r"|behaviour\w*|artefacts?|favourite\w*|organis(?:e|ed|ing|ation)\w*"
    r"|realis(?:e|ed|ing)\w*|recognis(?:e|ed|ing)\w*|analys(?:e|ed|ing)\w*"
    r"|apologis(?:e|ed|ing)\w*|defence|offence|licences?|practis(?:e|ed|ing)"
    r"|travelling|modelling|jewellery|neighbour\w*|honour\w*|flavour\w*|humour"
    r"|metres?|litres?|maths|whilst|amongst)\b", re.I)

US = {"colour": "color", "centred": "centered", "centre": "center",
      "catalogue": "catalog", "labelled": "labeled", "unlabelled": "unlabeled",
      "behaviour": "behavior", "artefact": "artifact", "favourite": "favorite",
      "organise": "organize", "realise": "realize", "recognise": "recognize",
      "analyse": "analyze", "apologise": "apologize", "defence": "defense",
      "offence": "offense", "licence": "license", "practise": "practice",
      "travelling": "traveling", "modelling": "modeling", "jewellery": "jewelry",
      "neighbour": "neighbor", "honour": "honor", "flavour": "flavor",
      "humour": "humor", "metre": "meter", "litre": "liter", "maths": "math",
      "whilst": "while", "amongst": "among"}

# Quotation carried by MARKUP. Blanked while the tags are still present.
QUOTED_HTML = [
    re.compile(r"<blockquote[\s\S]*?</blockquote>", re.I),
    re.compile(r"<q[ >][\s\S]*?</q>", re.I),
    re.compile(r"<cite[\s\S]*?</cite>", re.I),
]
# Quotation carried by PUNCTUATION. These run only AFTER every tag is stripped,
# which is what makes the straight " safe: at that point no attribute survives,
# so a " can only be a quotation mark. Running it against raw HTML would exempt
# the whole document, since every attribute is quoted.
#
# This matters far beyond politeness. In the history books the flagged words
# are overwhelmingly cited paper TITLES ("A note on the new evidence for
# Hipparchus' star catalogue") and translated primary sources ("There is a pond
# 1 zhang square. A reed grows at its centre..."). Americanising either one
# falsifies a citation, which is a worse defect than the dialect slip.
QUOTED_TEXT = [
    re.compile("“[^”]{0,3000}”"),
    re.compile("‘[^’]{0,3000}’"),
    # Bounded so one stray quote cannot swallow a page.
    re.compile(r'"[^"]{0,3000}"'),
]


def allowed_phrases(root):
    """Proper nouns and cited titles that keep their spelling.

    The same escape hatch hello paint's retired_wording.json gives each rule,
    and for the same reason its `grey` rule needed one: a manufacturer's color
    name is a proper noun printed on the actual object, and Americanising it
    makes it wrong rather than consistent.

    In the history books this is the difference between a gate and a
    liability: "Wellcome Library Catalogue", "Munich Digitisation Centre" and
    "Maths Vidya Institute" are the real names of real institutions, and
    "New evidence for Hipparchus' Star Catalogue revealed by multispectral
    imaging" is an APA reference to a real paper. Rewriting any of them
    falsifies a citation.

    One phrase per line in wording-allow.txt, with a reason in a # comment.
    Matched case-insensitively with flexible whitespace, so a line wrap in the
    source cannot decide whether a proper noun survives.
    """
    path = os.path.join(root, "wording-allow.txt")
    if not os.path.exists(path):
        return []
    out = []
    for raw in open(path, encoding="utf-8"):
        line = raw.split("#")[0].strip()
        if line:
            out.append(line)
    return out


def blank(text, rx):
    """Replace a match with spaces, keeping length so offsets still line up."""
    return rx.sub(lambda m: re.sub(r"\S", " ", m.group(0)), text)


def visible(raw, is_html):
    """What a reader actually sees, minus anything somebody is being quoted on."""
    t = raw
    if is_html:
        t = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", t, flags=re.I)
        for rx in QUOTED_HTML:
            t = blank(t, rx)
        # Strip every tag, which takes every ATTRIBUTE with it: aria-labelledby,
        # class names, data-*. Only what a reader sees survives. This must
        # happen BEFORE the punctuation pass below.
        t = re.sub(r"<[^>]+>", " ", t)
        t = html.unescape(t)
    for rx in QUOTED_TEXT:
        t = blank(t, rx)
    return t


def suggest(word):
    low = word.lower()
    for uk, us in US.items():
        if low.startswith(uk):
            return us + low[len(uk):]
    return "the US spelling"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    allow = allowed_phrases(root)
    bad, files, chars = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in
                       (".git", "node_modules", "__pycache__", "fonts", "covers", "apple")]
        for name in sorted(filenames):
            if not name.endswith((".html", ".txt")):
                continue
            full = os.path.join(dirpath, name)
            raw = open(full, encoding="utf-8", errors="replace").read()
            text = visible(raw, name.endswith(".html"))
            for phrase in allow:
                pat = r"\s+".join(re.escape(w) for w in phrase.split())
                text = re.sub(pat, lambda m: " " * len(m.group(0)), text, flags=re.I)
            files += 1
            chars += len(text.strip())
            for m in UK.finditer(text):
                a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
                ctx = re.sub(r"\s+", " ", text[a:b]).strip()
                bad.append((os.path.relpath(full, root), m.group(0),
                            suggest(m.group(0)), ctx))

    if files == 0 or chars == 0:
        print("  FAIL  US spelling: found no prose to check. The checker is "
              "broken or pointed at the wrong root.")
        return 1

    if bad:
        seen = set()
        print(f"  FAIL  US spelling: {len(bad)} UK spelling(s) in shipping copy")
        for f, found, fix, ctx in bad:
            if (f, found, ctx) in seen:
                continue
            seen.add((f, found, ctx))
            print(f'          {f}: "{found}" should be "{fix}"')
            print(f"              ...{ctx}...")
        print("          A direct quote is exempt: put it in <blockquote>, <q>, "
              "<cite>, or curly quotes, and it keeps the speaker's own words.")
        return 1

    print(f"  PASS  US spelling in every shipping word  ({files} files, "
          f"{chars:,} characters of visible prose, {len(US)} spellings checked; "
          f"attributes and direct quotes exempt"
          + (f", {len(allow)} declared proper noun(s)" if allow else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
