
var DATA = $data;
function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
// ---- i18n:zh/en 字典 + 切换(零外联,复用 localStorage;数据仍不出本机)----
// 注意:{n}/{m}/{g} 是占位符,由 JS 用 .replace 填;此文件走 Template.substitute,正文勿引入裸美元符
var I18N = {
  zh: {
    course_label: "演进课程", grew: "这个项目怎么长成的", chapters_lbl: "章节 · Chapters",
    degraded_head: "未智能编排",
    degraded_body: "未设置 API key 或调用失败,本课程按时间顺序朴素分章、无测验。设置 key 后重跑可得完整课程。",
    ch_num: "第 {n} 章 / 共 {m}", decision_k: "生成解释 · 决定摘要",
    diff_na: "(diff 不可用)", no_narrative: "尚未叙事 — 跑 codetalk digest",
    risks_summary: "潜在风险 / 未闭环", quiz_h: "场景测验 — Quiz {n}", hint_prefix: "提示:",
    footer: "本机阅读 · 解释不代替原始记录 · {n} 章 · 生成 {g}"
  },
  en: {
    course_label: "Evolution Course", grew: "How this project grew", chapters_lbl: "Chapters",
    degraded_head: "No smart orchestration",
    degraded_body: "No API key set or the call failed; this course is split into chapters by time only, with no quizzes. Set a key and re-run for the full course.",
    ch_num: "Chapter {n} / {m}", decision_k: "Generated interpretation · decision summary",
    diff_na: "(diff unavailable)", no_narrative: "Not yet narrated — run codetalk digest",
    risks_summary: "Potential risks / open loops", quiz_h: "Scenario quiz — Quiz {n}", hint_prefix: "Hint: ",
    footer: "Local reading · interpretations do not replace source records · {n} chapters · generated {g}"
  }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang");
  if (s === "zh" || s === "en") return s;
  return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en";
} catch(e){ return "zh"; } })();
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
var main = document.getElementById("main"), toc = document.getElementById("toc");
var PROJECT = (document.getElementById("proj") || {}).textContent || "";
var GENERATED = (document.getElementById("gen") || {}).textContent || "";
var secs = [], tocLinks = [];
function renderCourse(){
  var old = document.querySelector(".wrap .degraded"); if (old) old.remove();
  main.innerHTML = ""; toc.innerHTML = "";
  if (DATA.degraded){
    var d = document.createElement("div");
    d.className = "degraded";
    d.innerHTML = "<b>" + esc(t("degraded_head")) + "</b> · " + esc(t("degraded_body"));
    document.querySelector(".wrap").insertBefore(d, document.querySelector("nav"));
  }
  (DATA.chapters || []).forEach(function(ch, ci){
    var sec = document.createElement("section");
    sec.className = "ch"; sec.id = "ch" + ci;
    var html = '<div class="num">'
      + esc(t("ch_num").replace("{n}", ci + 1).replace("{m}", DATA.chapters.length))
      + '</div><h2>' + esc(ch.title) + '</h2>';
    if (ch.intro)  // 当时的决定:原分析直接显示(保留)
      html += '<div class="intro"><span class="k">' + esc(t("decision_k")) + '</span>'
        + esc(ch.intro) + '</div>';
    if (ch.plain)  // 大白话:另加的可展开层,不藏原分析
      html += '<details class="bdh"><summary></summary><div class="body">'
        + esc(ch.plain) + '</div></details>';
    (ch.blocks || []).forEach(function(b){
      var badge = b.type ? '<span class="badge ' + esc(b.type) + '">'
        + esc(b.type) + '</span>' : '';
      html += '<div class="pair"><div class="ph">' + badge + '<b>' + esc(b.sha)
        + '</b> · ' + esc(b.subject) + '</div><div class="cols"><pre>'
        + (b.diff ? esc(b.diff) : esc(t("diff_na")))
        + '</pre><div class="say"><div class="e">'  // 代码讲解直接显示(保留)
        + esc(b.what || t("no_narrative"))
        + '</div></div></div></div>';
    });
    var risks = ch.risks || [], loops = ch.open_loops || [];
    if (risks.length || loops.length){
      html += '<details class="lapse"><summary>' + esc(t("risks_summary")) + '</summary><ul>';
      risks.forEach(function(r){ html += '<li>' + esc(r) + '</li>'; });
      loops.forEach(function(l){ html += '<li class="loop">' + esc(l) + '</li>'; });
      html += '</ul></details>';
    }
    (ch.quiz || []).forEach(function(qz, qi){
      var opts = qz.options || [];
      // quiz answer 越界校验:LLM 给错索引时钳到范围,避免该题永远答不对
      var ans = Number.isInteger(qz.answer) ? qz.answer : 0;
      if (ans < 0 || ans >= opts.length) ans = 0;
      html += '<div class="quiz" data-ans="' + ans + '"><div class="qh">'
        + esc(t("quiz_h").replace("{n}", qi + 1))
        + '</div><p class="q">' + esc(qz.q) + '</p>';
      opts.forEach(function(o, oi){
        html += '<button class="opt" data-i="' + oi + '">' + esc(o) + '</button>';
      });
      html += '<div class="hint">' + esc(t("hint_prefix")) + esc(qz.hint) + '</div></div>';
    });
    sec.innerHTML = html;
    main.appendChild(sec);
    var a = document.createElement("a");
    a.href = "#ch" + ci; a.id = "toc" + ci;
    a.innerHTML = '<span class="n">' + (ci + 1 < 10 ? "0" : "") + (ci + 1)
      + '</span>' + esc(ch.title);
    toc.appendChild(a);
  });
  secs = [].slice.call(main.children);
  tocLinks = [].slice.call(toc.children);
}
function renderFooter(){
  document.getElementById("foot").textContent =
    t("footer").replace("{n}", (DATA.chapters || []).length).replace("{g}", GENERATED);
}
function applyLang(){
  document.documentElement.lang = LANG;
  document.title = PROJECT + " — " + t("course_label");
  document.querySelectorAll("[data-i18n]").forEach(function(el){
    el.textContent = t(el.getAttribute("data-i18n")); });
  var lb = document.getElementById("langbtn"); if (lb) lb.textContent = LANG === "zh" ? "EN" : "中文";
  renderCourse(); renderFooter();
  if (window.onLangChange) window.onLangChange();  // 重渲染后刷新滚动进度/TOC 高亮
}
function toggleLang(){ LANG = LANG === "zh" ? "en" : "zh";
  try { localStorage.setItem("codetalk.lang", LANG); } catch(e){}
  applyLang(); }
