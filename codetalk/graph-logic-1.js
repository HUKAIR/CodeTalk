
var DATA = $data;
// ---- i18n:zh/en 字典 + 切换(零外联,复用 localStorage;纯本地零 LLM)----
var I18N = {
  zh: {
    clear:"清除选择", relation:"依据：后续提交触及相同文件，不代表已证实的因果关系。", graph_title: "决策影响图",
    sub_lead: "决策 → 沿时间向前牵动的改动 · 点蓝色决策节点看下游",
    sub_tail: "纯本地零 LLM",
    zoom_in: "放大", zoom_out: "缩小", zoom_fit: "适配窗口", fit: "适配",
    empty: "还没有可画的决策。<br>去关键 commit 留 <b>Vibe-Decision:</b> trailer,或先跑 <b>codetalk digest</b>。",
    panel_hint: "点左侧蓝色(实线=决策记录,虚线=叙事)决策节点,查看它牵动了哪些后续改动。",
    kind_breadcrumb: "原始决策记录", kind_narrative: "生成解释", kind_change: "改动",
    downstream_pre: "关联的后续改动(", downstream_post: "):"
  },
  en: {
    clear:"Clear selection", relation:"Basis: later commits touched the same files; this is not proven causation.", graph_title: "Decision Impact Graph",
    sub_lead: "Decisions → the changes they pull forward over time · click a blue decision node to see downstream",
    sub_tail: "fully local, zero LLM",
    zoom_in: "Zoom in", zoom_out: "Zoom out", zoom_fit: "Fit to window", fit: "Fit",
    empty: "No decisions to draw yet.<br>Leave a <b>Vibe-Decision:</b> trailer on a key commit, or run <b>codetalk digest</b> first.",
    panel_hint: "Click a blue decision node on the left (solid = decision note, dashed = narrative) to see which later changes it pulled forward.",
    kind_breadcrumb: "Source decision record", kind_narrative: "Generated interpretation", kind_change: "Change",
    downstream_pre: "Related later changes (", downstream_post: "):"
  }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang");
  if (s === "zh" || s === "en") return s;
  return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en";
} catch(e){ return "zh"; } })();
var TITLE_PREFIX = (function(){ var h = document.querySelector("h1");
  return h && h.firstChild ? (h.firstChild.nodeValue || "") : ""; })();
var curSel = null;
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
function panelHint(){ panel.innerHTML = '<div class="sub">' + esc(t("panel_hint")) + '</div>'; }
function applyLang(){
  document.documentElement.lang = LANG;
  document.title = TITLE_PREFIX + t("graph_title");
  document.querySelectorAll("[data-i18n]").forEach(function(el){ el.textContent = t(el.getAttribute("data-i18n")); });
  document.querySelectorAll("[data-i18n-title]").forEach(function(el){ el.title = t(el.getAttribute("data-i18n-title")); });
  var lb = document.getElementById("langbtn"); if (lb) lb.textContent = LANG === "zh" ? "EN" : "中文";
  if (window.onLangChange) window.onLangChange();     // 让动态内容(空态/面板)重渲染
}
function toggleLang(){ LANG = LANG === "zh" ? "en" : "zh";
  try { localStorage.setItem("codetalk.lang", LANG); } catch(e){}
  applyLang(); }
