# Contact form API: the one-time setup

The portfolio's two contact forms, the commission form on the homepage
("Have something you wish already existed?") and the discovery-call form at
/coaching/, both post to one small Cloudflare Worker in this folder, which
emails the message to you (formatted differently depending on which form it
came from). Everything is built and tested. Three things need a click from
you before it can actually send mail, because Cloudflare requires a human to
approve them, no API can do this part.

## Why this exists

The site is static (Cloudflare Pages), so there's no server to receive a
form post. This Worker is that server: a few lines of code that validate
the submission and hand it to Cloudflare's own email-sending service, so
your inbox never appears anywhere in the site's code that a visitor (or a
spam scraper) can see.

## Step 1: widen the API token (2 minutes)

The existing deploy token (`megan-warren-com-deploys`) is deliberately
scoped to just what the Pages sites need. Deploying a Worker and sending
mail both need one more permission group each.

1. [dash.cloudflare.com](https://dash.cloudflare.com) &rarr; profile icon &rarr;
   **My Profile** &rarr; **API Tokens**.
2. Find `megan-warren-com-deploys` &rarr; **Edit**.
3. Under Permissions, add:
   - `Account` / `Workers Scripts` / `Edit`
   - Whatever permission group covers **Email** for your account (the
     dashboard's own wording may say "Email Routing Addresses" and "Email
     Routing Rules", or it may show up under a newer "Email Service" name;
     add every Email-related Edit permission you see, there's no harm in
     the token being able to do all of them)
4. **Continue to summary** &rarr; **Save**.

Nothing else changes: it's the same token value, so the keychain entry and
the `CLOUDFLARE_API_TOKEN` secret already on this repo keep working.

## Step 2: turn on Email Service for megan-warren.com (5 minutes)

1. In the Cloudflare dashboard, pick the megan-warren.com zone.
2. Go to **Compute** &rarr; **Email Service**.
3. Find **Email Sending** (this is what lets the Worker send mail *from*
   `contact@megan-warren.com`) &rarr; **Onboard Domain** &rarr; pick
   megan-warren.com. It adds a few DNS records (SPF/DKIM) automatically.
4. Find **Email Routing** &rarr; **Onboard Domain** if it isn't already on
   for this zone (it adds an MX record automatically; there's no existing
   mail on this domain, so this is safe).
5. Under **Destination Addresses**, add `meganraewarren@gmail.com`.
6. **Check your Gmail inbox** for an email from Cloudflare and click
   **Verify email address**. This is the one step that has to be a human,
   by design, it's Cloudflare confirming you actually own that inbox
   before they'll relay mail to it.

## Step 3: tell me it's done

Once steps 1 and 2 are done, say so and I'll finish the last piece myself:
deploy the Worker, plug its real address into the form (right now it has a
placeholder), and send a real test message through the live form to
confirm it lands in your inbox before calling it done.

If you'd rather do it yourself: push to `main` (the deploy workflow in
`.github/workflows/deploy-worker.yml` runs automatically), then check the
Cloudflare dashboard under **Workers & Pages** &rarr; `megan-warren-contact`
for its `*.workers.dev` address, and paste that into the `ENDPOINT` constant
in `index.html`'s contact-form script (search for `TODO before this goes
live`).

## Routine updates after that

Same as everything else here: push to `main`. `deploy-worker.yml` only
re-deploys the Worker when `worker/` changes; the site itself still deploys
on every push via the existing `deploy.yml`.

## Troubleshooting

- **Form says "That didn't send."** The Worker reached Cloudflare's email
  service but the send itself failed, almost always because Step 2 isn't
  finished yet (destination not verified, or the sending domain isn't
  onboarded). Check both in the dashboard.
- **Form says "Could not reach the server."** The Worker either isn't
  deployed yet, or the `ENDPOINT` in `index.html` doesn't match its real
  address. Check the Actions tab on this repo for a failed
  `Deploy contact API to Cloudflare Workers` run.
- **Nothing happens when you click "Send message."** Open the browser
  console; the form validates client-side first, so this usually means a
  required field (name, a valid-looking email, or at least a short
  message) is empty.
