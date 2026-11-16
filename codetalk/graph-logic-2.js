
// ---- 绘制:主干、枝柄、关联线、卡片、提交、「你在这里」 ----
function nodeG(id, cls, tip, inner){
  var a = ann(id), p = POS[id];
  var mark = (a.note || (a.tags || []).length) ? '<circle class="mark" cx="' + (p.leaf ? p.x + LW - 4 : p.x + 9) + '" cy="' + (p.leaf ? p.y - LH / 2 + 4 : p.y - 9) + '" r="4.5"/>' : '';
  return '<g class="n ' + cls + (id === sel ? ' sel' : '') + (a.hidden ? ' faded' : '') + '" data-id="' + esc(id) +
    '" tabindex="0" role="button" aria-label="' + esc(tip) + '"><title>' + esc(tip) + '</title>' + inner + mark + '</g>';
}
function card(id, cls, chip, text, extra){     // 卡片只放「类型 + 一句摘要」,文字在框内换行并截成两行
  var p = POS[id], box = 'x="' + p.x + '" y="' + (p.y - LH / 2) + '" width="' + LW + '" height="' + LH + '"';
  // 文字区固定为两行高(34px),放在框的内边距之内 → 任何语言都不会溢出边框
  return nodeG(id, 'leaf ' + cls, text, '<rect ' + box + ' rx="12"' + (extra || '') + '/><foreignObject x="' + (p.x + 12) + '" y="' + (p.y - 17) +
    '" width="' + (LW - 24) + '" height="34"><div class="ct"><b>' + esc(chip) + '</b>' + esc(summary(text)) + '</div></foreignObject>');
}
function line(cls, d, edge, style){            // 可见细线 + 一条透明的粗命中线,方便点中
  return '<path class="' + cls + (selEdge === edge ? ' on' : '') + '" d="' + d + '"' + (style ? ' style="' + style + '"' : '') +
    '/><path class="hit" data-edge="' + esc(edge) + '" d="' + d + '"/>';
}
function cx(p){ return p.x + (p.leaf ? LW / 2 : 0); }
function progress(){
  var noted = TRUNK.filter(isNoted), read = noted.filter(function(c){ return REVIEWED[c.id]; }).length;
  document.getElementById('progress').textContent = t('progress') + ' ' + read + ' / ' + noted.length;
  var bar = document.getElementById('bar'); if(bar) bar.style.width = (noted.length ? Math.round(100 * read / noted.length) : 0) + '%';
  document.getElementById('nextunread').textContent = read < noted.length ? t('next_unread') : t('all_read');
}
function render(){
  if(!TRUNK.length){ document.getElementById('empty').hidden = false; document.getElementById('empty').innerHTML = t('empty');
    document.getElementById('controls').hidden = true; document.getElementById('toolbar').hidden = true; return; }
  layout();
  var s = '', pts = [], lastMonth = '';
  TRUNK.forEach(function(c){
    var p = POS[c.id] || POS['run:' + RUN_OF[c.id]]; if(!p) return;
    if(!pts.length || pts[pts.length - 1] !== p) pts.push(p);
    var m = c.date.slice(0, 7);
    if(m !== lastMonth && POS[c.id]){ s += '<text class="month" x="' + (p.x - 6) + '" y="' + (p.y - 18) + '">' + esc(m) + '</text>'; lastMonth = m; }
  });
  if(pts.length){ s += '<path class="trunk" d="M' + (pts[0].x - 30) + ',' + pts[0].y + pts.map(function(p){ return ' L' + p.x + ',' + p.y; }).join('') + ' L' + (pts[pts.length - 1].x + 30) + ',' + pts[pts.length - 1].y + '"/>'; }
  LEAVES.concat(PLANS).forEach(function(l){     // 枝柄:计划用方向色,未实施为虚线
    var p = POS[l.id], c = POS[l.commit]; if(!p || !c) return;
    var style = l.type === 'plan' ? ' style="stroke:' + dirColor(l.dir) + (l.done ? '' : ';stroke-dasharray:5 4') + '"' : '';
    s += '<path class="stem" data-a="' + l.commit + '" data-b="' + esc(l.id) + '"' + style + ' d="M' + c.x + ',' + c.y + ' C' + c.x + ',' + (c.y + (p.y - c.y) * 0.6) + ' ' + c.x + ',' + p.y + ' ' + p.x + ',' + p.y + '"/>';
  });
  if(sel && BYID[sel] && BYID[sel].type === 'commit' && POS[sel]){   // 选中提交 → 画出它与前后提交的关联线
    neighbours(sel, false).concat(neighbours(sel, true)).forEach(function(o){
      var a = POS[sel], b = POS[o.id] || POS['run:' + RUN_OF[o.id]]; if(!b) return;
      var first = o.ts < BYID[sel].ts ? o.id : sel, second = first === sel ? o.id : sel;
      s += line('arc', 'M' + a.x + ',' + a.y + ' Q' + ((a.x + b.x) / 2) + ',' + (a.y + 24 + Math.min(80, Math.abs(b.x - a.x) / 12)) + ' ' + b.x + ',' + b.y, 'file|' + first + '|' + second);
    });
  }
  userLinks().forEach(function(l){
    var a = POS[l.a], b = POS[l.b]; if(!a || !b) return;
    s += line('ulink', 'M' + cx(a) + ',' + a.y + ' Q' + ((cx(a) + cx(b)) / 2) + ',' + ((a.y + b.y) / 2 - 50) + ' ' + cx(b) + ',' + b.y, 'link|' + l.key);
  });
  PLANS.forEach(function(p){                    // 已实施的计划 → 连到实施它的提交
    var a = POS[p.id], b = p.done && (POS[p.done] || POS['run:' + RUN_OF[p.done]]); if(!a || !b) return;
    s += line('pline', 'M' + (a.x + LW) + ',' + a.y + ' C' + (a.x + LW + 60) + ',' + a.y + ' ' + b.x + ',' + (b.y - 70) + ' ' + b.x + ',' + (b.y - 9), 'plan|' + p.id, 'stroke:' + dirColor(p.dir));
  });
  LEAVES.forEach(function(l){ if(POS[l.id]) s += card(l.id, 'k-' + l.kind + ' src-' + l.source, t('k_' + l.kind), l.text); });
  PLANS.forEach(function(p){
    if(!POS[p.id]) return;
    var color = dirColor(p.dir);
    s += card(p.id, 'k-plan' + (p.done ? ' done' : ''), (p.done ? '✓ ' : '') + (p.dir || t('k_plan')), p.text,
      ' style="stroke:' + color + (p.done ? '' : ';stroke-dasharray:6 4') + '"');
  });
  Object.keys(POS).forEach(function(id){
    var p = POS[id], n = BYID[id];
    if(p.leaf) return;
    if(p.run){
      s += nodeG(id, 'k-run', t('expand_run') + ' · ' + p.run + t('commits_n'), '<rect x="' + (p.x - 24) + '" y="' + (p.y - 11) + '" width="48" height="22" rx="11"/><text x="' + p.x + '" y="' + (p.y + 4) + '" text-anchor="middle">+' + p.run + '</text>');
    } else if(p.plain){
      s += nodeG(id, 'k-plain', '[' + id + '] ' + n.date + ' ' + n.subject, '<circle cx="' + p.x + '" cy="' + p.y + '" r="4"/>');
    } else {
      var ct = commitType(n.subject);
      s += nodeG(id, 'k-commit' + (isNoted(n) && !REVIEWED[id] ? ' unread' : ''), '[' + id + '] ' + n.date + ' ' + n.subject,
        '<circle cx="' + p.x + '" cy="' + p.y + '" r="8"/><foreignObject x="' + (p.x + 12) + '" y="' + (p.y + 9) + '" width="' + (LW - 4) + '" height="32"><div class="cl">' +
        (ct.tag ? '<b>' + esc(ct.tag) + '</b>' : '') + esc(ct.rest) + '</div></foreignObject>');
    }
  });
  var hp = POS[HEAD] || POS['run:' + RUN_OF[HEAD]];
  if(hp){                                       // 「你在这里」:最新提交上的脉动标记
    s += '<g class="here"><title>' + esc(t('here_tip')) + '</title><circle class="pulse" cx="' + hp.x + '" cy="' + hp.y + '" r="9">' +
      '<animate attributeName="r" values="9;26;9" dur="2.6s" repeatCount="indefinite"/><animate attributeName="opacity" values=".5;0;.5" dur="2.6s" repeatCount="indefinite"/></circle>' +
      '<g transform="translate(' + (hp.x - 100) + ',' + (hp.y - 48) + ')"><rect width="88" height="26" rx="13"/><path d="M74,25 L92,40 L84,22 z"/><text x="44" y="17" text-anchor="middle">' + esc(t('here')) + '</text></g></g>';
  }
  svg.innerHTML = s;
  progress();
  paintHits();
}
// ---- 视口:viewBox 始终与画布同比例,k = 每像素多少图上单位 ----
var VB = {x: 0, y: 0, k: 1};
function applyVB(){
  var r = svg.getBoundingClientRect();
  svg.setAttribute('viewBox', VB.x + ' ' + VB.y + ' ' + Math.max(1, r.width * VB.k) + ' ' + Math.max(1, r.height * VB.k));
}
function zoomAt(px, py, factor){               // 以画布上的像素点 (px,py) 为锚缩放
  var k2 = Math.min(8, Math.max(0.2, VB.k * factor));
  VB.x += px * (VB.k - k2); VB.y += py * (VB.k - k2); VB.k = k2; applyVB();
}
function zoom(factor){ var r = svg.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, factor); }
function fit(){                                // 适配:整张图回到视口
  var r = svg.getBoundingClientRect(), w = FULL.x1 - FULL.x0, h = FULL.y1 - FULL.y0;
  VB.k = Math.max(w / Math.max(1, r.width), h / Math.max(1, r.height), 0.2);
  VB.x = FULL.x0 - (r.width * VB.k - w) / 2; VB.y = FULL.y0 - (r.height * VB.k - h) / 2; applyVB();
}
function centerOn(id){
  var p = POS[id] || POS['run:' + RUN_OF[id]]; if(!p) return;
  var r = svg.getBoundingClientRect();
  VB.x = cx(p) - r.width * VB.k / 2; VB.y = p.y - r.height * VB.k / 2; applyVB();
}
function home(){                               // 初始视图:原始大小,把「你在这里」放在画面右侧
  var r = svg.getBoundingClientRect(), p = POS[HEAD] || POS['run:' + RUN_OF[HEAD]] || {x: FULL.x1, y: 0};
  VB.k = 1; VB.x = p.x - r.width * 0.62; VB.y = -r.height / 2; applyVB();
}
