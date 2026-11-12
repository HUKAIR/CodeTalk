
// ---- i18n:zh/en 字典 + 切换(静态字典零外联,复用 localStorage)----
var I18N = {
  zh: {
    title: "CodeTalk · 接地对话", tagline: "接地对话 · 本地优先 · 模型调用按配置",
    nav_console: "控制台", nav_tunnel: "时光轴", nav_graph: "决策图", nav_course: "演进课程",
    latest:"回到最新", close_files:"关闭文件", return_reading:"返回阅读位置", original:"来源记录", retrieved:"本地检索结果", generated:"生成解释（非证据）", files_btn: "文件 ▸", send: "问", you: "你", searching: "…接地检索中",
    hint: "问「这段代码当初为什么这么写」——答案接地到真实 commit / 决策 / 会话原话;无 key 或 --no-llm 时降级为零-LLM 接地罗列(不出网)。",
    q_ph: "例:为什么把重试从装饰器改成显式循环?(可带 文件:行)",
    ft_empty: "无文件或非 git 仓。", ft_head: "点变更文件 → 接地追问",
    ft_prefix: "这个文件当初为什么改:", suggest_prefix: "💡 Tab 填入:",
    degraded: "零-LLM 接地(未调模型)", copy: "复制", copied: "已复制", copy_fail: "复制失败",
    hl_legend: "高亮=逐字源自来源;其余为综合,点引用核验",
    loading_commit: "读取 commit…", commit_fail: "打不开该 commit(可能不在本地仓)",
    discuss: "讨论·", no_evidence: "(无证据)",
    diff_title: "看这枚 commit 的真实改动(git show,零 LLM)",
    err: "出错了(后端没起来?查 codetalk web 终端)",
    suggest: ["为什么这段代码当初要这么写?", "这里的关键决策是什么,依据什么?",
      "为什么从 X 改成 Y?", "这段有哪些待验证的风险?",
      "codetalk/llm.py:43-56 当初为什么这么设计?"]
  },
  en: {
    title: "CodeTalk · Grounded chat", tagline: "Grounded chat · local-first · model calls follow config",
    nav_console: "Console", nav_tunnel: "Timeline", nav_graph: "Graph", nav_course: "Course",
    latest:"Back to latest", close_files:"Close files", return_reading:"Return to reading", original:"Source records", retrieved:"Local retrieval results", generated:"Generated interpretation (not evidence)", files_btn: "Files ▸", send: "Ask", you: "You", searching: "…grounding retrieval",
    hint: "Ask \"why was this code written this way\" — answers are grounded in real commits / decisions / session transcripts; without a key or with --no-llm it degrades to a zero-LLM evidence list (no egress).",
    q_ph: "e.g. why was retry moved from a decorator to an explicit loop? (optional file:line)",
    ft_empty: "No files, or not a git repo.", ft_head: "Click a changed file → grounded follow-up",
    ft_prefix: "Why was this file changed: ", suggest_prefix: "💡 Tab to fill: ",
    degraded: "Zero-LLM grounding (no model call)", copy: "Copy", copied: "Copied", copy_fail: "Copy failed",
    hl_legend: "Highlight = verbatim from source; the rest is synthesized — click a citation to verify",
    loading_commit: "Loading commit…", commit_fail: "Can't open that commit (maybe not in the local repo)",
    discuss: "chat·", no_evidence: "(no evidence)",
    diff_title: "See this commit's real change (git show, zero-LLM)",
    err: "Error (backend down? check the codetalk web terminal)",
    suggest: ["Why was this code written this way?", "What's the key decision here, and on what basis?",
      "Why change from X to Y?", "What risks here are still unverified?",
      "Why was codetalk/llm.py:43-56 designed this way?"]
  }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang");
  if (s === "zh" || s === "en") return s;
  return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en";
} catch(e){ return "zh"; } })();
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
function applyLang(){
  document.documentElement.lang = LANG;
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach(function(el){ el.textContent = t(el.getAttribute("data-i18n")); });
  document.querySelectorAll("[data-i18n-ph]").forEach(function(el){ el.placeholder = t(el.getAttribute("data-i18n-ph")); });
  var lb = document.getElementById("langbtn"); if (lb) lb.textContent = LANG === "zh" ? "EN" : "中文";
  if (window.onLangChange) window.onLangChange();     // 让动态内容(建议/文件树)重渲染
}
function toggleLang(){ LANG = LANG === "zh" ? "en" : "zh";
  try { localStorage.setItem("codetalk.lang", LANG); } catch(e){}
  applyLang(); }

var convId = "web-" + Date.now();
var turn = 0;
var TREE = $tree_data;
var pendingTarget = null;
var log = document.getElementById("log");
// 自动滚到最新:仅在用户已在底部时(上滚阅读历史时不打断)
function atBottom(){ return (window.innerHeight + window.scrollY)
  >= document.documentElement.scrollHeight - 80; }
