#!/usr/bin/env python3
"""Run JavaScript in the Chrome tab showing Search Console.

The JS is base64'd into the AppleScript so quoting can never mangle it, which
is the thing that silently breaks these otherwise.
"""
import base64, subprocess, sys

def run_js(js, match="search.google.com/search-console"):
    b64 = base64.b64encode(js.encode()).decode()
    scpt = '''
tell application "Google Chrome"
  repeat with w in windows
    repeat with t in tabs of w
      if (URL of t as string) contains "%s" then
        return execute t javascript "eval(atob('%s'))"
      end if
    end repeat
  end repeat
  return "NO-TAB"
end tell''' % (match, b64)
    p = subprocess.run(["osascript", "-e", scpt], capture_output=True, text=True)
    if p.returncode != 0:
        return "ERR: " + p.stderr.strip()[:300]
    return p.stdout.strip()

if __name__ == "__main__":
    print(run_js(sys.stdin.read()))
