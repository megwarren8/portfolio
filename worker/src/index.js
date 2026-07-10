// Contact form API for megan-warren.com.
// Receives a POST from either of the portfolio's two forms (the homepage
// commission form, or /coaching/'s discovery-call form), validates it, and
// emails it to Megan via Cloudflare Email Service (send_email binding).
// Nothing here is reachable from the browser except through fetch(), so
// the destination address below is never exposed on either site page.

const DESTINATION = "meganraewarren@gmail.com";
const FROM = "Megan Warren Portfolio <contact@megan-warren.com>";

const ALLOWED_ORIGINS = [
  "https://megan-warren.com",
  "https://www.megan-warren.com",
];
const LOCAL_ORIGIN = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;

const FORMATS = {
  boston: "In person, downtown Boston",
  remote: "Remote, over Zoom",
  unsure: "Not sure yet",
};

const MIN_FILL_MS = 2500; // faster than this and it's almost certainly a bot
const MAX_TEXT = 5000;
const MAX_NAME = 200;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function corsHeaders(origin) {
  const allowed = origin && (ALLOWED_ORIGINS.includes(origin) || LOCAL_ORIGIN.test(origin));
  const headers = {
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    Vary: "Origin",
  };
  if (allowed) headers["Access-Control-Allow-Origin"] = origin;
  return headers;
}

function json(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function str(v) {
  return typeof v === "string" ? v.trim() : "";
}

// Builds the {subject, text, html} for a commission-inquiry submission.
function commissionEmail(name, email, message) {
  const subject = `Portfolio contact: ${name} (Commission inquiry)`;
  const text =
    `New commission inquiry from megan-warren.com\n\n` +
    `From: ${name} <${email}>\n\n` +
    `${message}\n`;
  const html =
    `<p><strong>New commission inquiry from megan-warren.com</strong></p>` +
    `<p>From: ${escapeHtml(name)} &lt;${escapeHtml(email)}&gt;</p>` +
    `<p>${escapeHtml(message).replace(/\n/g, "<br>")}</p>`;
  return { subject, text, html };
}

// Builds the {subject, text, html} for an AI-coaching submission.
function coachingEmail(name, email, goal, tried, format) {
  const formatLabel = FORMATS[format] || FORMATS.unsure;
  const triedLine = tried ? tried : "(not answered)";
  const subject = `Portfolio contact: ${name} (AI coaching inquiry)`;
  const text =
    `New AI coaching inquiry from megan-warren.com/coaching/\n\n` +
    `From: ${name} <${email}>\n` +
    `Format: ${formatLabel}\n\n` +
    `Wants to be able to do:\n${goal}\n\n` +
    `Already tried:\n${triedLine}\n`;
  const html =
    `<p><strong>New AI coaching inquiry from megan-warren.com/coaching/</strong></p>` +
    `<p>From: ${escapeHtml(name)} &lt;${escapeHtml(email)}&gt;<br>` +
    `Format: ${escapeHtml(formatLabel)}</p>` +
    `<p><strong>Wants to be able to do:</strong><br>${escapeHtml(goal).replace(/\n/g, "<br>")}</p>` +
    `<p><strong>Already tried:</strong><br>${escapeHtml(triedLine).replace(/\n/g, "<br>")}</p>`;
  return { subject, text, html };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== "POST") {
      return json({ ok: false, error: "Method not allowed." }, 405, origin);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Could not read that submission." }, 400, origin);
    }

    // Honeypot: a real visitor never fills this in. A bot that fills every
    // field will. Pretend success either way so bots don't learn to adapt.
    if (str(body.company) !== "") {
      return json({ ok: true }, 200, origin);
    }
    const startedAt = Number(body.startedAt);
    if (Number.isFinite(startedAt) && Date.now() - startedAt < MIN_FILL_MS) {
      return json({ ok: true }, 200, origin);
    }

    const kind = body.kind === "coaching" ? "coaching" : "commission";
    const name = str(body.name);
    const email = str(body.email);

    if (!name || name.length > MAX_NAME) {
      return json({ ok: false, error: "Enter your name." }, 400, origin);
    }
    if (!email || email.length > 320 || !EMAIL_RE.test(email)) {
      return json({ ok: false, error: "Enter a valid email address." }, 400, origin);
    }

    let mail;
    if (kind === "commission") {
      const message = str(body.message);
      if (!message || message.length < 10) {
        return json({ ok: false, error: "Say a little more about what you need." }, 400, origin);
      }
      if (message.length > MAX_TEXT) {
        return json({ ok: false, error: `Keep it under ${MAX_TEXT} characters.` }, 400, origin);
      }
      mail = commissionEmail(name, email, message);
    } else {
      const goal = str(body.goal);
      const tried = str(body.tried).slice(0, MAX_TEXT);
      const format = str(body.format);
      if (!goal || goal.length < 10) {
        return json({ ok: false, error: "Say a little more, a sentence or two is plenty." }, 400, origin);
      }
      if (goal.length > MAX_TEXT) {
        return json({ ok: false, error: `Keep it under ${MAX_TEXT} characters.` }, 400, origin);
      }
      mail = coachingEmail(name, email, goal, tried, format);
    }

    try {
      await env.EMAIL.send({ to: DESTINATION, from: FROM, ...mail });
    } catch (err) {
      return json(
        { ok: false, error: "That didn't send. Try again in a moment." },
        502,
        origin
      );
    }

    return json({ ok: true }, 200, origin);
  },
};
