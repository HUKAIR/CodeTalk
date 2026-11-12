
// ---- i18n:zh/en 字典 + 切换(零外联,复用 localStorage;数据仍不出本机)----
var I18N = {
  zh: {
    title_suffix: "时光轴", header_timeline: "时光轴",
    ago_today: "今天", ago_days_suffix: " 天前",
    tag_due: "待验证", tag_notdue: "未到期",
    empty_commits: "还没有任何 commit。",
    intro_p1: "从", intro_recent: "最近",
    intro_p2: "往下,是这个项目一步步长成现在的样子。共 ",
    intro_p3: " 枚 commit · 已叙事 ", intro_p4: " · 待验证的担心 ",
    intro_p5: " 处。点任意一条展开它当时的决策与推导。",
    badge_decisions: " 决策", badge_toverify: " 待验证", badge_capsules: " 胶囊",
    prev_unnarrated: "尚未叙事 — 终端跑 codetalk digest",
    lbl_what: "改了什么 — What", lbl_why: "为什么 — Why",
    lbl_decisions: "关键决策 — Decisions", lbl_open: "待验证 — Open",
    lbl_capsule: "时间胶囊 — Capsule",
    body_unnarrated: "这枚 commit 尚未被叙事。回终端跑 codetalk digest。",
    btn_overthought: "想多了", btn_resolved: "已解决", btn_worried: "还在担心", btn_forgot: "忘记了",
    due_recorded: "已记录:", due_reanswer: "改答 ↺",
    due_head_p1: "■ 到期待验证的预测 — ", due_head_p2: " 枚",
    due_worried: "你担心:", q_open: "「", q_close: "」",
    due_readonly: "只读 · 跑 codetalk tunnel --serve 可回写答案",
    writeback_fail: "写回失败,请重试",
    foot_p1: "已读 ", foot_p2: " 段叙事",
    foot_serve: " · serve 模式:回答即时写回 cache.db", foot_readonly: " · 只读模式"
  },
  en: {
    title_suffix: "Timeline", header_timeline: "Timeline",
    ago_today: "today", ago_days_suffix: " days ago",
    tag_due: "Due", tag_notdue: "Not yet due",
    empty_commits: "No commits yet.",
    intro_p1: "From ", intro_recent: "most recent",
    intro_p2: " down, watch this project grow into what it is today. ",
    intro_p3: " commits · ", intro_p4: " narrated · ",
    intro_p5: " open concerns to verify. Click any entry to expand its decisions and reasoning at the time.",
    badge_decisions: " decisions", badge_toverify: " to verify", badge_capsules: " capsules",
    prev_unnarrated: "Not narrated yet — run codetalk digest in the terminal",
    lbl_what: "What", lbl_why: "Why",
    lbl_decisions: "Decisions", lbl_open: "Open",
    lbl_capsule: "Capsule",
    body_unnarrated: "This commit hasn't been narrated yet. Run codetalk digest in the terminal.",
    btn_overthought: "Overthought it", btn_resolved: "Resolved", btn_worried: "Still worried", btn_forgot: "Forgot",
    due_recorded: "Recorded: ", due_reanswer: "Change answer ↺",
    due_head_p1: "■ Predictions due for verification — ", due_head_p2: "",
    due_worried: " you worried: ", q_open: "“", q_close: "”",
    due_readonly: "Read-only · run codetalk tunnel --serve to write answers back",
    writeback_fail: "Write-back failed, please retry",
    foot_p1: "Read ", foot_p2: " narratives",
    foot_serve: " · serve mode: answers written back to cache.db instantly", foot_readonly: " · read-only mode"
  }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang");
  if (s === "zh" || s === "en") return s;
  return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en";
} catch(e){ return "zh"; } })();
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
var OUTCOMES = [["btn_overthought","想多了"],["btn_resolved","已解决"],["btn_worried","还在担心"]];
// 显示映射含后端第 4 值「忘记了」(仅经 vault markdown 手勾产生,前端不作按钮);未知则原样
var OUTLABELS = OUTCOMES.concat([["btn_forgot","忘记了"]]);
function outLabel(canon){                 // 规范中文 outcome → 当前语言显示
  for (var i = 0; i < OUTLABELS.length; i++) if (OUTLABELS[i][1] === canon) return t(OUTLABELS[i][0]);
  return canon;
}
var PROJECT = "$project";
function applyLang(){
  document.documentElement.lang = LANG;
  document.title = PROJECT + " — " + t("title_suffix");
  document.querySelectorAll("[data-i18n]").forEach(function(el){ el.textContent = t(el.getAttribute("data-i18n")); });
  var lb = document.getElementById("langbtn"); if (lb) lb.textContent = LANG === "zh" ? "EN" : "中文";
  if (window.onLangChange) window.onLangChange();     // 让动态内容(时间轴/胶囊)重渲染
}
function toggleLang(){ LANG = LANG === "zh" ? "en" : "zh";
  try { localStorage.setItem("codetalk.lang", LANG); } catch(e){}
  applyLang(); }

