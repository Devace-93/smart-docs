/* Smart Docs editor. One file, no build step. Talks to /api/v1 with fetch. */
(function () {
  'use strict';
  var root = document.getElementById('app');
  var BASE = root.dataset.base || '';
  var TIERS = (root.dataset.tiers || '').split(',').filter(Boolean);
  // The identity service (SD-014). The session is the `3m4_session` cookie it set; this
  // page never sees a token. Session calls go to the accounts origin with credentials.
  var ACCOUNTS = (document.querySelector('meta[name="accounts-url"]') || {}).content || 'https://accounts.3m4.net';
  var S = { newKey: null, me: null, projects: [], project: null, tree: [], node: null, dirty: false, collapsed: {}, view: 'editor', preview: false, search: null };

  // ---- helpers ---------------------------------------------------------
  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === 'class') el.className = attrs[k];
      else if (k === 'html') el.innerHTML = attrs[k];
      else if (k.indexOf('on') === 0) el.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined) el.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) { if (c === null || c === undefined) return; el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return el;
  }
  function toast(msg, bad) {
    var t = h('div', { class: 'toast' + (bad ? ' bad' : '') }, [msg]);
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, bad ? 5000 : 2500);
  }
  function accountsUrl(page) { return ACCOUNTS + '/' + page + '?return_to=' + encodeURIComponent(location.origin + '/app'); }
  function toLogin() { location.assign(accountsUrl('login')); }
  async function accountsPost(path) {
    var r = await fetch(ACCOUNTS + '/api' + path, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    return r.ok;
  }
  // html.authed drives the shared header (Open the editor vs Log in, see app.css).
  function setAuthed(on) { document.documentElement.classList.toggle('authed', !!on); }
  async function logout() { try { await accountsPost('/session/logout'); } catch (e) {} setAuthed(false); location.assign('/'); }
  var refreshing = null;
  function refreshSession() { if (!refreshing) refreshing = accountsPost('/session/refresh').catch(function () { return false; }).finally(function () { refreshing = null; }); return refreshing; }
  async function api(method, path, body, retried) {
    var opts = { method: method, headers: {}, credentials: 'same-origin' };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    var r = await fetch('/api/v1' + path, opts);
    if (r.status === 204) return null;
    var data = null; try { data = await r.json(); } catch (e) {}
    if (!r.ok) {
      var code = data && data.code;
      if (r.status === 401 && code === 'session_expired' && !retried) {
        // The access token ran out: ask accounts for a fresh one, then retry once.
        if (await refreshSession()) return api(method, path, body, true);
      }
      if (r.status === 401 && code !== 'unauthorized') { toLogin(); }
      var msg = (data && data.message) || ('HTTP ' + r.status);
      if (data && data.hint) msg += ' ' + data.hint;
      var err = new Error(msg); err.status = r.status; err.code = code; err.data = data; throw err;
    }
    return data;
  }
  function go(hash) { if (location.hash === hash) render(); else location.hash = hash; }
  function fmtDate(s) { return s ? new Date(s).toLocaleString() : ''; }
  function confirmLeave() { return !S.dirty || confirm('You have unsaved changes. Leave anyway?'); }

  // ---- shell -------------------------------------------------------------
  async function loadProjects() { S.projects = await api('GET', '/projects'); }
  async function loadTree() { S.tree = S.project ? await api('GET', '/projects/' + S.project.slug + '/tree') : []; }

  function sidebar() {
    var sel = h('select', { onchange: function () { if (!confirmLeave()) { sel.value = S.project ? S.project.slug : ''; return; } go('#/p/' + sel.value); } },
      [h('option', { value: '' }, ['— project —'])].concat(S.projects.map(function (p) { var o = h('option', { value: p.slug }, [p.name]); if (S.project && p.slug === S.project.slug) o.selected = true; return o; })));
    var newProj = h('button', { class: 'mini', title: 'New project', onclick: async function () {
      var name = prompt('Project name'); if (!name) return;
      try { var p = await api('POST', '/projects', { name: name }); await loadProjects(); go('#/p/' + p.slug); } catch (ex) { toast(ex.message, true); }
    } }, ['+']);
    var tools = S.project ? h('div', { class: 'row' }, [
      h('button', { class: 'mini', onclick: function () { newNode('page'); } }, ['+ page']),
      h('button', { class: 'mini', onclick: function () { newNode('folder'); } }, ['+ folder']),
      h('button', { class: 'mini', onclick: function () { S.view = 'search'; render(); } }, ['search']),
      h('a', { class: 'mini btn', href: S.project.public_url, target: '_blank', title: 'Public project page' }, ['public ↗'])
    ]) : null;
    var views = h('nav', { class: 'views' }, [
      h('a', { href: '#/projects' }, ['Projects']),
      h('a', { href: '#/keys' }, ['API keys']),
      h('a', { href: '#/usage' }, ['Usage']),
      h('a', { href: '#/settings' }, ['Settings']),
      h('a', { href: ACCOUNTS + '/profile', target: '_blank', rel: 'noopener' }, ['Account ↗']),
      h('a', { href: '#', onclick: function (e) { e.preventDefault(); if (!confirmLeave()) return; logout(); } }, ['Log out'])
    ]);
    return h('aside', { class: 'side' }, [h('div', { class: 'row' }, [sel, newProj]), tools, treeList(S.tree), views]);
  }

  function treeList(items) {
    return h('ul', { class: 'ptree' }, items.map(function (n) {
      var isSel = S.node && S.node.path === n.path && S.view === 'editor';
      var collapsed = !!S.collapsed[n.path];
      var row = h('div', { class: 'n' + (isSel ? ' sel' : ''), onclick: function () {
        if (n.kind === 'folder' && n.children.length) { S.collapsed[n.path] = !collapsed; }
        openNode(n.path);
      } }, [
        h('span', { class: 'k' }, [n.kind === 'folder' ? (collapsed ? '▸' : '▾') : '·']),
        h('span', null, [n.title]),
        n.public ? h('span', { class: 'pub' }, ['public']) : null
      ]);
      var kids = (!collapsed && n.children.length) ? treeList(n.children) : null;
      return h('li', null, [row, kids]);
    }));
  }

  async function newNode(kind) {
    if (!S.project) return;
    var title = prompt(kind === 'folder' ? 'Folder name' : 'Page title'); if (!title) return;
    var parent = S.node ? (S.node.kind === 'folder' ? S.node.path : S.node.path.split('/').slice(0, -1).join('/')) : '';
    if (S.node) { var p2 = prompt('Create under (folder path, empty for root)', parent); if (p2 === null) return; parent = p2; }
    try {
      var node = await api('POST', '/projects/' + S.project.slug + '/nodes', { kind: kind, title: title, parent_path: parent || null, markdown: kind === 'page' ? '# ' + title + '\n\n' : '' });
      await loadTree(); S.dirty = false; go('#/p/' + S.project.slug + '/' + node.path);
    } catch (ex) { toast(ex.message, true); }
  }

  async function openNode(path) {
    if (!confirmLeave()) return;
    S.view = 'editor';
    go('#/p/' + S.project.slug + '/' + path);
  }

  // ---- editor -------------------------------------------------------------
  function editor() {
    if (!S.project) return h('div', { class: 'empty' }, ['Pick a project on the left, or create one with +.']);
    if (!S.node) return h('div', { class: 'empty' }, [S.tree.length ? 'Pick a page in the tree.' : 'This project is empty. Add a page with “+ page”.']);
    var n = S.node;
    if (n.kind === 'folder') {
      return h('div', { class: 'editor' }, [
        h('div', { class: 'bar' }, [h('h2', null, ['Folder: ' + n.title]), h('span', { class: 'muted' }, [n.path])]),
        h('p', { class: 'muted' }, ['Folders hold pages and other folders. Select the folder and press “+ page” to add a page inside it.']),
        h('div', { class: 'bar' }, [
          h('button', { onclick: function () { moveDialog(n); } }, ['Move / rename…']),
          h('button', { class: 'danger', onclick: function () { deleteNode(n); } }, ['Delete folder and contents'])
        ])
      ]);
    }
    var title = h('input', { type: 'text', value: n.title, oninput: function () { S.dirty = true; } });
    var ta = h('textarea', { spellcheck: 'false', oninput: function () { S.dirty = true; if (S.preview) schedulePreview(); } }, [n.markdown || '']);
    var preview = h('div', { class: 'preview prose', html: n.html || '' });
    var previewTimer = null;
    function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(async function () { try { var r = await api('POST', '/render', { markdown: ta.value }); preview.innerHTML = r.html; } catch (e) {} }, 500); }
    var saveBtn = h('button', { class: 'primary', onclick: save }, ['Save']);
    async function save() {
      saveBtn.disabled = true;
      try {
        var out = await api('PATCH', '/projects/' + S.project.slug + '/nodes/' + n.path, { markdown: ta.value, title: title.value, expected_version: n.version });
        S.node = out; S.dirty = false; await loadTree(); render(); toast('Saved. Version ' + out.version + '. Summary and tags are on their way.');
        pollEnrichment(out.path, out.version);
      } catch (ex) {
        if (ex.status === 409) { if (confirm(ex.message + '\n\nOverwrite with your version?')) { n.version = undefined; var out2 = await api('PATCH', '/projects/' + S.project.slug + '/nodes/' + n.path, { markdown: ta.value, title: title.value }); S.node = out2; S.dirty = false; await loadTree(); render(); } }
        else toast(ex.message, true);
      } finally { saveBtn.disabled = false; }
    }
    var pubBtn = h('button', { onclick: async function () {
      try { var out = await api('POST', '/projects/' + S.project.slug + '/nodes/' + n.path + '/publish', { public: !n.public }); n.public = out.public; n.version = out.version; n.public_url = out.public_url; await loadTree(); render(); toast(out.public ? 'Published at ' + out.public_url : 'Unpublished'); } catch (ex) { toast(ex.message, true); }
    } }, [n.public ? 'Unpublish' : 'Publish']);
    var bar = h('div', { class: 'bar' }, [
      title, saveBtn, pubBtn,
      h('button', { onclick: function () { S.preview = !S.preview; render(); } }, [S.preview ? 'Hide preview' : 'Preview']),
      h('button', { onclick: function () { moveDialog(n); } }, ['Move…']),
      h('button', { class: 'danger', onclick: function () { deleteNode(n); } }, ['Delete'])
    ]);
    var st = n.enrich_status || 'pending';
    var stClass = st === 'done' || st === 'agent' ? 'ok' : (st === 'failed' || st === 'rate_limited' ? 'bad' : 'warn');
    var status = h('div', { class: 'status' }, [
      h('span', null, ['Path ', h('code', null, [n.path])]),
      h('span', null, ['v' + n.version]),
      h('span', { class: stClass, title: n.enrich_error || '' }, ['metadata: ' + st]),
      n.public_url ? h('a', { href: n.public_url, target: '_blank' }, ['public page ↗']) : h('span', { class: 'muted' }, ['private']),
      n.public_url ? h('a', { href: n.public_url + '.md', target: '_blank' }, ['.md']) : null
    ]);
    var meta = (n.summary || (n.tags && n.tags.length)) ? h('div', { class: 'status' }, [
      n.summary ? h('span', null, [n.summary]) : null,
      h('span', null, (n.tags || []).map(function (t) { return h('span', { class: 'tag' }, [t]); }))
    ]) : null;
    var body = S.preview ? h('div', { class: 'split' }, [ta, preview]) : ta;
    var wrap = h('div', { class: 'editor' }, [bar, status, meta, body]);
    wrap.addEventListener('keydown', function (e) { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); } });
    return wrap;
  }

  var pollTimer = null;
  function pollEnrichment(path, version) {
    clearTimeout(pollTimer); var tries = 0;
    (function tick() {
      pollTimer = setTimeout(async function () {
        if (!S.node || S.node.path !== path || S.dirty) return;
        try { var fresh = await api('GET', '/projects/' + S.project.slug + '/nodes/' + path); if (fresh.enrich_status !== 'pending') { S.node = fresh; await loadTree(); render(); return; } } catch (e) {}
        if (++tries < 20) tick();
      }, 3000);
    })();
  }

  async function moveDialog(n) {
    var parent = prompt('New parent folder path (empty for root)', n.path.split('/').slice(0, -1).join('/')); if (parent === null) return;
    var slug = prompt('Slug (last part of the path)', n.path.split('/').pop()); if (slug === null) return;
    try { var out = await api('POST', '/projects/' + S.project.slug + '/nodes/' + n.path + '/move', { new_parent_path: parent || null, new_slug: slug }); await loadTree(); S.dirty = false; go('#/p/' + S.project.slug + '/' + out.path); toast('Moved to ' + out.path); } catch (ex) { toast(ex.message, true); }
  }
  async function deleteNode(n) {
    if (!confirm('Delete "' + n.title + '"' + (n.kind === 'folder' ? ' and everything inside' : '') + '?')) return;
    try { await api('DELETE', '/projects/' + S.project.slug + '/nodes/' + n.path); S.node = null; S.dirty = false; await loadTree(); go('#/p/' + S.project.slug); } catch (ex) { toast(ex.message, true); }
  }

  // ---- other views ----------------------------------------------------------
  function searchView() {
    var q = h('input', { type: 'text', placeholder: 'Ask in plain words…', value: (S.search && S.search.q) || '' });
    var list = h('ul', { class: 'results' });
    async function run() {
      list.innerHTML = '';
      try {
        var hits = await api('GET', '/projects/' + S.project.slug + '/search?q=' + encodeURIComponent(q.value) + '&k=10');
        S.search = { q: q.value };
        if (!hits.length) list.appendChild(h('li', { class: 'muted' }, ['No embedded pages match yet. New pages become searchable once the worker embeds them.']));
        hits.forEach(function (x) { list.appendChild(h('li', null, [h('a', { href: '#/p/' + S.project.slug + '/' + x.path }, [x.title]), ' ', h('span', { class: 'score' }, ['score ' + x.score]), h('div', { class: 'muted' }, [x.summary || ''])])); });
      } catch (ex) { toast(ex.message, true); }
    }
    var form = h('form', { onsubmit: function (e) { e.preventDefault(); run(); } }, [h('div', { class: 'bar' }, [q, h('button', { class: 'primary', type: 'submit' }, ['Search'])])]);
    return h('div', { class: 'editor' }, [h('h2', null, ['Semantic search in ' + S.project.name]), form, list]);
  }

  async function projectsView() {
    var rows = S.projects.map(function (p) { return h('tr', null, [h('td', null, [h('a', { href: '#/p/' + p.slug }, [p.name])]), h('td', null, [h('code', null, [p.slug])]), h('td', null, [h('a', { href: p.public_url, target: '_blank' }, ['public']), ' · ', h('a', { href: p.llms_txt_url, target: '_blank' }, ['llms.txt'])]), h('td', null, [h('button', { class: 'mini', onclick: async function () { var d = prompt('Description', p.description || ''); if (d === null) return; try { await api('PATCH', '/projects/' + p.slug, { description: d }); await loadProjects(); render(); } catch (ex) { toast(ex.message, true); } } }, ['describe']), ' ', h('button', { class: 'mini danger', onclick: async function () { if (!confirm('Delete project "' + p.name + '" and all its pages?')) return; try { await api('DELETE', '/projects/' + p.slug); await loadProjects(); if (S.project && S.project.slug === p.slug) S.project = null; render(); } catch (ex) { toast(ex.message, true); } } }, ['delete'])])]); });
    return h('div', null, [h('h2', null, ['Projects']), S.projects.length ? h('table', { class: 'list' }, [h('thead', null, [h('tr', null, [h('th', null, ['Name']), h('th', null, ['Slug']), h('th', null, ['Public']), h('th', null, [''])])]), h('tbody', null, rows)]) : h('p', { class: 'empty' }, ['No projects yet. Press + in the sidebar.'])]);
  }

  async function keysView() {
    var keys = await api('GET', '/me/keys');
    var shown = h('div');
    if (S.newKey) {
      var k = S.newKey; S.newKey = null;  // shown once, on the render right after creation
      shown.appendChild(h('div', { class: 'card' }, [h('p', null, ['Copy this key now. It is shown once.']), h('div', { class: 'keyshow' }, [k.key]), h('p', { class: 'muted' }, ['Claude Code: ', h('code', null, ['claude mcp add --transport http smart-docs ' + BASE + '/mcp --header "Authorization: Bearer ' + k.key + '"'])])]));
    }
    var name = h('input', { type: 'text', placeholder: 'key name (e.g. claude-code)', value: 'claude-code' });
    var scopes = ['read', 'write', 'publish'].map(function (s) { var c = h('input', { type: 'checkbox', value: s }); c.checked = true; return h('label', { style: 'display:inline-flex;gap:4px;margin-right:12px' }, [c, s]); });
    var form = h('form', { onsubmit: async function (e) {
      e.preventDefault();
      var sc = scopes.map(function (l) { return l.firstChild; }).filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
      try { S.newKey = await api('POST', '/me/keys', { name: name.value, scopes: sc }); render(); } catch (ex) { toast(ex.message, true); }
    } }, [h('div', { class: 'bar' }, [name, h('span', null, scopes), h('button', { class: 'primary', type: 'submit' }, ['Create key'])])]);
    var rows = keys.map(function (k) { return h('tr', null, [h('td', null, [k.name]), h('td', null, [h('code', null, [k.prefix + '…'])]), h('td', null, [k.scopes.join(', ')]), h('td', null, [fmtDate(k.created_at)]), h('td', null, [k.last_used_at ? fmtDate(k.last_used_at) : 'never']), h('td', null, [h('button', { class: 'mini danger', onclick: async function () { if (!confirm('Revoke this key?')) return; await api('DELETE', '/me/keys/' + k.id); render(); } }, ['revoke'])])]); });
    return h('div', null, [h('h2', null, ['API keys']), h('p', { class: 'muted' }, ['Agents authenticate with ', h('code', null, ['Authorization: Bearer sd_…']), ' on the REST API and on the MCP endpoint ', h('code', null, [BASE + '/mcp']), '.']), form, shown, keys.length ? h('table', { class: 'list' }, [h('thead', null, [h('tr', null, [h('th', null, ['Name']), h('th', null, ['Prefix']), h('th', null, ['Scopes']), h('th', null, ['Created']), h('th', null, ['Last used']), h('th')])]), h('tbody', null, rows)]) : h('p', { class: 'muted' }, ['No keys yet.'])]);
  }

  async function usageView() {
    var u = await api('GET', '/me/usage');
    function row(k, v) { return h('tr', null, [h('td', null, [k]), h('td', null, [String(v)])]); }
    return h('div', null, [h('h2', null, ['Model usage']), h('table', { class: 'list' }, [h('tbody', null, [
      row('Current tier', u.tier), row('Tiers on this instance', u.tiers_available.join(', ')),
      row('Hosted: used today / daily limit', u.hosted.enabled ? u.hosted.used_today + ' / ' + u.hosted.daily_limit + ' (resets ' + fmtDate(u.hosted.resets_at) + ')' : 'disabled'),
      row('Local: used last hour / hourly limit', u.local.enabled ? u.local.used_last_hour + ' / ' + u.local.hourly_limit + ' (max ' + u.local.per_10s_limit + ' per 10 s)' : 'disabled'),
      row('BYOK', u.byok.enabled ? (u.byok.configured ? 'configured' : 'not configured') : 'disabled'),
      row('Agent mode', u.agent.note)
    ])])]);
  }

  async function settingsView() {
    var me = S.me;
    var tier = h('select', null, TIERS.map(function (t) { var o = h('option', { value: t }, [t]); if (t === me.tier) o.selected = true; return o; }));
    var url = h('input', { type: 'text', placeholder: 'https://api.openai.com/v1', value: me.byok_base_url || '' });
    var model = h('input', { type: 'text', placeholder: 'gpt-4o-mini', value: me.byok_model || '' });
    var key = h('input', { type: 'password', placeholder: me.byok_configured ? '(stored, leave blank to keep)' : 'sk-…' });
    var form = h('form', { onsubmit: async function (e) {
      e.preventDefault();
      var body = { tier: tier.value, byok_base_url: url.value, byok_model: model.value };
      if (key.value) body.byok_key = key.value;
      try { S.me = await api('PATCH', '/me', body); toast('Saved'); render(); } catch (ex) { toast(ex.message, true); }
    } }, [
      h('label', null, ['Model tier for summaries and tags']), tier,
      h('p', { class: 'muted' }, ['hosted: the operator pays, capped per day · local: the operator\'s Ollama, capped per hour · byok: your own OpenAI-compatible endpoint · agent: the agent supplies summary and tags, nothing is called.']),
      TIERS.indexOf('byok') >= 0 ? h('div', { class: 'card' }, [h('h3', null, ['Bring your own key']), h('label', null, ['Base URL']), url, h('label', null, ['Model']), model, h('label', null, ['API key (stored encrypted)']), key]) : null,
      h('p', null, [h('button', { class: 'primary', type: 'submit' }, ['Save'])])
    ]);
    return h('div', null, [h('h2', null, ['Settings']), h('p', { class: 'muted' }, ['Signed in as ', me.email, ' · handle ', h('code', null, [me.handle]), ' · e-mail, password, avatar and handle are managed at ', h('a', { href: ACCOUNTS + '/profile', target: '_blank', rel: 'noopener' }, ['your 3m4 account']), '. Renaming the handle there renames your public URLs here.']), form]);
  }

  // ---- router -------------------------------------------------------------------
  async function render() {
    root.innerHTML = '';
    var hash = location.hash || '#/projects';
    var parts = hash.slice(2).split('/');
    try {
      if (!S.me) S.me = await api('GET', '/me');  // 401 sends the browser to the accounts login page
    } catch (ex) { if (ex.status !== 401) toast(ex.message, true); return; }
    setAuthed(true);
    var nav = document.getElementById('nav-user');
    if (nav) { nav.innerHTML = ''; nav.appendChild(h('a', { class: 'nav-user', href: ACCOUNTS + '/profile', title: 'Your 3m4 account' }, [S.me.avatar_url ? h('img', { src: S.me.avatar_url, alt: '' }) : null, '@' + S.me.handle])); }
    if (!S.me.email_verified) {
      // Everything but /me answers 403 email_unverified until the address is confirmed.
      root.appendChild(h('div', { class: 'auth' }, [
        h('h1', null, ['Verify your e-mail']),
        h('p', null, ['Open the link sent to ', h('strong', null, [S.me.email]), ' to start using the editor.']),
        h('p', null, [h('a', { class: 'btn primary', href: ACCOUNTS + '/profile' }, ['Resend or change the address'])]),
        h('p', { class: 'muted' }, [h('a', { href: '#', onclick: async function (e) { e.preventDefault(); await refreshSession(); S.me = null; render(); } }, ['I verified it, reload'])])
      ]));
      return;
    }
    try { if (!S.projects.length) await loadProjects(); } catch (ex) { toast(ex.message, true); return; }
    var pane = h('section', { class: 'pane' });
    if (parts[0] === 'p' && parts[1]) {
      var slug = decodeURIComponent(parts[1]);
      if (!S.project || S.project.slug !== slug) { S.project = S.projects.find(function (p) { return p.slug === slug; }) || null; S.node = null; S.search = null; if (S.project) await loadTree(); }
      var path = parts.slice(2).map(decodeURIComponent).join('/');
      if (path) {
        if (!S.node || S.node.path !== path) { try { S.node = await api('GET', '/projects/' + slug + '/nodes/' + path); S.view = 'editor'; } catch (ex) { toast(ex.message, true); S.node = null; } }
      } else if (S.view !== 'search') { S.node = null; }
      pane.appendChild(S.view === 'search' ? searchView() : editor());
    } else {
      S.view = 'editor';
      var v = parts[0];
      try { pane.appendChild(v === 'keys' ? await keysView() : v === 'usage' ? await usageView() : v === 'settings' ? await settingsView() : await projectsView()); } catch (ex) { toast(ex.message, true); }
    }
    root.appendChild(h('div', { class: 'shell' }, [sidebar(), pane]));
  }
  window.addEventListener('hashchange', render);
  window.addEventListener('beforeunload', function (e) { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });
  // A tab that comes back after a while re-checks the session (accounts may have logged it out).
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible' && S.me && !S.dirty) { S.me = null; render(); } });
  render();
})();
