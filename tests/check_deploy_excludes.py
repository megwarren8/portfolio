#!/usr/bin/env python3
"""The build tooling must not be published.

Until 2026-08-29 the deploy rsynced everything, so megan-warren.com/tools/ and
/tests/ served her build scripts and gates to anyone who typed the URL. Nothing
secret was in them, but the books hub 404s its own tools and this site did not,
and a public site serving its own generators reads as an accident because it
was one.

The exclusion lives in one rsync line in .github/workflows/deploy.yml, which is
exactly the kind of line a later edit drops without anybody noticing. This
pins it.

    python3 tests/check_deploy_excludes.py

Note what this CANNOT do: once a path has been served, Cloudflare keeps its own
copy for the TTL, and removing the file does not purge it. After the 08-29
exclusion the bare URLs kept answering 200 from cache for days while a
cache-busted query 404'd. Deleting is a byte change under a stable URL, and no
reference-scanning gate can see a file nobody references.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(HERE, ".github", "workflows", "deploy.yml")
MUST_EXCLUDE = ["tools", "tests", "cache-exempt.txt"]


def main():
    if not os.path.exists(WORKFLOW):
        print("  FAIL  deploy excludes: .github/workflows/deploy.yml is missing")
        return 1
    body = open(WORKFLOW, encoding="utf-8").read()
    if "rsync" not in body:
        print("  FAIL  deploy excludes: no rsync in the workflow, so this gate "
              "no longer knows how the site is assembled. Re-point it.")
        return 1
    missing = [d for d in MUST_EXCLUDE
               if not re.search(r"--exclude\s+'?" + re.escape(d) + r"'?(\s|$)", body)]
    if missing:
        print(f"  FAIL  deploy excludes: {', '.join(missing)} would be published. "
              f"Add --exclude for each to the rsync in deploy.yml.")
        return 1
    print(f"  PASS  the build tooling stays off the public site  "
          f"({len(MUST_EXCLUDE)} path(s) excluded from the deploy rsync)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