// 测验交互:点选项判对错,错给提示;答对锁定
main.addEventListener("click", function(e){
  var btn = e.target.closest(".opt");
  if (!btn) return;
  var quiz = btn.closest(".quiz");
  if (quiz.dataset.done) return;
  var ans = parseInt(quiz.dataset.ans, 10);
  if (parseInt(btn.dataset.i, 10) === ans){
    btn.classList.add("ok"); quiz.dataset.done = "1";
  } else {
    btn.classList.add("bad");
  }
  quiz.querySelector(".hint").classList.add("show");
});
// 进度条 + 目录高亮(secs/tocLinks 由 renderCourse 填,语言切换重渲染后仍指向最新)
function onScroll(){
  var h = document.documentElement;
  var p = h.scrollTop / (h.scrollHeight - h.clientHeight || 1);
  document.getElementById("bar").style.width = (p * 100).toFixed(1) + "%";
  var cur = 0;
  secs.forEach(function(s, i){ if (s.getBoundingClientRect().top < 120) cur = i; });
  tocLinks.forEach(function(a, i){ a.classList.toggle("on", i === cur); });
}
addEventListener("scroll", onScroll, { passive: true });
document.addEventListener("keydown", function(e){     // j/k 跳下一/上一章(不抢方向键滚动)
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  var tag = e.target && e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (e.key !== "j" && e.key !== "k") return;
  var cur = 0;
  secs.forEach(function(s, i){ if (s.getBoundingClientRect().top < 120) cur = i; });
  var nx = Math.max(0, Math.min(secs.length - 1, e.key === "j" ? cur + 1 : cur - 1));
  if (secs[nx]){ e.preventDefault();
    secs[nx].scrollIntoView({ behavior: "auto", block: "start" }); }
});
// 语言切换:静态元素 + 章节/测验/页脚由 applyLang→renderCourse/renderFooter 换,
// 重渲染后经 onLangChange 刷新滚动进度条 + TOC 高亮
window.onLangChange = onScroll;
var _lb = document.getElementById("langbtn");
if (_lb) _lb.addEventListener("click", toggleLang);
applyLang();