var DATA = $data;          // _payload:最新在前
var SERVE = $serve;        // --serve:回答/回看写回 cache;file:// 只读
var VKEY = "codetalk.visited.$project";

function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function store(v){
  try {
    if (v === undefined) return JSON.parse(localStorage.getItem(VKEY)) || {};
    localStorage.setItem(VKEY, JSON.stringify(v));
  } catch (e) { return {}; }
}
function post(path, payload){
  if (!SERVE) return Promise.resolve(false);
  return fetch(path, { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(projectPayload(payload)) })
    .then(function(r){ return r.ok; })
    .catch(function(){ return false; });
}
// 键盘可达:Enter / Space 激活;Space 阻止默认滚屏。给可点击非按钮元素接键。
function onActivate(el, fn){
  el.addEventListener("click", fn);
  el.addEventListener("keydown", function(e){
    if (e.key === "Enter" || e.key === " "){ e.preventDefault(); fn(e); }
  });
}
var visited = store();

function agoText(n){
  return n === 0 ? t("ago_today") : n + t("ago_days_suffix");
}
function capTag(cap){
  if (cap.outcome) return '<span class="tag done">✓ ' + esc(outLabel(cap.outcome)) + '</span>';
  if (cap.opened) return '<span class="tag due">' + t("tag_due") + '</span>';
  return '<span class="tag">' + t("tag_notdue") + '</span>';
}

// ---- 主体:按天分组的线性时间轴 ----
function renderTimeline(){
  var app = document.getElementById("app");
  if (!DATA.length){ app.innerHTML = '<p class="empty">' + esc(t("empty_commits")) + '</p>'; return; }
  var narrated = DATA.filter(function(c){ return c.what; }).length;
  var openRisks = DATA.reduce(function(a, c){ return a + c.risks.length; }, 0);
  var html = '<p class="intro">' + esc(t("intro_p1")) + '<b>' + esc(t("intro_recent")) + '</b>'
    + esc(t("intro_p2")) + '<b>' + DATA.length + '</b>' + esc(t("intro_p3"))
    + '<b>' + narrated + '</b>' + esc(t("intro_p4"))
    + '<b>' + openRisks + '</b>' + esc(t("intro_p5")) + '</p>';
  html += dueCapsulesHtml();
  var lastDay = null;
  DATA.forEach(function(c, i){
    if (c.day !== lastDay){
      lastDay = c.day;
      html += '<div class="day">' + c.day + ' · ' + agoText(c.days_ago) + '</div>';
    }
    html += rowHtml(c, i);
  });
  app.innerHTML = html;
  DATA.forEach(function(c, i){
    var head = document.getElementById("h" + i);
    onActivate(head, function(){ toggleRow(c, i); });
  });
  wireDueButtons();
  renderFooter();
}

function rowHtml(c, i){
  var cls = "row" + (visited[c.sha] ? " read" : "") + (c.risks.length ? " risky" : "");
  var badges = '<span class="d">' + c.decisions.length + esc(t("badge_decisions")) + '</span>'
    + (c.risks.length ? ' · <span class="r">' + c.risks.length + esc(t("badge_toverify")) + '</span>' : "")
    + ((c.capsules || []).length ? ' · <span class="c">' + c.capsules.length + esc(t("badge_capsules")) + '</span>' : "");
  var prev = c.what || t("prev_unnarrated");
  return '<div class="' + cls + '" id="r' + i + '">'
    + '<div class="head" id="h' + i + '" role="button" tabindex="0"'
    + ' aria-expanded="false" aria-controls="b' + i + '"><div class="top">'
    + '<span class="sha">' + c.sha + '</span>'
    + '<span class="subj">' + esc(c.subject) + '</span>'
    + '<span class="badges">' + badges + '</span></div>'
    + '<div class="prev">' + esc(prev) + '</div></div>'
    + '<div class="body" id="b' + i + '"></div></div>';
}

