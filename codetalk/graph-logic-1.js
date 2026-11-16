
var DATA = $data;
var SERVE = $serve;
// ---- i18n:默认中文;zh/en 字典 + 切换(零外联,复用 localStorage;纯本地零 LLM)----
var I18N = {
  zh: {
    graph_title: "开发脉络图", sub_tail: "纯本地零 LLM",
    sub_lead: "主干是按时间排列的提交;向上长出决策与计划,向下长出被否决方案与待验证事项",
    zoom_in: "放大", zoom_out: "缩小", zoom_fit: "适配窗口", fit: "适配",
    hint: "滚轮缩放 · 拖动空白平移 · 拖动节点可固定位置 · 点线看两端的修改", search_ph: "搜索提交、决策、文件、批注",
    k_decision: "决策", k_rejected: "被否决", k_watch: "待验证", k_plan: "计划", k_plain: "无记录提交", k_hidden: "已隐藏",
    empty: "还没有可画的提交。<br>在关键 commit 留 <b>Vibe-Decision:</b> / <b>Vibe-Rejected:</b> / <b>Vibe-Watch:</b>,这里就会长出枝叶。",
    panel_hint: "点任意节点或连线查看详情。卡片实线=决策记录(作者原文),虚线=生成解释;实心圆点是还没看懂的提交,空心是已理解的;「+N」是折叠起来的一段无记录提交,点开即可展开。",
    here: "你在这里", here_tip: "当前最新提交", progress: "已理解", next_unread: "下一个未读", all_read: "全部已理解",
    understood: "已理解", not_understood: "还没标记为已理解", mark_read: "我看懂了,标记为已理解",
    src_breadcrumb: "作者原文", src_narrative: "生成解释(非作者原文)", of_commit: "所属提交", full_text: "全文",
    files: "改动的文件", upstream: "之前改到相同文件的提交", downstream: "之后改到相同文件的提交",
    relation: "依据:两个提交触及相同文件,不代表已证实的因果关系。",
    load_src: "读提交原文与差异", load_later: "读后一个提交的实际修改", loading: "读取中…", load_fail: "读取失败", copy: "复制完整 SHA", copied: "已复制",
    my_notes: "我的批注", note_ph: "写下你对这个节点的理解或提醒(只存本机)", tags_ph: "标签,用逗号分隔",
    hide: "在图上隐藏此节点", save: "保存", saved: "已保存", save_fail: "保存失败", unpin: "解除固定位置",
    link: "连到另一个节点", link_pick: "请点另一个节点完成连线(Esc 取消)", links: "手动连线", remove: "移除",
    plans: "计划方向", plan_ph: "接下来打算做什么", dir_ph: "方向名称(同名同色)", add_plan: "添加计划",
    plan_open: "计划中", plan_done: "已实施", mark_done: "标记为已实施", done_pick: "请点实施它的那个提交(Esc 取消)",
    reopen: "改回计划中", done_by: "实施提交", plan_from: "从这个提交延伸",
    e_file: "两个提交改到了相同文件", e_link: "手动连线", e_plan: "计划与它的实施提交", shared: "共同改到的文件", earlier: "较早的提交", later: "较晚的提交",
    readonly: "静态页面只读。运行 codetalk graph --serve 后可写批注、标记已理解、添加计划、建立连线。",
    expand_run: "展开这段无记录提交", commits_n: " 个提交",
    ct_feat: "新功能", ct_fix: "修复", ct_docs: "文档", ct_refactor: "重构", ct_test: "测试", ct_chore: "杂项", ct_perf: "性能", ct_ci: "流水线", ct_build: "构建", ct_style: "格式", ct_revert: "回退"
  },
  en: {
    graph_title: "Development Thread", sub_tail: "fully local, zero LLM",
    sub_lead: "The trunk is commits in time order; decisions and plans grow upward, rejected options and open watches grow downward",
    zoom_in: "Zoom in", zoom_out: "Zoom out", zoom_fit: "Fit to window", fit: "Fit",
    hint: "Wheel to zoom · drag empty space to pan · drag a node to pin it · click a line to see what changed", search_ph: "Search commits, decisions, files, notes",
    k_decision: "Decision", k_rejected: "Rejected", k_watch: "Watch", k_plan: "Plan", k_plain: "Commits without notes", k_hidden: "Hidden",
    empty: "No commits to draw yet.<br>Leave <b>Vibe-Decision:</b> / <b>Vibe-Rejected:</b> / <b>Vibe-Watch:</b> on key commits and leaves will grow here.",
    panel_hint: "Click any node or line for details. On cards, solid = decision note (the author's words), dashed = generated interpretation. Filled dots are commits you have not understood yet, hollow ones are understood; a \"+N\" pill is a folded run of commits without notes.",
    here: "You are here", here_tip: "Latest commit", progress: "Understood", next_unread: "Next unread", all_read: "All understood",
    understood: "Understood", not_understood: "Not marked as understood yet", mark_read: "I understand this — mark as understood",
    src_breadcrumb: "Author's own words", src_narrative: "Generated interpretation (not the author's words)", of_commit: "Commit", full_text: "Full text",
    files: "Files changed", upstream: "Earlier commits touching the same files", downstream: "Later commits touching the same files",
    relation: "Basis: both commits touched the same files; this is not proven causation.",
    load_src: "Read commit message and diff", load_later: "Read what the later commit changed", loading: "Loading…", load_fail: "Could not load", copy: "Copy full SHA", copied: "Copied",
    my_notes: "My notes", note_ph: "What you understand or want to remember about this node (stays on this machine)", tags_ph: "Tags, comma separated",
    hide: "Hide this node on the graph", save: "Save", saved: "Saved", save_fail: "Could not save", unpin: "Release pinned position",
    link: "Link to another node", link_pick: "Click another node to finish the link (Esc to cancel)", links: "Manual links", remove: "Remove",
    plans: "Planned directions", plan_ph: "What you intend to do next", dir_ph: "Direction name (same name, same colour)", add_plan: "Add plan",
    plan_open: "Planned", plan_done: "Implemented", mark_done: "Mark as implemented", done_pick: "Click the commit that implemented it (Esc to cancel)",
    reopen: "Back to planned", done_by: "Implemented by", plan_from: "Extends from this commit",
    e_file: "Two commits touched the same files", e_link: "Manual link", e_plan: "A plan and the commit that implemented it", shared: "Files both touched", earlier: "Earlier commit", later: "Later commit",
    readonly: "This static page is read-only. Run codetalk graph --serve to add notes, mark commits understood, add plans and draw links.",
    expand_run: "Unfold this run of commits without notes", commits_n: " commits",
    ct_feat: "feature", ct_fix: "fix", ct_docs: "docs", ct_refactor: "refactor", ct_test: "test", ct_chore: "chore", ct_perf: "perf", ct_ci: "ci", ct_build: "build", ct_style: "style", ct_revert: "revert"
  }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang"); return s === "en" ? "en" : "zh"; } catch(e){ return "zh"; } })();
var TITLE_PREFIX = (function(){ var h = document.querySelector("h1");
  return h && h.firstChild ? (h.firstChild.nodeValue || "") : ""; })();
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function clip(s, units){                       // 按视觉宽度截断:CJK 算 2 个单位
  var w = 0, out = '';
  for(var i=0;i<s.length;i++){ w += s.charCodeAt(i) > 0x2e7f ? 2 : 1; if(w > units) return out + '…'; out += s.charAt(i); }
  return out;
}
function summary(text){                        // 卡片只放大致摘要:取第一句,全文在详情面板
  var m = String(text).split(/[。;;!?!?]|——|\. | — | -- /)[0].trim();
  return m || String(text);
}
function commitType(subject){                  // "fix(x): 做了什么" → {tag:"修复", rest:"做了什么"}
  var m = /^(\w+)(\([^)]*\))?!?:\s*(.+)/.exec(subject || '');
  var tag = m && I18N.zh['ct_' + m[1].toLowerCase()] ? t('ct_' + m[1].toLowerCase()) : '';
  return {tag: tag, rest: tag ? m[3] : (subject || '')};
}
// ---- 数据索引 ----
var svg = document.getElementById('svg'), panel = document.getElementById('panel');
var ANN = DATA.annotations || {};
var TRUNK = DATA.trunk || [], LEAVES = DATA.leaves || [], HEAD = DATA.head || '';
var REVIEWED = {}; (DATA.reviewed || []).forEach(function(s){ REVIEWED[s] = 1; });
var BYID = {}, LEAVES_OF = {}, PLANS = [];
TRUNK.forEach(function(c){ c.type = 'commit'; BYID[c.id] = c; LEAVES_OF[c.id] = []; });
LEAVES.forEach(function(l){ l.type = 'leaf'; BYID[l.id] = l; if(LEAVES_OF[l.commit]) LEAVES_OF[l.commit].push(l); });
var SHOW = {decision:true, rejected:true, watch:true, plan:true, plain:true, hidden:false};
var EXPANDED = {}, RUN_OF = {}, POS = {}, FULL = {x0:0, y0:0, x1:0, y1:0};
var sel = null, selEdge = null, hits = null, DRAG = null, pick = null;
var LW = 236, LH = 50, STEP = 62, BASE = 76, PAD = 60, FOLD = 6;
var PALETTE = ['#7a5cc4', '#1f8a9c', '#c2620c', '#b0447e', '#3f7fd0', '#6f8f1f'];
function ann(id){ return ANN[id] || {}; }
function hiddenNode(id){ return !SHOW.hidden && ann(id).hidden; }
function isNoted(c){ return LEAVES_OF[c.id].length > 0; }
function loadPlans(){                          // 计划方向是本机批注:plan:<commit>:<id> → 节点
  PLANS.forEach(function(p){ delete BYID[p.id]; });
  PLANS = Object.keys(ANN).filter(function(k){ return k.indexOf('plan:') === 0 && BYID[k.split(':')[1]]; }).sort().map(function(k){
    var a = ANN[k]; return {id: k, type: 'plan', commit: k.split(':')[1], text: a.text || '', dir: a.dir || '', done: a.done || ''};
  });
  PLANS.forEach(function(p){ BYID[p.id] = p; });
}
function dirColor(dir){                        // 同名方向同色
  var dirs = []; PLANS.forEach(function(p){ if(dirs.indexOf(p.dir) < 0) dirs.push(p.dir); });
  return PALETTE[Math.max(0, dirs.indexOf(dir)) % PALETTE.length];
}
function plansOf(cid){ return SHOW.plan ? PLANS.filter(function(p){ return p.commit === cid; }) : []; }
function visibleLeaves(cid){
  return LEAVES_OF[cid].filter(function(l){ return SHOW[l.kind] && !hiddenNode(l.id); });
}
function userLinks(){                          // [{key,a,b}] 手动连线
  return Object.keys(ANN).filter(function(k){ return k.indexOf('link:') === 0; }).map(function(k){
    var p = k.slice(5).split('>'); return {key: k, a: p[0], b: p[1]}; });
}
// ---- 版面:确定性的「主干 + 枝叶」,不做力导向 ----
function layout(){
  loadPlans(); POS = {}; RUN_OF = {};
  var x = PAD, run = [], up = 0, down = 0;
  function flush(){
    if(!run.length) return;
    var key = run[0].id;
    run.forEach(function(c){ RUN_OF[c.id] = key; });
    if(run.length > FOLD && !EXPANDED[key]){
      POS['run:' + key] = {x: x + 30, y: 0, run: run.length}; x += 78;
    } else if(SHOW.plain){
      run.forEach(function(c){ POS[c.id] = {x: x + 9, y: 0, plain: true}; x += 18; });
      x += 10;
    }
    run = [];
  }
  TRUNK.forEach(function(c){
    if(hiddenNode(c.id)) return;
    var lv = visibleLeaves(c.id), pl = plansOf(c.id), a = ann(c.id);
    if(!lv.length && !pl.length && !a.note && !(a.tags || []).length && !a.pin && c.id !== HEAD){ run.push(c); return; }
    flush();
    x += 26; POS[c.id] = {x: x, y: 0};
    var u = 0, d = 0;
    lv.forEach(function(l){
      var isUp = l.kind === 'decision', k = isUp ? u++ : d++;
      POS[l.id] = {x: x + 20, y: (isUp ? -1 : 1) * (BASE + k * STEP), leaf: true};
    });
    pl.forEach(function(p){ POS[p.id] = {x: x + 44, y: -(BASE + (u++) * STEP), leaf: true}; });  // 计划向前上方延伸
    up = Math.max(up, u); down = Math.max(down, d);
    x += LW + (pl.length ? 70 : 46);
  });
  flush();
  Object.keys(POS).forEach(function(id){        // 用户固定的位置覆盖自动版面
    var p = ann(id).pin; if(p){ POS[id].x = p.x; POS[id].y = p.y; }
  });
  if(DRAG && POS[DRAG.id]){ POS[DRAG.id].x = DRAG.x; POS[DRAG.id].y = DRAG.y; }
  FULL = {x0: 0, x1: x + PAD, y0: -(BASE + up * STEP + 40), y1: BASE + down * STEP + 40};
}
function sharedFiles(a, b){ return a.files.filter(function(f){ return b.files.indexOf(f) >= 0; }); }
function neighbours(cid, later){               // 改到相同文件的提交:之后最近 8 个 / 之前最近 5 个
  var c = BYID[cid], out = [];
  if(!c || !c.files.length) return out;
  TRUNK.forEach(function(o){ if((later ? o.ts > c.ts : o.ts < c.ts) && sharedFiles(c, o).length) out.push(o); });
  return later ? out.slice(0, 8) : out.slice(-5);
}
function related(id){                          // 悬停时一起高亮的节点
  var n = BYID[id], out = {}; out[id] = 1;
  if(n && n.type === 'commit'){ LEAVES_OF[id].forEach(function(l){ out[l.id] = 1; }); PLANS.forEach(function(p){ if(p.commit === id || p.done === id) out[p.id] = 1; }); }
  if(n && n.type !== 'commit'){ out[n.commit] = 1; if(n.done) out[n.done] = 1; }
  userLinks().forEach(function(l){ if(l.a === id) out[l.b] = 1; if(l.b === id) out[l.a] = 1; });
  return out;
}
