(function () {
  // Runs in <head> so the theme and the signed-in state are set before first paint.
  var THEME_KEY = '3m4.theme';
  var root = document.documentElement;

  // Theme: same key and precedence as the other 3m4 apps (system preference
  // unless the user chose one explicitly).
  function apply(t) { root.setAttribute('data-theme', t); }
  var saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch (e) {}
  if (saved === 'dark' || saved === 'light') apply(saved);

  // Signed-in state: public pages are cached (Cache-Control: public), so the
  // header decides client-side whether to show "Open the editor" or "Log in"
  // (html.authed, see app.css). The session lives in the accounts.3m4.net
  // cookie (SD-014), which this page cannot read, so ask the accounts API the
  // same way the session.js widget does: one credentialed GET, one refresh
  // attempt on an expired access token, re-checked when the tab regains focus.
  var meta = document.querySelector('meta[name="accounts-url"]');
  var accounts = meta ? meta.getAttribute('content').replace(/\/$/, '') : '';
  function setAuthed(on) { root.classList.toggle('authed', !!on); }
  function session() {
    return fetch(accounts + '/api/session', { credentials: 'include' }).then(function (r) {
      if (r.ok) return true;
      if (r.status !== 401) return false;
      return r.json().then(function (body) {
        if (!body || !body.error || body.error.code !== 'session_expired') return false;
        return fetch(accounts + '/api/session/refresh', {
          method: 'POST', credentials: 'include',
          headers: { 'Content-Type': 'application/json' }, body: '{}',
        }).then(function (rr) { return rr.ok; });
      }, function () { return false; });
    }, function () { return false; });
  }
  function checkSession() {
    if (!accounts || typeof fetch !== 'function') return;
    session().then(setAuthed, function () { setAuthed(false); });
  }
  checkSession();
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') checkSession();
  });

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