function bodyHtml(c){
  var h = '<p class="ro">'+(LANG === "zh" ? "以下为缓存解释，非原始记录。核对原始提交：" : "Cached interpretation, not source records. Inspect the original commit: ")+ '<code>git show '+esc(c.sha)+'</code></p>';
  if (c.what) h += '<div class="lbl">' + esc(t("lbl_what")) + '</div><p>' + esc(c.what) + '</p>';
  if (c.why) h += '<div class="lbl">' + esc(t("lbl_why")) + '</div><p>' + esc(c.why) + '</p>';
  if (c.decisions.length){
    h += '<div class="lbl">' + esc(t("lbl_decisions")) + '</div><ol>';
    c.decisions.forEach(function(d){ h += '<li>' + esc(d) + '</li>'; });
    h += '</ol>';
  }
  if (c.risks.length){
    h += '<div class="lbl">' + esc(t("lbl_open")) + '</div><ol class="risks">';
    c.risks.forEach(function(r){ h += '<li>' + esc(r) + '</li>'; });
    h += '</ol>';
  }
  if ((c.capsules || []).length){
    h += '<div class="lbl">' + esc(t("lbl_capsule")) + '</div>';
    c.capsules.forEach(function(cap){
      h += '<div class="cap">' + capTag(cap) + esc(cap.risk) + '</div>';
    });
  }
  if (!c.what && !c.why)
    h += '<p class="empty">' + esc(t("body_unnarrated")) + '</p>';
  return h;
}

function toggleRow(c, i){
  var row = document.getElementById("r" + i);
  var open = row.classList.toggle("open");
  document.getElementById("h" + i).setAttribute("aria-expanded",
    open ? "true" : "false");
  if (!open) return;
  var body = document.getElementById("b" + i);
  if (!body.innerHTML) body.innerHTML = bodyHtml(c);
  if (!visited[c.sha]){                 // 首次展开:记回看(喂理解债)
    visited[c.sha] = 1; store(visited);
    row.classList.add("read");
    post("/reviewed", { sha: c.sha });
  }
}

// ---- 待验证胶囊:置顶 callout,serve 模式可现场回答写回 cache ----
function dueCaps(){
  var out = [];
  DATA.forEach(function(c){
    (c.capsules || []).forEach(function(cap){
      if (cap.opened && !cap.outcome) out.push({ cap: cap, host: c });
    });
  });
  return out;
}
function dueBtnsHtml(k){
  var h = '<div class="btns">';
  OUTCOMES.forEach(function(o){            // data-out 恒为规范中文(稳定写回键),标签按语言译
    h += '<button class="btn" data-k="' + k + '" data-out="' + esc(o[1]) + '"'
      + (SERVE ? "" : " disabled") + '>' + esc(t(o[0])) + '</button>';
  });
  return h + '</div>';
}
function dueDoneHtml(out){
  return '<span class="ago">' + esc(t("due_recorded")) + '</span>'
    + '<span style="color:var(--ok)">' + esc(outLabel(out)) + '</span>'
    + ' <span class="reanswer" role="button" tabindex="0">' + esc(t("due_reanswer")) + '</span>';
}
function dueCapsulesHtml(){
  var due = dueCaps();
  if (!due.length) return "";
  var h = '<div class="due"><h4>' + esc(t("due_head_p1")) + due.length + esc(t("due_head_p2")) + '</h4>';
  due.forEach(function(d, k){
    h += '<div class="q" data-k="' + k + '"><span class="ago">'
      + esc(agoText(d.host.days_ago)) + esc(t("due_worried")) + '</span>'
      + esc(t("q_open")) + esc(d.cap.risk) + esc(t("q_close"))
      + '<div class="ans" id="due-ans-' + k + '">' + dueBtnsHtml(k) + '</div></div>';
  });
  if (!SERVE) h += '<div class="ro">' + esc(t("due_readonly")) + '</div>';
  h += '</div>';
  return h;
}
// 答案区在「选项组」与「已记录 + 改答↺」两态间切换;改答只是再 post 一次新 outcome
// (set_capsule_outcome 是 UPDATE,后端天然支持改写)。
function wireDueAns(k, due){
  var ans = document.getElementById("due-ans-" + k);
  if (!ans) return;
  ans.querySelectorAll(".btn").forEach(function(b){
    if (!SERVE) return;
    b.addEventListener("click", function(){
      answerDue(k, due, b.getAttribute("data-out"));
    });
  });
  var re = ans.querySelector(".reanswer");
  if (re) onActivate(re, function(){
    ans.innerHTML = dueBtnsHtml(k); wireDueAns(k, due); });
}
function answerDue(k, due, out){
  // res.ok 确认写回后才落地「已记录」,失败保留选项 + 提示重试,杜绝 UI 假成功。
  var ans = document.getElementById("due-ans-" + k), d = due[k];
  post("/capsule", { capsule_id: d.cap.id, outcome: out }).then(function(ok){
    if (ok){ d.cap.outcome = out; ans.innerHTML = dueDoneHtml(out); wireDueAns(k, due); }
    else ans.insertAdjacentHTML("beforeend",
      '<div class="ro" style="color:var(--warn)">' + esc(t("writeback_fail")) + '</div>');
  });
}
