(function(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  var targets = document.querySelectorAll('.chip, .tool');
  if (!('IntersectionObserver' in window)) { targets.forEach(function(t){ t.classList.add('in'); }); return; }
  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    });
  }, { threshold: 0.14, rootMargin: '0px 0px -40px 0px' });
  targets.forEach(function(t){ io.observe(t); });
})();

(function(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.addEventListener('click', function(e){
    var a = e.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute('href').slice(1);
    if (!id) return;
    var target = document.getElementById(id);
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    if (history.pushState) history.pushState(null, '', '#' + id);
  });
})();

(function(){
  var root = document.documentElement;
  var btn = document.getElementById('themeToggle');
  var metaTheme = document.querySelector('meta[name="theme-color"]');
  var DARK_META = '#0E0A18', LIGHT_META = '#FAF8FC';

  function isLight(){ return root.getAttribute('data-theme') === 'light'; }
  function sync(){
    var light = isLight();
    if (btn) btn.setAttribute('aria-label', light ? 'Switch to dark mode' : 'Switch to light mode');
    if (metaTheme) metaTheme.setAttribute('content', light ? LIGHT_META : DARK_META);
  }
  sync();

  if (btn) {
    btn.addEventListener('click', function(){
      var next = isLight() ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch(e) {}
      sync();
    });
  }

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', function(e){
      var saved = null;
      try { saved = localStorage.getItem('theme'); } catch(err) {}
      if (saved) return;
      root.setAttribute('data-theme', e.matches ? 'light' : 'dark');
      sync();
    });
  }
})();

// TODO before this goes live: replace with the real workers.dev URL
// Cloudflare assigns on first deploy of worker/ (see worker/README.md).
var CONTACT_ENDPOINT = /^(localhost|127\.0\.0\.1)$/.test(location.hostname)
  ? 'http://localhost:8787'
  : 'https://megan-warren-contact.mwarren.workers.dev';

// Shared shell for both contact forms (commission on the homepage, coaching
// on /coaching/). Each page supplies its own field list and payload shape;
// this owns validation wiring, loading/success/error states, and the
// honeypot/time-trap anti-spam fields every submission carries.
function wireContactForm(opts){
  var form = document.getElementById(opts.formId);
  if (!form) return;

  var renderedAt = Date.now();
  var submitBtn = form.querySelector('button[type="submit"]');
  var submitLabel = submitBtn.querySelector('span');
  var statusEl = form.querySelector('.cf-status');
  var companyInput = form.querySelector('.cf-hp input');

  var fields = {};
  opts.fields.forEach(function(f){
    fields[f.key] = {
      input: document.getElementById(f.id),
      err: document.getElementById(f.id + '-err'),
      validate: f.validate
    };
  });
  var order = opts.fields.map(function(f){ return f.key; });

  function setError(key, msg){ if (fields[key].err) fields[key].err.textContent = msg || ''; }
  function clearErrors(){ order.forEach(function(k){ setError(k, ''); }); }

  function validate(){
    clearErrors();
    var firstInvalid = null;
    order.forEach(function(key){
      var f = fields[key];
      var msg = f.validate ? f.validate(f.input.value.trim()) : null;
      if (msg) { setError(key, msg); if (!firstInvalid) firstInvalid = key; }
    });
    if (firstInvalid) fields[firstInvalid].input.focus();
    return !firstInvalid;
  }

  function setBusy(busy){
    submitBtn.disabled = busy;
    if (busy) {
      form.setAttribute('aria-busy', 'true');
      submitLabel.innerHTML = '<span class="cf-submit-spin" aria-hidden="true"></span>Sending…';
    } else {
      form.removeAttribute('aria-busy');
      submitLabel.textContent = opts.submitLabel || 'Send message';
    }
  }

  function showStatus(msg, kind){
    statusEl.textContent = msg || '';
    if (kind) statusEl.setAttribute('data-kind', kind); else statusEl.removeAttribute('data-kind');
  }

  function showSuccess(){
    var done = document.createElement('div');
    done.className = 'cf-done';
    done.setAttribute('tabindex', '-1');
    done.innerHTML = opts.successHtml + '<button type="button">Send another message</button>';
    form.replaceWith(done);
    done.focus();
    done.querySelector('button').addEventListener('click', function(){
      done.replaceWith(form);
      form.reset();
      setBusy(false);
      showStatus('');
      fields[order[0]].input.focus();
    });
  }

  form.addEventListener('submit', function(e){
    e.preventDefault();
    if (!validate()) return;

    setBusy(true);
    showStatus('');

    var values = {};
    order.forEach(function(k){ values[k] = fields[k].input.value.trim(); });
    var payload = opts.buildPayload(values);
    payload.company = companyInput ? companyInput.value : '';
    payload.startedAt = renderedAt;

    fetch(CONTACT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function(res){
        return res.json().catch(function(){ return {}; }).then(function(data){
          return { ok: res.ok, data: data };
        });
      })
      .then(function(result){
        if (result.data && result.data.ok) {
          showSuccess();
          return;
        }
        setBusy(false);
        showStatus((result.data && result.data.error) || 'Something went wrong. Try again in a moment.', 'error');
      })
      .catch(function(){
        setBusy(false);
        showStatus('Could not reach the server. Check your connection and try again.', 'error');
      });
  });
}
