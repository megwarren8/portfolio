# megan-warren.com

Live at **[megan-warren.com](https://megan-warren.com)**: the portfolio of Megan Warren (Educator and Creative), who does instructional design and technical writing from Boston, working remotely.

## Pages

- `/` home: who she works with, what she makes, the numbers, four featured pieces, how a project runs, FAQ, and how to hire her (the full galleries live on the service pages)
- `/manuals/` training manuals, onboarding guides, how-to guides, and study guides
- `/custom-tools/` Ask the Turtle's free tools, Prospect Finder (described, private), classroom tools, and the Rehearsal app in development
- `/canvas/` Canvas unit hub and prep page samples (the only page that loads `canvas.css` and the KaTeX fonts)
- `404.html` the not-found page

Plain static HTML and one stylesheet, `shared.css`. No build step. The one script, `theme.js`, runs the light/dark switch in the header (the site follows the device until a visitor picks, and remembers the pick in that browser).

## Deploy

A push to `main` deploys to Cloudflare Pages through `.github/workflows/deploy.yml`, after these gates pass:

```
python3 tests/check_site.py
python3 tests/check_cache_busting.py
python3 tests/check_wording.py
python3 tests/check_deploy_excludes.py
```

After a deploy, `python3 tests/seo_check.py` checks the live site.

When `shared.css`, `canvas.css` or `theme.js` changes, update its `?v=` stamp on every page (the 404 inlines a copy of `shared.css`, so paste the new sheet into it too).

© 2026 Megan Warren. All rights reserved.
