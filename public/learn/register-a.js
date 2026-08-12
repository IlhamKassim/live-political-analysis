/* Register A's theme behaviour, shared by every page under public/learn/
   (see register-a.css's header for why this is a shared file, not a copy
   pasted into each page).

   Two independent pieces, deliberately not bundled into one function:

   - The pre-paint read runs synchronously, inline in <head>, before this
     file is even requested — see each page's own inline <script> for that
     half (same pattern as public_page.py's _THEME_INIT_SCRIPT). A returning
     reader's stored theme has to apply before first paint, which an
     external, deferred-loading script can't guarantee; that part stays
     inline on every page and is not moved here.
   - initThemeToggle, below, wires the visible button once the DOM is
     ready. This half has nothing time-critical about it, so it is the
     part safe to share as a normal external file. */

function initThemeToggle(buttonId) {
  var btn = document.getElementById(buttonId);
  if (!btn) return;

  function dark() {
    var set = document.documentElement.getAttribute("data-theme");
    return set ? set === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function label() { btn.textContent = dark() ? "Light" : "Dark"; }
  btn.addEventListener("click", function () {
    var next = dark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    label();
  });
  label();
}
