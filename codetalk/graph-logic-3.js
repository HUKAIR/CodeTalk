
// ---- 高亮:搜索命中常亮,悬停时改亮相关节点 ----
function paintHits(){ hover(null); }
function hover(id){
  if(DRAG) return;
  var rel = id ? related(id) : null;
  svg.classList.toggle('dim', !!(rel || hits));
  svg.querySelectorAll('.n, .stem').forEach(function(el){
    var a = el.getAttribute('data-id'), on;
    if(rel) on = a ? rel[a] : (rel[el.getAttribute('data-a')] && rel[el.getAttribute('data-b')]);
    else on = hits && a && hits[a];
    el.classList.toggle('hot', !!on);
  });
}
function reveal(id){                           // 让被折叠/被筛掉的节点重新出现
  var n = BYID[id]; if(!n) return;
  var cid = n.type === 'commit' ? id : n.commit;
  if(n.type === 'leaf') SHOW[n.kind] = true;
  if(n.type === 'plan') SHOW.plan = true;
  if(RUN_OF[cid]) { EXPANDED[RUN_OF[cid]] = true; SHOW.plain = true; }
  if(ann(id).hidden || ann(cid).hidden) SHOW.hidden = true;
  syncChips();
}
function syncChips(){
  document.querySelectorAll('.chip[data-show]').forEach(function(b){ b.setAttribute('aria-pressed', String(!!SHOW[b.getAttribute('data-show')])); });
}
// ---- 写入:先改本地状态立即重画,服务模式再写回本机缓存 ----
function post(path, payload){
  return fetch(apiPath(path), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(projectPayload(payload))})
    .then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; });
}
function merged(id, patch){
  var o = {}, a = ann(id), k;
  for(k in a) o[k] = a[k];
  for(k in patch){ if(patch[k] == null) delete o[k]; else o[k] = patch[k]; }
  return o;
}
function saveAnn(key, data, done){             // data 为 null = 删除
  if(data === null) delete ANN[key]; else ANN[key] = data;
  render();
  if(!SERVE){ if(done) done(true); return; }
  post('/graph/annotation', {key: key, data: data}).then(function(j){
    if(j && j.annotations){ ANN = j.annotations; render(); }
    if(done) done(!!j);
  });
}
function setAnn(id, patch){
  saveAnn(id, merged(id, patch), function(ok){ if(sel === id) showPanel(ok ? t('saved') : t('save_fail')); });
}
// ---- 选择 ----
function activate(id){
  if(id.indexOf('run:') === 0){ EXPANDED[id.slice(4)] = true; render(); return; }
  var p = pick; pick = null;
  if(p && p.mode === 'link' && p.from !== id){ saveAnn('link:' + p.from + '>' + id, {}, function(){ select(p.from); }); return; }
  if(p && p.mode === 'done'){                   // 计划 → 指定实施它的提交
    var n = BYID[id], cid = n.type === 'commit' ? id : n.commit;
    saveAnn(p.from, merged(p.from, {done: cid}), function(){ select(p.from); });
    return;
  }
  select(id);
}
function select(id){ sel = id; selEdge = null; render(); showPanel(); }
function selectEdge(edge){ selEdge = edge; render(); showEdge(); }
function goItem(n, cls){
  var body = n.type === 'commit' ? '<b>[' + n.id + ']</b> ' + esc(n.subject)
    : (n.type === 'plan' ? '<i class="dot" style="background:' + dirColor(n.dir) + '"></i>' + esc((n.dir ? n.dir + ' · ' : '') + n.text) : esc(n.text));
  return '<li class="' + (cls || '') + '" data-go="' + esc(n.id) + '" tabindex="0">' + body + '</li>';
}
function srcButton(sha, label){ return SERVE ? '<div class="row"><button id="loadsrc" data-sha="' + esc(sha) + '">' + label + '</button></div><pre id="src" hidden></pre>' : ''; }
// ---- 详情面板:卡片只有摘要,全文与来龙去脉都在这里 ----
function editBlock(id, status){
  var a = ann(id), h = '<h3>' + t('my_notes') + '</h3>';
  var links = userLinks().filter(function(l){ return l.a === id || l.b === id; });
  if(SERVE){
    h += '<textarea id="an-note" placeholder="' + esc(t('note_ph')) + '">' + esc(a.note || '') + '</textarea>';
    h += '<input id="an-tags" type="text" placeholder="' + esc(t('tags_ph')) + '" value="' + esc((a.tags || []).join(', ')) + '">';
    h += '<div class="row"><label><input id="an-hidden" type="checkbox"' + (a.hidden ? ' checked' : '') + '> ' + t('hide') + '</label></div>';
    h += '<div class="row"><button id="an-save" class="primary">' + t('save') + '</button><button id="an-link">' + t('link') + '</button>' +
      (a.pin ? '<button id="an-unpin">' + t('unpin') + '</button>' : '') + '<span id="status">' + esc(status || '') + '</span></div>';
  } else {
    if(a.note) h += '<div class="txt">' + esc(a.note) + '</div>';
    h += (a.tags || []).map(function(x){ return '<span class="tag">' + esc(x) + '</span>'; }).join('');
    h += '<p class="sub">' + esc(t('readonly')) + '</p>';
  }
  if(links.length){
    h += '<h3>' + t('links') + '</h3><ul>' + links.map(function(l){
      var o = BYID[l.a === id ? l.b : l.a]; if(!o) return '';
      return '<li data-go="' + esc(o.id) + '" tabindex="0">' + esc(clip(o.subject || o.text, 44)) +
        (SERVE ? ' <button data-unlink="' + esc(l.key) + '">' + t('remove') + '</button>' : '') + '</li>';
    }).join('') + '</ul>';
  }
  return h;
}
function planBlock(cid){
  var mine = PLANS.filter(function(p){ return p.commit === cid; }), h = '<h3>' + t('plans') + '</h3>';
  if(mine.length) h += '<ul>' + mine.map(function(p){ return goItem(p, p.done ? 'pdone' : 'popen'); }).join('') + '</ul>';
  if(SERVE){
    var dirs = []; PLANS.forEach(function(p){ if(p.dir && dirs.indexOf(p.dir) < 0) dirs.push(p.dir); });
    h += '<input id="pl-text" type="text" maxlength="300" placeholder="' + esc(t('plan_ph')) + '"><input id="pl-dir" type="text" maxlength="24" list="dirs" placeholder="' + esc(t('dir_ph')) +
      '"><datalist id="dirs">' + dirs.map(function(d){ return '<option value="' + esc(d) + '">'; }).join('') + '</datalist><div class="row"><button id="pl-add">' + t('add_plan') + '</button></div>';
  }
  return h;
}
function showPanel(status){
  var n = sel && BYID[sel], h = '';
  if(!n){ panel.innerHTML = '<div class="sub">' + esc(t('panel_hint')) + '</div>'; return; }
  if(n.type === 'commit'){
    var ct = commitType(n.subject);
    h += '<h2>' + (ct.tag ? '<span class="tag">' + esc(ct.tag) + '</span>' : '') + esc(ct.rest) + '</h2><div class="meta">' + esc(n.date) + ' · ' + esc(n.sha) + '</div>';
    if(isNoted(n)){
      h += '<div class="row">' + (REVIEWED[n.id] ? '<span class="ok">✓ ' + t('understood') + '</span>'
        : (SERVE ? '<button id="markread" class="primary">' + t('mark_read') + '</button>' : '<span class="sub">' + t('not_understood') + '</span>')) + '</div>';
    }
    ['decision', 'rejected', 'watch'].forEach(function(kind){
      var ls = LEAVES_OF[n.id].filter(function(l){ return l.kind === kind; });
      if(ls.length) h += '<h3>' + t('k_' + kind) + '</h3><ul>' + ls.map(function(l){ return goItem(l, 'k-' + kind); }).join('') + '</ul>';
    });
    h += planBlock(n.id);
    h += '<h3>' + t('files') + ' (' + n.nfiles + ')</h3><ul>' + n.files.slice(0, 12).map(function(f){ return '<li class="file">' + esc(f) + '</li>'; }).join('') + '</ul>';
    if(n.nfiles > 12) h += '<div class="sub">+' + (n.nfiles - 12) + '</div>';
    [['upstream', false], ['downstream', true]].forEach(function(dir){
      var ns = neighbours(n.id, dir[1]);
      if(ns.length) h += '<h3>' + t(dir[0]) + ' (' + ns.length + ')</h3><ul>' + ns.map(function(o){ return goItem(o); }).join('') + '</ul>';
    });
    h += '<div class="row"><button id="copysha">' + t('copy') + '</button></div>' + srcButton(n.sha, t('load_src'));
  } else if(n.type === 'plan'){
    h += '<h3><i class="dot" style="background:' + dirColor(n.dir) + '"></i>' + esc(n.dir || t('k_plan')) + ' · ' + t(n.done ? 'plan_done' : 'plan_open') + '</h3><div class="txt">' + esc(n.text) + '</div>';
    h += '<h3>' + t('plan_from') + '</h3><ul>' + goItem(BYID[n.commit]) + '</ul>';
    if(n.done && BYID[n.done]) h += '<h3>' + t('done_by') + '</h3><ul>' + goItem(BYID[n.done]) + '</ul>';
    if(SERVE) h += '<div class="row"><button id="pl-done" class="primary">' + t('mark_done') + '</button>' + (n.done ? '<button id="pl-reopen">' + t('reopen') + '</button>' : '') +
      '<button id="pl-del">' + t('remove') + '</button><span id="status">' + esc(status || '') + '</span></div>';
    else h += '<p class="sub">' + esc(t('readonly')) + '</p>';
    panel.innerHTML = h; wirePanel(); return;
  } else {
    h += '<h3>' + t('k_' + n.kind) + ' · ' + t('src_' + n.source) + '</h3><div class="txt">' + esc(n.text) + '</div>';
    h += '<h3>' + t('of_commit') + '</h3><ul>' + goItem(BYID[n.commit]) + '</ul>';
  }
  panel.innerHTML = h + editBlock(sel, status);
  wirePanel();
}
function showEdge(){                           // 点线:两端是谁、共同改了什么、后一个提交的实际修改
  var p = selEdge.split('|'), h = '';
  if(p[0] === 'file'){
    var a = BYID[p[1]], b = BYID[p[2]], files = sharedFiles(a, b);
    h += '<h2>' + t('e_file') + '</h2><h3>' + t('earlier') + '</h3><ul>' + goItem(a) + '</ul><h3>' + t('later') + '</h3><ul>' + goItem(b) + '</ul>';
    h += '<h3>' + t('shared') + ' (' + files.length + ')</h3><ul>' + files.slice(0, 20).map(function(f){ return '<li class="file">' + esc(f) + '</li>'; }).join('') + '</ul>';
    h += srcButton(b.sha, t('load_later')) + '<p class="sub">' + esc(t('relation')) + '</p>';
  } else if(p[0] === 'link'){
    var ends = p[1].slice(5).split('>');
    h += '<h2>' + t('e_link') + '</h2><ul>' + ends.map(function(id){ return BYID[id] ? goItem(BYID[id]) : ''; }).join('') + '</ul>';
    if(SERVE) h += '<div class="row"><button data-unlink="' + esc(p[1]) + '">' + t('remove') + '</button></div>';
  } else {
    var pl = BYID[selEdge.slice(5)];
    h += '<h2>' + t('e_plan') + '</h2><ul>' + goItem(pl) + '</ul><h3>' + t('done_by') + '</h3><ul>' + goItem(BYID[pl.done]) + '</ul>' + srcButton(BYID[pl.done].sha, t('load_later'));
  }
  panel.innerHTML = h; wirePanel();
}
function on(id, fn){ var el = document.getElementById(id); if(el) el.addEventListener('click', fn); }
function wirePanel(){
  panel.querySelectorAll('[data-go]').forEach(function(el){
    function go(e){
      if(e.target.closest('[data-unlink]')) return;
      var id = el.getAttribute('data-go'); reveal(id); select(id); centerOn(id);
    }
    el.addEventListener('click', go);
    el.addEventListener('keydown', function(e){ if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); go(e); } });
  });
  panel.querySelectorAll('[data-unlink]').forEach(function(b){
    b.addEventListener('click', function(){ selEdge = null; saveAnn(b.getAttribute('data-unlink'), null, function(){ showPanel(); }); });
  });
  on('copysha', function(){
    var b = document.getElementById('copysha');
    try { navigator.clipboard.writeText(BYID[sel].sha).then(function(){ b.textContent = t('copied'); }); } catch(e){}
  });
  on('loadsrc', function(){
    var pre = document.getElementById('src'); pre.hidden = false; pre.textContent = t('loading');
    fetch(apiPath('/api/commit/' + document.getElementById('loadsrc').getAttribute('data-sha'))).then(function(r){ return r.ok ? r.json() : null; })
      .then(function(j){ pre.textContent = j ? (j.subject + '\n\n' + (j.body || '') + '\n\n' + (j.diff || '')) : t('load_fail'); })
      .catch(function(){ pre.textContent = t('load_fail'); });
  });
  on('markread', function(){                    // 「我看懂了」→ 记入本机的回看记录,理解债随之减少
    var n = BYID[sel];
    post('/reviewed', {sha: n.sha}).then(function(j){ if(j){ REVIEWED[n.id] = 1; render(); } showPanel(j ? '' : t('save_fail')); });
  });
  on('an-save', function(){
    var tags = document.getElementById('an-tags').value.split(/[,，]/).map(function(x){ return x.trim().slice(0, 32); }).filter(Boolean).slice(0, 8);
    setAnn(sel, {note: document.getElementById('an-note').value.slice(0, 2000) || null,
                 tags: tags.length ? tags : null, hidden: document.getElementById('an-hidden').checked ? true : null});
  });
  on('an-link', function(){ pick = {mode: 'link', from: sel}; document.getElementById('status').textContent = t('link_pick'); });
  on('an-unpin', function(){ setAnn(sel, {pin: null}); });
  on('pl-add', function(){
    var text = document.getElementById('pl-text').value.trim(); if(!text) return;
    var cid = sel, dir = document.getElementById('pl-dir').value.trim();
    saveAnn('plan:' + cid + ':' + Date.now().toString(36), dir ? {text: text, dir: dir} : {text: text}, function(){ if(sel === cid) showPanel(); });
  });
  on('pl-done', function(){ pick = {mode: 'done', from: sel}; document.getElementById('status').textContent = t('done_pick'); });
  on('pl-reopen', function(){ setAnn(sel, {done: null}); });
  on('pl-del', function(){ var cid = BYID[sel].commit; saveAnn(sel, null, function(){ select(cid); }); });
}
// ---- 指针:点选 / 拖节点固定 / 拖空白平移 / 滚轮缩放 ----
var press = null, raf = 0;
function at(e){ var r = svg.getBoundingClientRect(); return {px: e.clientX - r.left, py: e.clientY - r.top}; }
svg.addEventListener('pointerdown', function(e){
  if(e.button !== 0) return;
  var g = e.target.closest('.n'), h = e.target.closest('[data-edge]'), pt = at(e), id = g ? g.getAttribute('data-id') : null;
  press = {id: id, edge: h ? h.getAttribute('data-edge') : null, px: pt.px, py: pt.py, vx: VB.x, vy: VB.y, moved: false};
  if(id && POS[id]){ press.ox = POS[id].x; press.oy = POS[id].y; }
  svg.setPointerCapture(e.pointerId);
});
svg.addEventListener('pointermove', function(e){
  if(!press) return;
  var pt = at(e), dx = pt.px - press.px, dy = pt.py - press.py;
  if(!press.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
  press.moved = true;
  if(press.id && press.id.indexOf('run:') !== 0){
    DRAG = {id: press.id, x: press.ox + dx * VB.k, y: press.oy + dy * VB.k};
    if(!raf) raf = requestAnimationFrame(function(){ raf = 0; render(); });
  } else {
    svg.classList.add('panning'); VB.x = press.vx - dx * VB.k; VB.y = press.vy - dy * VB.k; applyVB();
  }
});
svg.addEventListener('pointerup', function(){
  var p = press; press = null; svg.classList.remove('panning');
  if(!p) return;
  if(p.moved && DRAG){ var d = DRAG; DRAG = null; setAnn(d.id, {pin: {x: Math.round(d.x), y: Math.round(d.y)}}); return; }
  if(p.moved) return;
  if(p.id) activate(p.id); else if(p.edge) selectEdge(p.edge);
});
svg.addEventListener('pointercancel', function(){ press = null; DRAG = null; svg.classList.remove('panning'); render(); });
svg.addEventListener('pointerover', function(e){ if(press) return; var g = e.target.closest('.n'); hover(g ? g.getAttribute('data-id') : null); });
svg.addEventListener('pointerleave', function(){ if(!press) hover(null); });
svg.addEventListener('wheel', function(e){ e.preventDefault(); var pt = at(e); zoomAt(pt.px, pt.py, Math.exp(e.deltaY * 0.0015)); }, {passive: false});
svg.addEventListener('keydown', function(e){                // 键盘可达:Enter/Space 激活节点
  var g = e.target.closest && e.target.closest('.n');
  if(g && (e.key === 'Enter' || e.key === ' ')){
    e.preventDefault(); var id = g.getAttribute('data-id'); activate(id);
    var again = svg.querySelector('.n[data-id="' + id + '"]'); if(again) again.focus();
  }
});
// ---- 搜索、筛选、理解进度 ----
var hitList = [], hitAt = -1;
function haystack(n){
  var a = ann(n.id);
  return [n.id, n.sha, n.subject, n.text, n.dir, (n.files || []).join(' '), a.note, (a.tags || []).join(' ')].join(' ').toLowerCase();
}
function search(q){
  q = q.trim().toLowerCase(); hits = null; hitList = []; hitAt = -1;
  if(q){
    hits = {};
    TRUNK.concat(LEAVES, PLANS).forEach(function(n){ if(haystack(n).indexOf(q) >= 0){ hits[n.id] = 1; hitList.push(n.id); } });
    hitList.forEach(reveal);
  }
  document.getElementById('qn').textContent = q ? String(hitList.length) : '';
  render();
}
var qEl = document.getElementById('q');
qEl.addEventListener('input', function(){ search(qEl.value); });
qEl.addEventListener('keydown', function(e){                // Enter:跳到下一个命中
  if(e.key !== 'Enter' || !hitList.length) return;
  hitAt = (hitAt + 1) % hitList.length; select(hitList[hitAt]); centerOn(hitList[hitAt]);
});
document.querySelectorAll('.chip[data-show]').forEach(function(b){
  b.addEventListener('click', function(){ var k = b.getAttribute('data-show'); SHOW[k] = !SHOW[k]; syncChips(); render(); });
});
document.getElementById('nextunread').addEventListener('click', function(){   // 从最早一个还没看懂的提交开始补
  var c = TRUNK.filter(function(x){ return isNoted(x) && !REVIEWED[x.id] && !ann(x.id).hidden; })[0];
  if(c){ reveal(c.id); select(c.id); centerOn(c.id); }
});
// ---- 缩放按钮、键盘、主题、语言 ----
document.getElementById('zin').addEventListener('click', function(){ zoom(0.8); });
document.getElementById('zout').addEventListener('click', function(){ zoom(1.25); });
document.getElementById('zfit').addEventListener('click', fit);
document.getElementById('zhome').addEventListener('click', home);
document.addEventListener('keydown', function(e){           // + 放大 / - 缩小 / 0·f 适配 / Esc 取消
  if(e.metaKey || e.ctrlKey || e.altKey) return;
  var tag = e.target && e.target.tagName;
  if(e.key === 'Escape'){ pick = null; if(tag !== 'INPUT' && tag !== 'TEXTAREA'){ sel = null; selEdge = null; render(); showPanel(); } return; }
  if(tag === 'INPUT' || tag === 'TEXTAREA') return;
  if(e.key === '+' || e.key === '='){ e.preventDefault(); zoom(0.8); }
  else if(e.key === '-'){ e.preventDefault(); zoom(1.25); }
  else if(e.key === '0' || e.key === 'f'){ e.preventDefault(); fit(); }
});
window.addEventListener('resize', applyVB);
document.getElementById('themebtn').addEventListener('click', function(){
  var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('codetalk.theme', next); } catch(e){}
});
function applyLang(){
  document.documentElement.lang = LANG;
  document.title = TITLE_PREFIX + t('graph_title');
  document.querySelectorAll('[data-i18n]').forEach(function(el){ el.textContent = t(el.getAttribute('data-i18n')); });
  document.querySelectorAll('[data-i18n-title]').forEach(function(el){ el.title = t(el.getAttribute('data-i18n-title')); });
  document.querySelectorAll('[data-i18n-ph]').forEach(function(el){ el.placeholder = t(el.getAttribute('data-i18n-ph')); });
  document.getElementById('langbtn').textContent = LANG === 'zh' ? 'EN' : '中文';
  render();
  if(selEdge) showEdge(); else showPanel();
}
document.getElementById('langbtn').addEventListener('click', function(){
  LANG = LANG === 'zh' ? 'en' : 'zh';
  try { localStorage.setItem('codetalk.lang', LANG); } catch(e){}
  applyLang();
});
applyLang();
home();