function scrollEnd(){ window.scrollTo(0, document.documentElement.scrollHeight); document.getElementById("latest").hidden = true; }
document.getElementById("latest").onclick = scrollEnd;
window.addEventListener("scroll", function(){ document.getElementById("latest").hidden = atBottom() || !log.children.length; }, {passive:true});
function setDrawer(open, restore){
  var dr = document.getElementById("ftdrawer"), trigger = document.getElementById("filesbtn");
  dr.classList.toggle("open", open); dr.inert = !open; dr.setAttribute("aria-hidden", String(!open)); trigger.setAttribute("aria-expanded", String(open));
  if (open) dr.querySelector("button").focus({preventScroll:true}); else if (restore) trigger.focus({preventScroll:true});
}

function renderFiletree(){
  var T = TREE && TREE.nodes;
  var dr = document.getElementById("ftdrawer");
  if (!T || !T.children || !T.children.length){
    dr.innerHTML = '<button type="button" class="drawer-close">'+esc(t("close_files"))+'</button><p class="hint">'+esc(t("ft_empty"))+'</p>'; dr.querySelector('button').onclick = function(){setDrawer(false,true);}; return; }
  function mark(code){ return code ? code.replace(/ /g,"").charAt(0) : ""; }
  function nodeHtml(node, depth){
    var pad = ' style="padding-left:'+(depth*14)+'px"';
    if (node.type === "file"){
      var m = mark(node.code);
      var cls = "ftf" + (m ? " st-"+esc(m) : "")
        + (node.code && node.code.indexOf("D")>=0 ? " del" : "");
      var badge = node.label ? ' <span class="stb">'+esc(node.label)+'</span>' : "";
      return '<div class="'+cls+'" data-path="'+esc(node.path)+'" role="button"'
        + ' tabindex="0"'+(node.label?' title="'+esc(node.label)+'"':"")+pad+'>'
        + esc(node.name)+badge+'</div>';
    }
    var kids = node.children.map(function(c){ return nodeHtml(c, depth+1); }).join("");
    return '<details'+(node.changed?" open":"")+'><summary'+pad+'>'+esc(node.name)
      + '</summary>'+kids+'</details>';
  }
  dr.innerHTML = '<button type="button" class="drawer-close">'+esc(t("close_files"))+'</button><div class="hint">'+esc(t("ft_head"))+'</div>'
    + T.children.map(function(c){ return nodeHtml(c, 0); }).join("");
  dr.querySelector(".drawer-close").onclick = function(){ setDrawer(false, true); };
  dr.querySelectorAll(".ftf").forEach(function(el){
    function act(){
      var p = el.getAttribute("data-path");
      document.getElementById("q").value = t("ft_prefix") + p;
      pendingTarget = p;
      document.getElementById("q").focus();
      setDrawer(false, false);
    }
    el.addEventListener("click", act);
    el.addEventListener("keydown", function(e){
      if (e.key==="Enter" || e.key===" "){ e.preventDefault(); act(); } });
  });
}
document.getElementById("filesbtn").addEventListener("click", function(){
  setDrawer(!document.getElementById("ftdrawer").classList.contains("open"), true); });
document.addEventListener("keydown", function(e){      // Esc 关文件抽屉
  if (e.key === "Escape"){ var dr = document.getElementById("ftdrawer");
    if (dr && dr.classList.contains("open")) setDrawer(false, true); } });
renderFiletree();

// 输入框为空时按 Tab → 填入当前建议问题并切下一条(无外联,纯本地;建议随语言切换)
var sIdx = 0, qEl = document.getElementById("q"), sHint = document.getElementById("shint");
function showSuggest(){ var sg = t("suggest"); sHint.textContent = t("suggest_prefix") + sg[sIdx % sg.length]; }
showSuggest();
qEl.addEventListener("keydown", function(e){
  // Enter 发送、Shift+Enter 换行;IME 合成中(中文选词)不发,避免误触
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229){
    e.preventDefault();
    var fm = document.getElementById("f");
    if (fm.requestSubmit){ fm.requestSubmit(); }
    else { fm.dispatchEvent(new Event("submit", { cancelable: true })); }
    return;
  }
  if (e.key === "Tab" && !qEl.value.trim()){
    e.preventDefault();
    var sg = t("suggest");
    qEl.value = sg[sIdx % sg.length];
    sIdx = (sIdx + 1) % sg.length;
    showSuggest();
  }
});

function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function add(who, cls){
  var d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = '<div class="who">' + who + '</div><div class="body"></div>';
  log.appendChild(d);
  return d.querySelector(".body");
}
