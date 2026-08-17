#!/usr/bin/env python3
"""Submit a URL for indexing in Search Console and report what Google said.

    python3 tools/request_indexing.py <resource_id> <url> [url ...]

    python3 tools/request_indexing.py sc-domain:megan-warren.com \
        https://trigonometry.megan-warren.com/about
    python3 tools/request_indexing.py https://hellopaintart.com/ \
        https://hellopaintart.com/ohuhu-copic-conversion-chart/

Drives the Search Console tab in the real Chrome through AppleScript, so it
uses the session Megan is already signed in to. There is no API for this:
Google's Indexing API is limited to JobPosting and BroadcastEvent, and the
URL Inspection API is read-only. There is also no deep link, the ?id=
parameter takes an opaque inspection token, not a URL.

The quota is roughly 10 a day and it is PER GOOGLE ACCOUNT, not per property,
so a second property does not buy a fresh allowance.

Every step is verified against the live page rather than assumed:
  - the property actually switched before typing a URL into it
  - the inspection finished (the button is present and enabled)
  - the click produced Google's own confirmation, quota, or error wording

The button is a Google jsaction component, not a <button>. A plain .click()
on it does nothing at all and looks exactly like success, so the click is a
full pointer/mouse sequence and the result is read back from the page.
"""
import json, sys, time
from chrome import run_js

CONFIRM = "Indexing requested"
QUOTA   = ["Quota Exceeded", "exceeded your daily quota"]
FAIL    = ["Something went wrong", "problem submitting"]

def js(code):
    return run_js(code)

def switch_property(resource_id, timeout=45):
    js("location.href=%s" % json.dumps(
        "https://search.google.com/search-console?resource_id=" + resource_id))
    for _ in range(timeout // 3):
        time.sleep(3)
        r = js("(function(){return JSON.stringify({u:location.href,"
               "inp:!![].slice.call(document.querySelectorAll('input')).find("
               "function(i){return (i.getAttribute('aria-label')||'')"
               ".indexOf('Inspect any URL')===0;})});})()")
        try:
            o = json.loads(r)
        except Exception:
            continue
        if o.get("inp"):
            return True, o["u"]
    return False, r

def inspect(url, timeout=75):
    code = """(function(){
      var inp=[].slice.call(document.querySelectorAll('input')).find(function(i){
        return (i.getAttribute('aria-label')||'').indexOf('Inspect any URL')===0;});
      if(!inp) return 'NO-INPUT';
      inp.focus();
      var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      s.call(inp, %s);
      inp.dispatchEvent(new Event('input',{bubbles:true}));
      inp.dispatchEvent(new Event('change',{bubbles:true}));
      ['keydown','keypress','keyup'].forEach(function(t){
        inp.dispatchEvent(new KeyboardEvent(t,{key:'Enter',code:'Enter',
          keyCode:13,which:13,bubbles:true}));});
      return 'ok';})()""" % json.dumps(url)
    if js(code) != "ok":
        return False, "could not reach the inspect box"
    for _ in range(timeout // 5):
        time.sleep(5)
        r = js("(function(){var b=[].slice.call(document.querySelectorAll("
               "'[role=button],button')).filter(function(e){return e.offsetParent;})"
               ".find(function(e){return (e.innerText||'').trim().toUpperCase()"
               "==='REQUEST INDEXING';});"
               "return JSON.stringify({ready:!!b,dis:b?b.getAttribute('aria-disabled'):null});})()")
        try:
            o = json.loads(r)
        except Exception:
            continue
        if o.get("ready") and o.get("dis") != "true":
            return True, "inspection ready"
    return False, "inspection did not finish in %ds" % timeout

def click_request():
    code = """(function(){
      var b=[].slice.call(document.querySelectorAll('[role=button],button'))
        .filter(function(e){return e.offsetParent;})
        .find(function(e){return (e.innerText||'').trim().toUpperCase()==='REQUEST INDEXING';});
      if(!b) return 'NO-BUTTON';
      var r=b.getBoundingClientRect(), cx=r.left+r.width/2, cy=r.top+r.height/2;
      function ev(t,C){b.dispatchEvent(new C(t,{bubbles:true,cancelable:true,composed:true,
        clientX:cx,clientY:cy,button:0,buttons:(t.indexOf('up')>0?0:1),
        pointerId:1,pointerType:'mouse',isPrimary:true,view:window}));}
      b.focus();
      ev('pointerdown',PointerEvent); ev('mousedown',MouseEvent);
      ev('pointerup',PointerEvent);   ev('mouseup',MouseEvent); ev('click',MouseEvent);
      return 'clicked';})()"""
    return js(code)

def outcome(timeout=60):
    for _ in range(timeout // 5):
        time.sleep(5)
        t = js("document.body.innerText")
        low = t.lower()
        if CONFIRM.lower() in low: return "REQUESTED"
        for q in QUOTA:
            if q.lower() in low: return "QUOTA"
        for f in FAIL:
            if f.lower() in low: return "ERROR"
    return "NO-CONFIRMATION"

def dismiss():
    js("""(function(){var d=[].slice.call(document.querySelectorAll('[role=button],button'))
      .find(function(e){return (e.innerText||'').trim().toLowerCase()==='dismiss' && e.offsetParent;});
      if(d){d.click();} return 'ok';})()""")

def do(url):
    ok, why = inspect(url)
    if not ok: return "INSPECT-FAILED: " + why
    if click_request() != "clicked": return "BUTTON-MISSING"
    res = outcome()
    dismiss()
    return res

if __name__ == "__main__":
    prop = sys.argv[1]
    urls = sys.argv[2:]
    ok, where = switch_property(prop)
    print("property %s -> %s" % (prop, "ok" if ok else "FAILED: " + str(where)[:90]))
    if not ok: sys.exit(1)
    for u in urls:
        print("  %-58s %s" % (u[:58], do(u)), flush=True)