var NW = 150, NH = 26, GAPX = 64, GAPY = 44, PAD = 30;
var svg = document.getElementById('svg'), panel = document.getElementById('panel');
var VB = null;            // 当前 viewBox {x,y,w,h};FULL = 整图尺寸
var FULL = {w: 0, h: 0};
function esc(s){ return (s || '').replace(/[&<>]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
function render(){
  var nodes = DATA.nodes, edges = DATA.edges;
  if(!nodes.length){ document.getElementById('empty').hidden = false; document.getElementById('controls').hidden = true; return; }
  var xsArr = []; for(var i=0;i<nodes.length;i++){ if(xsArr.indexOf(nodes[i].ts)<0) xsArr.push(nodes[i].ts); }
  xsArr.sort(function(a,b){ return a-b; });
  var xi = {}; for(var j=0;j<xsArr.length;j++){ xi[xsArr[j]] = j; }
  // 纵向分层:决策一带、改动另一带;带内按列(时间)顺序贪心占行,避免同行重叠与边线穿节点。
  var byId = {}, maxRow = 0;
  function layout(kind){
    var band = nodes.filter(function(n){ return (kind === 'change') === (n.kind === 'change'); });
    band.sort(function(a,b){ return xi[a.ts] - xi[b.ts]; });
    var rowFreeCol = [];                                    // 每行已占用到的列号(含间距)
    for(var p=0;p<band.length;p++){
      var n = band[p], col = xi[n.ts], r = 0;
      while(r < rowFreeCol.length && rowFreeCol[r] > col){ r++; }  // 找第一条该列空闲的行
      if(r === rowFreeCol.length){ rowFreeCol.push(0); }
      rowFreeCol[r] = col + 1;                              // 占住本列(+1 列间隔防紧邻重叠)
      n._row = r; n.x = PAD + col * (NW + GAPX);
    }
    return rowFreeCol.length;
  }
  var decRows = layout('decision');
  layout('change');
  var GAP_BAND = 1;                                         // 决策带与改动带之间留一空行
  for(var k=0;k<nodes.length;k++){
    var nd0 = nodes[k];
    var rowBase = (nd0.kind === 'change') ? (decRows + GAP_BAND) : 0;
    nd0.y = PAD + (rowBase + nd0._row) * GAPY;
    if(rowBase + nd0._row > maxRow){ maxRow = rowBase + nd0._row; }
    byId[nd0.id] = nd0;
  }
  var W = PAD * 2 + xsArr.length * (NW + GAPX), H = PAD * 2 + (maxRow + 1) * GAPY;
  FULL.w = W; FULL.h = H;
  svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  setViewBox(0, 0, W, H);
  var s = '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#4a4a4a"/></marker></defs>';
  for(var e=0;e<edges.length;e++){
    var a = byId[edges[e].from], b = byId[edges[e].to];
    if(!a || !b) continue;
    var x1 = a.x + NW, y1 = a.y + NH/2, x2 = b.x, y2 = b.y + NH/2;
    s += '<path class="edge" d="M' + x1 + ',' + y1 + ' C' + (x1+30) + ',' + y1 + ' ' + (x2-30) + ',' + y2 + ' ' + x2 + ',' + y2 + '"/>';
  }
  for(var m=0;m<nodes.length;m++){
    var nd = nodes[m];
    var cls = nd.kind === 'breadcrumb' ? 'dec-b' : (nd.kind === 'narrative' ? 'dec-n' : 'chg');
    var full = (nd.text || nd.subject || '');
    var lbl = esc(full.slice(0, 18));
    var tip = '[' + nd.id + '] ' + full + (nd.badge ? ('  ·  ' + nd.badge) : '');
    s += '<g class="node" data-id="' + nd.id + '" tabindex="0" role="button" aria-label="' + esc(tip) + '">';
    s += '<title>' + esc(tip) + '</title>';                 // 原生 tooltip:悬停显全名
    s += '<rect class="' + cls + '" x="' + nd.x + '" y="' + nd.y + '" width="' + NW + '" height="' + NH + '" rx="3"/>';
    s += '<text x="' + (nd.x + 6) + '" y="' + (nd.y + 17) + '" font-size="12">' + lbl + '</text>';
    if(nd.badge){ s += '<text x="' + (nd.x + NW - 8) + '" y="' + (nd.y - 4) + '" font-size="11" fill="#5b9cff">●</text>'; }
    s += '</g>';
  }
  svg.innerHTML = s;
  var gs = svg.querySelectorAll('.node');
  for(var g=0;g<gs.length;g++){
    var act = (function(id){ return function(){ showPanel(id); }; })(gs[g].getAttribute('data-id'));
    gs[g].addEventListener('click', act);
    gs[g].addEventListener('keydown', (function(fn){ return function(e){  // 键盘可达:Enter/Space 激活
      if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); fn(); }
    }; })(act));
  }
}
function setViewBox(x, y, w, h){
  VB = {x: x, y: y, w: w, h: h};
  svg.setAttribute('viewBox', x + ' ' + y + ' ' + w + ' ' + h);
}
function zoom(factor){                                      // <1 放大、>1 缩小;以中心为基准
  if(!VB){ return; }
  var nw = VB.w * factor, nh = VB.h * factor;
  setViewBox(VB.x + (VB.w - nw) / 2, VB.y + (VB.h - nh) / 2, nw, nh);
}
function fit(){ setViewBox(0, 0, FULL.w, FULL.h); }        // 适配:整图回到 viewBox
function showPanel(id){
  curSel = id;
  var rects = svg.querySelectorAll('rect');
  for(var i=0;i<rects.length;i++){ rects[i].classList.remove('sel'); }
  var g = svg.querySelector('.node[data-id="' + id + '"]');
  if(g){ g.querySelector('rect').classList.add('sel'); }
  var n = null, dn = DATA.nodes;
  for(var k=0;k<dn.length;k++){ if(dn[k].id === id){ n = dn[k]; break; } }
  if(!n) return;
  var downs = [];
  for(var e=0;e<DATA.edges.length;e++){
    if(DATA.edges[e].from === id){
      for(var x=0;x<dn.length;x++){ if(dn[x].id === DATA.edges[e].to){ downs.push(dn[x]); break; } }
    }
  }
  var kindTxt = n.kind === 'breadcrumb' ? t('kind_breadcrumb') : (n.kind === 'narrative' ? t('kind_narrative') : t('kind_change'));
  var h = '<h2>[' + n.id + '] ' + kindTxt + ' · ' + esc(n.date) + '</h2>';
  if(n.text){ h += '<div class="txt">' + esc(n.text) + '</div>'; }
  if(n.badge){ h += '<div class="txt" style="color:var(--accent)">' + esc(n.badge) + '</div>'; }
  h += '<div class="sub">' + t('downstream_pre') + downs.length + t('downstream_post') + '</div><ul>';
  for(var d=0;d<downs.length;d++){ h += '<li><b>[' + downs[d].id + ']</b> ' + esc(downs[d].subject) + '</li>'; }
  h += '</ul><p class="sub">' + esc(t('relation')) + '</p>';
  panel.innerHTML = h;
}
document.getElementById('clear').onclick = function(){ curSel = null; svg.querySelectorAll('.sel').forEach(function(el){ el.classList.remove('sel'); }); panelHint(); };
document.getElementById('zin').addEventListener('click', function(){ zoom(0.8); });
document.getElementById('zout').addEventListener('click', function(){ zoom(1.25); });
document.getElementById('zfit').addEventListener('click', fit);
document.addEventListener('keydown', function(e){           // 键盘缩放:+ 放大 / - 缩小 / 0·f 适配
  if(e.metaKey || e.ctrlKey || e.altKey) return;
  var tag = e.target && e.target.tagName;
  if(tag === 'INPUT' || tag === 'TEXTAREA') return;
  if(e.key === '+' || e.key === '='){ e.preventDefault(); zoom(0.8); }
  else if(e.key === '-'){ e.preventDefault(); zoom(1.25); }
  else if(e.key === '0' || e.key === 'f'){ e.preventDefault(); fit(); }
});
// 语言切换:静态元素由 applyLang 换,动态内容(空态提示 + 右侧面板)经 onLangChange 重渲染
window.onLangChange = function(){
  var em = document.getElementById('empty'); if(em){ em.innerHTML = t('empty'); }
  if(curSel){ showPanel(curSel); } else { panelHint(); }
};
var _lb = document.getElementById('langbtn'); if(_lb){ _lb.addEventListener('click', toggleLang); }
render();
applyLang();
