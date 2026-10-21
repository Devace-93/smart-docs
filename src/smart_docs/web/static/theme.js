(function () {
  // Runs in <head> so the theme and the signed-in state are set before first paint.
  var THEME_KEY = '3m4.theme';
  var TOKEN_KEY = 'sd.token';
  var root = document.documentElement;

  // Theme: same key and precedence as the other 3m4 apps (system preference
  // unless the user chose one explicitly).
  function apply(t) { root.setAttribute('data-theme', t); }
  var saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch (e) {}
  if (saved === 'dark' || saved === 'light') apply(saved);

  // Signed-in state: public pages are cached, so the header decides client-side
  // whether to show "Open the editor" or "Log in" (html.authed, see app.css).
  var token = null;
  try { token = localStorage.getItem(TOKEN_KEY); } catch (e) {}
  if (token) root.classList.add('authed');

  // Mobile menu: the hamburger shows the nav links below the header bar.
  function setMenu(open) {
    var menu = document.getElementById('mobile-menu');
    var button = document.querySelector('[data-menu-toggle]');
    if (!menu || !button) return;
    menu.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    button.closest('.top').classList.toggle('menu-open', open);
  }
  function menuIsOpen() {
    var menu = document.getElementById('mobile-menu');
    return !!menu && !menu.hidden;
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-theme-toggle]')) {
      var cur = root.getAttribute('data-theme');
      if (!cur) cur = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      var next = cur === 'dark' ? 'light' : 'dark';
      apply(next);
      try { localStorage.setItem(THEME_KEY, next); } catch (e2) {}
      return;
    }
    if (e.target.closest('[data-menu-toggle]')) { setMenu(!menuIsOpen()); return; }
    // A click on a menu link or anywhere outside the header closes the menu.
    if (menuIsOpen() && (e.target.closest('#mobile-menu a') || !e.target.closest('.top'))) setMenu(false);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && menuIsOpen()) setMenu(false);
  });
  var desktop = window.matchMedia('(min-width: 768px)');
  function onDesktop(ev) { if (ev.matches && menuIsOpen()) setMenu(false); }
  if (desktop.addEventListener) desktop.addEventListener('change', onDesktop); else desktop.addListener(onDesktop);
})();
