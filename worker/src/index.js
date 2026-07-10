// Contact form API for megan-warren.com.
// Receives a POST from the portfolio's contact form, validates it, and
// emails it to Megan via Cloudflare Email Service (send_email binding).
// Nothing here is reachable from the browser except through fetch(), so
// the destination address below is never exposed on the site itself.

const DESTINATION = "meganraewarren@gmail.com";
const FROM = "Megan Warren Portfolio <contact@megan-warren.com>";

const ALLOWED_ORIGINS = [
  "https://megan-warren.com",
  "https://www.megan-warren.com",
];
const LOCAL_ORIGIN = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;

const TOPICS = {
  commission: "A commission / tool idea",
  coaching: "1:1 AI coaching",
  unsure: "Not sure yet",
};

const MIN_FILL_MS = 2500; // faster than this and it's almost certainly a bot
const MAX_MESSAGE = 5000;
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
    if (typeof body.company === "string" && body.company.trim() !== "") {
      return json({ ok: true }, 200, origin);
    }
    const startedAt = Number(body.startedAt);
    if (Number.isFinite(startedAt) && Date.now() - startedAt < MIN_FILL_MS) {
      return json({ ok: true }, 200, origin);
    }

    const name = typeof body.name === "string" ? body.name.trim() : "";
    const email = typeof body.email === "string" ? body.email.trim() : "";
    const message = typeof body.message === "string" ? body.message.trim() : "";
    const topic = TOPICS[body.topic] ? body.topic : "unsure";

    if (!name || name.length > MAX_NAME) {
      return json({ ok: false, error: "Enter your name." }, 400, origin);
    }
    if (!email || email.length > 320 || !EMAIL_RE.test(email)) {
      return json({ ok: false, error: "Enter a valid email address." }, 400, origin);
    }
    if (!message || message.length < 10) {
      return json({ ok: false, error: "Say a little more about what you need." }, 400, origin);
    }
    if (message.length > MAX_MESSAGE) {
      return json({ ok: false, error: `Keep it under ${MAX_MESSAGE} characters.` }, 400, origin);
    }

    const subject = `Portfolio contact: ${name} (${TOPICS[topic]})`;
    const text =
      `New message from megan-warren.com\n\n` +
      `From: ${name} <${email}>\n` +
      `Re: ${TOPICS[topic]}\n\n` +
      `${message}\n`;
    const html =
      `<p><strong>New message from megan-warren.com</strong></p>` +
      `<p>From: ${escapeHtml(name)} &lt;${escapeHtml(email)}&gt;<br>` +
      `Re: ${escapeHtml(TOPICS[topic])}</p>` +
      `<p>${escapeHtml(message).replace(/\n/g, "<br>")}</p>`;

    try {
      await env.EMAIL.send({ to: DESTINATION, from: FROM, subject, text, html });
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
