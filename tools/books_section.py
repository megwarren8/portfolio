#!/usr/bin/env python3
"""Render the derived blocks of /books/ out of books/books.json.

/books/ is a hand-authored page and stays one, because its argument and its
voice are Megan's. But three blocks on it are pure data, and hand-typed data
rots: the page shipped "alongside a companion history web book" while listing
three of them, and it printed seven books with no counts a reader could check.

So those three blocks derive:

  the shelf   the seven covers under the hero
  the proof   the counted things: books, sections, widgets, labelled math
  the rows    one card per book, cover and spec line and links

Everything between a BEGIN and END marker pair is owned by this script. The
rest of the file is hand-written and never touched.

  python3 tools/books_section.py           rewrite the three blocks in place
  python3 tools/books_section.py --check   change nothing; exit 1 on drift

Cover URLs carry ?v=<first 8 of the source art's sha256>, read from
books/covers/provenance.json. /books/covers/* ships immutable for a year and
a Pages deploy does not purge the zone cache, so a new cover has to be a new
URL or readers keep the old one. That is not hypothetical: it is what
books.megan-warren.com did with the history covers in August 2026.
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(HERE, "books", "index.html")
DATA = os.path.join(HERE, "books", "books.json")
PROV = os.path.join(HERE, "books", "covers", "provenance.json")


def e(s):
    return html.escape(str(s), quote=True)


def stamp(prov, bid, w):
    v = prov[bid]["srcSha256"][:8]
    return f"/books/covers/{bid}-{w}.webp?v={v}"


def shelf(d, prov):
    lis = "\n".join(
        f'            <li><img src="{e(stamp(prov, b["id"], 320))}" '
        f'width="320" height="512" alt="" aria-hidden="true" loading="eager" '
        f'decoding="async"></li>'
        for b in d["books"])
    return ('          <ul class="shelf">\n' + lis + "\n          </ul>")


def proof(d):
    t = d["totals"]
    # Only counted things belong here. Each number is re-derived by the gate
    # from this file, and this file was derived from the books themselves.
    tiles = [
        (f'{t["books"]}', "books, all free"),
        (f'{t["sections"]}', "sections written"),
        (f'{t["widgets"]}', "interactive widgets"),
        (f'{t["labelledMath"]:,}', "math expressions, every one labeled"),
    ]
    body = "\n".join(
        f"            <div><b>{e(n)}</b><span>{e(label)}</span></div>"
        for n, label in tiles)
    return '          <div class="proof">\n' + body + "\n          </div>"


def rows(d, prov):
    out = []
    for g in d["groups"]:
        out.append(f'          <h3 class="eyebrow bookgroup">{e(g["name"])}</h3>')
        for bid in g["books"]:
            b = next(x for x in d["books"] if x["id"] == bid)
            # Countable things only, and the ones a commissioner is buying:
            # for a course book the hint ladders and worked solutions ARE the
            # answer-key claim this page makes, quantified.
            spec = [b["kicker"]]
            if b["kind"] == "course":
                spec += [f'{b["sections"]} sections',
                         f'{b["widgets"]} interactive widgets', b["hints"], b["solutions"]]
            else:
                # A history's own unit is the chapter, not the section, and
                # printing both ("22 sections, 8 chapters") reads as a
                # contradiction even though each is true.
                spec += [b["chapters"], b["events"]]
            spec.append("free on Apple Books" if b["apple"] else "web edition only")
            specline = " &middot; ".join(e(x) for x in spec if x)

            # Two DIFFERENTLY NAMED inline tokens, day and night, and the
            # stylesheet picks between them into a third name. An inline
            # custom property beats every stylesheet rule, so a theme rule can
            # never override the name it is set under: that is what shipped a
            # 1.02:1 hover on the books hub in August 2026.
            style = (f'--bk-accent-day:{e(b["accent"]["day"])};'
                     f'--bk-accent-night:{e(b["accent"]["night"])}')
            apple = (f'<a href="{e(b["apple"])}" target="_blank" rel="noopener" '
                     f'aria-label="{e(b["title"])} on Apple Books, opens in a new tab">'
                     f'Apple Books edition</a>') if b["apple"] else ""
            # readUrl, NOT web. The four course books run 12.9 to 18.9 MB and
            # her page has always opened their short /about contents page
            # first, which the section's own prose promises. Linking the bare
            # root instead makes that sentence false and hands a reader a
            # whole textbook with no warning.
            links = (f'<a href="{e(b["readUrl"])}" target="_blank" rel="noopener">'
                     f'{e(b["readLabel"])}</a>')
            if apple:
                links += "\n              " + apple
            out.append(f"""          <article class="bookrow" style="{style}">
            <p class="bookrow-cover"><img
               src="{e(stamp(prov, bid, 320))}"
               srcset="{e(stamp(prov, bid, 320))} 320w, {e(stamp(prov, bid, 640))} 640w"
               sizes="(max-width:640px) 112px, 132px" width="320" height="512"
               loading="lazy" decoding="async"
               alt="Cover of {e(b['title'])}: {e(b['subtitle'])}, by Megan Warren."></p>
            <div>
              <h3><a href="{e(b["readUrl"])}" target="_blank" rel="noopener">{e(b["title"])}</a></h3>
              <p class="tool-spec mono">{specline}</p>
              <p>{e(b["blurb"])}</p>
              <p class="bookrow-links">{links}</p>
            </div>
          </article>""")
    return "\n".join(out)


def faq_from_page(page):
    """Read the FAQ the READER sees, and return it as FAQPage JSON-LD.

    The hand-written FAQPage block declared six questions; the visible FAQ
    asked seven different ones, and not one of them matched. Google's own
    policy is that FAQ markup must be the content on the page, so that block
    was at best ignored. Deriving it from the section means they cannot
    diverge again, in either direction.
    """
    sec = page[page.index('<section class="how" id="faq"'):
               page.index('<section class="cta" id="contact"')]
    items = re.findall(r'<div class="k">([\s\S]*?)</div>\s*<div class="v">([\s\S]*?)</div>', sec)
    out = []
    for q, a in items:
        strip = lambda t: html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t))).strip()
        out.append((strip(q), strip(a)))
    return out


def jsonld(d, prov):
    """The seven books as schema.org Book nodes, plus the ItemList that orders
    them. The page already published Service, FAQPage and BreadcrumbList and
    named seven books in prose while declaring none of them as entities, so a
    crawler could read the offer and not the portfolio. Generated here so the
    structured data and the visible cards can never disagree."""
    origin = "https://megan-warren.com"
    nodes = []
    for b in d["books"]:
        work = ""
        if b["apple"]:
            work = (',\n      "workExample": {"@type": "Book", "bookFormat": '
                    '"https://schema.org/EBook", "isAccessibleForFree": true, '
                    f'"url": {json.dumps(b["apple"])}}}')
        nodes.append(f"""    {{
      "@type": "Book",
      "@id": "{b['web']}/#book",
      "name": {json.dumps(b['title'])},
      "alternateName": {json.dumps(b['title'] + ': ' + b['subtitle'])},
      "url": "{b['web']}/",
      "image": "{origin}{stamp(prov, b['id'], 640)}",
      "author": {{"@id": "{origin}/#person"}},
      "publisher": {{"@id": "{origin}/#person"}},
      "inLanguage": "en-US",
      "bookFormat": "https://schema.org/EBook",
      "isAccessibleForFree": true,
      "numberOfPages": {b['sections']},
      "learningResourceType": "textbook",
      "description": {json.dumps(b['blurb'])},
      "offers": {{"@type": "Offer", "price": "0", "priceCurrency": "USD",
                 "availability": "https://schema.org/InStock",
                 "url": "{b['web']}/"}}{work}
    }}""")
    items = ",\n".join(
        f'        {{"@type": "ListItem", "position": {i + 1}, '
        f'"url": "{b["web"]}/", "name": {json.dumps(b["title"])}}}'
        for i, b in enumerate(d["books"]))
    lst = f"""    {{
      "@type": "ItemList",
      "@id": "{origin}/books/#booklist",
      "name": "Interactive books built and published by Megan Warren",
      "numberOfItems": {len(d['books'])},
      "itemListElement": [
{items}
      ]
    }}"""
    faq = faq_from_page(open(PAGE, encoding="utf-8").read())
    qs = ",\n".join(
        '        {"@type": "Question", "name": %s,\n'
        '         "acceptedAnswer": {"@type": "Answer", "text": %s}}'
        % (json.dumps(q), json.dumps(a)) for q, a in faq)
    faq_node = ('    {\n      "@type": "FAQPage",\n'
                '      "@id": "https://megan-warren.com/books/#faq",\n'
                '      "mainEntity": [\n' + qs + "\n      ]\n    }")
    body = ",\n".join(nodes + [lst, faq_node])
    return ('    <script type="application/ld+json">\n'
            '{\n  "@context": "https://schema.org",\n  "@graph": [\n'
            + body + "\n  ]\n}\n    </script>")


BLOCKS = {"shelf": shelf, "proof": proof, "rows": rows, "jsonld": jsonld}


def render(name, d, prov):
    fn = BLOCKS[name]
    return fn(d, prov) if fn.__code__.co_argcount == 2 else fn(d)


def main():
    check = "--check" in sys.argv
    d = json.load(open(DATA, encoding="utf-8"))
    prov = json.load(open(PROV, encoding="utf-8"))
    page = open(PAGE, encoding="utf-8").read()

    drift, done = [], []
    for name in BLOCKS:
        begin, end = f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"
        m = re.search(re.escape(begin) + r"[\s\S]*?" + re.escape(end), page)
        if not m:
            print(f"  MISSING MARKERS: {begin} ... {end} not found in books/index.html")
            return 1
        body = render(name, d, prov)
        new = f"{begin}\n{body}\n          {end}"
        if m.group(0) == new:
            continue
        drift.append(name)
        page = page[:m.start()] + new + page[m.end():]
        done.append(name)

    # The FAQ block derives from the page's own FAQ section, so a hand-edited
    # question silently changes what --check should expect. Re-render after
    # reading the CURRENT page, which is what the loop above already does, and
    # then say plainly whether schema and visible text still agree.
    faq_pairs = faq_from_page(open(PAGE, encoding="utf-8").read())
    schema_qs = re.findall(r'"@type": "Question", "name": "((?:[^"\\]|\\.)*)"', page)
    visible_qs = [q for q, _ in faq_pairs]
    if [json.loads('"%s"' % q) for q in schema_qs] != visible_qs:
        print("  FAQ SCHEMA DRIFT: the FAQPage questions are not the questions on "
              "the page. Google credits FAQ markup only when it matches visible "
              "content. Run python3 tools/books_section.py")
        return 1

    # THE PROMISE THE PROSE MAKES. The #live section tells a reader that the
    # four course-book links "open a short contents page first, so you can see
    # what is inside before downloading the whole book". Those books are 12.9
    # to 18.9 MB. On 2026-08-30 a rebuild repointed them at their bare roots
    # and the sentence silently became false, which is how a reader gets handed
    # a whole textbook with no warning. Pin the promise to the links.
    promise = "open a short contents page first"
    if promise in page:
        wrong = [b["id"] for b in d["books"]
                 if b["kind"] == "course" and not b["readUrl"].rstrip("/").endswith("/about")]
        if wrong:
            print(f"  CONTENTS-PAGE PROMISE BROKEN: the page still says the four course "
                  f"links {promise!r}, but {', '.join(wrong)} point at the book itself. "
                  f"Either repoint readUrl at /about or rewrite that sentence.")
            return 1

    if check:
        if drift:
            print(f"  BOOKS SECTION STALE: {', '.join(drift)} in books/index.html no longer "
                  f"matches books/books.json. Run python3 tools/books_section.py")
            return 1
        print(f"  BOOKS SECTION OK: all {len(BLOCKS)} derived blocks match books.json")
        return 0

    if done:
        open(PAGE, "w", encoding="utf-8").write(page)
        print(f"  rewrote {', '.join(done)} in books/index.html")
    else:
        print("  nothing to do; every derived block already matches books.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
