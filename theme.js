/* Light or dark: follows the device until the visitor picks one with the
   header switch; the pick is remembered in this browser (key "theme"). */
(function () {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem("theme"); } catch (e) {}
  if (saved === "dark" || saved === "light") root.setAttribute("data-theme", saved);
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  function current() {
    return root.getAttribute("data-theme") || (mq.matches ? "dark" : "light");
  }
  function paint() {
    var dark = current() === "dark";
    var b = document.querySelector(".theme");
    if (b) {
      b.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      b.setAttribute("aria-pressed", dark ? "true" : "false");
    }
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) metas[i].setAttribute("content", dark ? "#1F1535" : "#FBF7FC");
  }
  function ready() {
    var b = document.querySelector(".theme");
    if (b) b.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
      paint();
    });
    if (mq.addEventListener) mq.addEventListener("change", paint);
    paint();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready);
  else ready();
})();
