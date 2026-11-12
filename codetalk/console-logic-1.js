
var DATA = $data;
var SERVE = $serve;
var CHAT = $chat;
var VKEY = "codetalk.visited.$project_key";
var VIEWS = [["overview","开工概览"],["timeline","时光轴"],["graph","决策图"],["debt","理解债"],["filetree","文件树"],["prompts","指令回看"],["recap","会话摘要"]];

// ---- i18n:zh/en 字典 + 切换(零外联,复用 localStorage;数据仍不出本机)----
// 胶囊 outcome 的规范值恒为中文(写回 cache.db 的稳定键),仅显示层翻译。
var I18N = {
  zh: {
    console_label: "控制台", theme_toggle: "切换浅色/深色",
    search_ph: "搜时光轴 — 输入即过滤,Enter 搜全仓(/ 聚焦,Esc 清空)",
    search_aria: "搜索时光轴,Enter 全库检索",
    chip_crumb: "带决策", chip_risk: "有待验证", chip_cap: "有胶囊",
    view_overview: "开工概览", view_timeline: "时光轴", view_graph: "决策图",
    latest:"回到最新", view_debt: "理解债", view_filetree: "文件树", view_prompts: "指令回看",
    view_recap: "会话摘要", no_recap: "没抓到本项目的 Claude Code 会话记录。",
    recap_turns: "轮", recap_no_text: "(无文本输出)",
    room_search:"搜索", room_archive:"项目档案", room_read:"阅读", room_compare:"对照", room_saved:"书签", room_workspace:"工作台", full_chat: "完整对话与文件", chatfab: "接地追问", chat_dialog: "接地对话",
    chat_header: "接地对话 · 本地优先 · 模型调用按配置", close: "关闭",
    chatq_ph: "问这段代码当初为什么这么写…", ask: "问",
    ft_result_aria: "全库检索结果",
    ft_header: "全库检索 · 零 LLM(Enter 搜全仓,不止已加载)",
    ft_close_aria: "关闭检索结果",
    searching: "检索中…", no_result: "无结果", search_fail: "检索失败(后端没起来?)",
    today: "今天", days_ago: "天前",
    out_overthought: "想多了", out_resolved: "已解决", out_worried: "还在担心", out_forgot: "忘记了",
    recorded: "已记录:", reanswer: "改答 ↺", writeback_fail: "写回失败,请重试",
    readonly_hint: "只读 · 跑 console --serve 可回写",
    last_decision_label: "上次的决定 · ",
    no_digest_yet: "还没有日报。",
    run_digest_pre: "终端跑 ", run_digest_post: " 生成你的开工概览。",
    ran_ok_pre: "✓ 今天已跑过 ", ran_ok_post: " · 记录是新的",
    ran_due_pre: "今天还没跑 ", ran_due_mid: " · 上次 ",
    ran_due_post: " —— 去终端跑一下,把今天和 AI 的协作沉淀下来",
    tile_pending: "待验证胶囊", tile_coverage: "决策记录覆盖", tile_debt: "TOP 理解债",
    pending_pre: "到期待验证的预测 · ", pending_post: " 枚",
    you_worried: "你曾担心:", worried_open: "「", worried_close: "」",
    debt_top3: "理解债 top 3", see_all: "看全部 →",
    w_debt: "债", w_churn: "改", w_reviewed: "回看", w_caps: "胶囊",
    w_last_decision: "上次决定:",
    want_to_know: "想弄清什么?",
    act_chat_q: "随便问:这段代码当初为什么这么写",
    act_chat_sub: "用真实 commit / 测试 / PR 原话作答,不让 AI 现编",
    act_graph_q: "某个决策,后来牵动了哪些改动?",
    act_graph_sub: "顺着一个决策,看它的下游连锁改动",
    act_filetree_q: "某个改过的文件,当初为什么改?",
    act_filetree_sub: "从变更文件直接跳到它的来龙去脉",
    tag_due: "待验证", tag_notdue: "未到期",
    lbl_what: "改了什么", lbl_why: "为什么", lbl_decisions: "关键决策", lbl_risks: "待验证",
    no_narrative: "尚未叙事 — 跑 codetalk digest。", no_narrative_short: "尚未叙事",
    ask_this: "接地追问这段 →",
    tl_hits_mid: " 条命中 / 共 ", tl_hits_suffix: "(Esc 清空)",
    tl_default_sub: "最新在顶,点开看叙事",
    no_commits: "还没有 commit。", no_hits: "无命中:换个关键词或筛选。",
    w_decisions: " 决策", w_risks_badge: " 待验证", w_capsules: " 胶囊",
    graph_head: "决策图 — 每个决策牵动了下游哪些改动(点开)",
    no_decisions: "还没有决策节点(留 Vibe-Decision 或跑 digest 后出现)。",
    kind_breadcrumb: "原始决策记录", kind_narrative: "生成解释",
    affects_pre: "影响 ", affects_post: " 处 ▾", no_downstream: "无下游",
    ask_decision: "接地追问这个决策 →",
    debt_head: "理解债 — AI 改得多、你回看少的模块",
    no_debt: "暂无理解债数据。",
    drill_pre: "看债构成 · 未回看决策 ", drill_mid: " · 待填胶囊 ", drill_post: " ▾",
    debt_hint1: "回看是护栏弱信号；分数结合改动量、距回看时间、回看与胶囊回填比例，不是代码质量评分。",
    pending_cap_label: "待填胶囊",
    debt_hint2: "到「开工概览」回填实际结果，不必为了分数选择已解决。",
    filetree_head: "文件树 — 工作区变更 + 点开看「当初为什么」",
    expand_all: "展开全部", collapse_all: "折叠全部",
    ft_empty: "无文件或非 git 仓。",
    ft_panel_empty: "点左侧文件看它的决策历史(零 LLM)。",
    ft_no_narrative: "暂无叙事(尚未提交或无历史)。", deeper: "更深:",
    no_prompts: "近 7 天没有抓到发给 AI 的指令。",
    foot_read_pre: "已读 ", foot_read_post: " 段叙事",
    foot_serve: " · serve:回答即时写回 cache.db", foot_readonly: " · 只读",
    you: "你", chat_searching: "…接地检索中",
    degraded: "零-LLM 罗列(未调模型)", grounded_pre: "接地 ", conv_word: " 讨论",
    discuss: "讨论·", no_evidence: "(无证据)",
    chat_err: "出错了(后端没起来?查 codetalk web 终端)",
    chatwith_pre: "关于「", chatwith_mid: "」(", chatwith_post: ")当初为什么这么写?"
  },
  en: {
    console_label: "Console", theme_toggle: "Toggle light/dark",
    search_ph: "Search the timeline — type to filter, Enter for full-repo search (/ focus, Esc clear)",
    search_aria: "Search the timeline; Enter for full-repo search",
    chip_crumb: "Has decision", chip_risk: "Has to-verify", chip_cap: "Has capsule",
    view_overview: "Overview", view_timeline: "Timeline", view_graph: "Decision graph",
    latest:"Back to latest", view_debt: "Comprehension debt", view_filetree: "File tree", view_prompts: "Prompt replay",
    view_recap: "Session recap", no_recap: "No Claude Code session captured for this project.",
    recap_turns: "turns", recap_no_text: "(no text output)",
    room_search:"Search", room_archive:"Project archive", room_read:"Read", room_compare:"Compare", room_saved:"Bookmarks", room_workspace:"Workspace", full_chat: "Full chat & files", chatfab: "Grounded follow-up", chat_dialog: "Grounded chat",
    chat_header: "Grounded chat · local-first · model calls follow config", close: "Close",
    chatq_ph: "Ask why this code was written this way…", ask: "Ask",
    ft_result_aria: "Full-repo search results",
    ft_header: "Full-repo search · zero LLM (Enter searches the whole repo, not just loaded)",
    ft_close_aria: "Close search results",
    searching: "Searching…", no_result: "No results", search_fail: "Search failed (backend not running?)",
    today: "today", days_ago: "days ago",
    out_overthought: "Overthought it", out_resolved: "Resolved", out_worried: "Still worried", out_forgot: "Forgot",
    recorded: "Recorded: ", reanswer: "Change answer ↺", writeback_fail: "Write-back failed, please retry",
    readonly_hint: "Read-only · run console --serve to write back",
    last_decision_label: "Last decision · ",
    no_digest_yet: "No digest yet.",
    run_digest_pre: "Run ", run_digest_post: " in your terminal to generate your overview.",
    ran_ok_pre: "✓ Ran ", ran_ok_post: " today · records are fresh",
    ran_due_pre: "Haven't run ", ran_due_mid: " today · last run ",
    ran_due_post: " — run it in your terminal to capture today's work with AI",
    tile_pending: "Pending capsules", tile_coverage: "Decision-note coverage", tile_debt: "Top debt",
    pending_pre: "Predictions due to verify · ", pending_post: "",
    you_worried: " you were worried: ", worried_open: "“", worried_close: "”",
    debt_top3: "Comprehension debt · top 3", see_all: "See all →",
    w_debt: "debt", w_churn: "churn ", w_reviewed: "reviewed ", w_caps: "caps",
    w_last_decision: "last decision: ",
    want_to_know: "What do you want to figure out?",
    act_chat_q: "Just ask: why was this code written this way",
    act_chat_sub: "Answered from real commit / test / PR quotes — no AI improvisation",
    act_graph_q: "Which later changes did a decision pull forward?",
    act_graph_sub: "Follow a decision to its downstream chain of changes",
    act_filetree_q: "Why was a changed file changed?",
    act_filetree_sub: "Jump straight from a changed file to its backstory",
    tag_due: "to verify", tag_notdue: "not yet due",
    lbl_what: "What changed", lbl_why: "Why", lbl_decisions: "Key decisions", lbl_risks: "To verify",
    no_narrative: "No narrative yet — run codetalk digest.", no_narrative_short: "No narrative",
    ask_this: "Grounded follow-up on this →",
    tl_hits_mid: " hits / ", tl_hits_suffix: " (Esc to clear)",
    tl_default_sub: "Newest on top; click to expand the narrative",
    no_commits: "No commits yet.", no_hits: "No matches: try another keyword or filter.",
    w_decisions: " decisions", w_risks_badge: " to verify", w_capsules: " capsules",
    graph_head: "Decision graph — the downstream changes each decision pulled (click to expand)",
    no_decisions: "No decision nodes yet (leave a Vibe-Decision, or run digest).",
    kind_breadcrumb: "Source decision record", kind_narrative: "Generated interpretation",
    affects_pre: "affects ", affects_post: " ▾", no_downstream: "No downstream",
    ask_decision: "Grounded follow-up on this decision →",
    debt_head: "Comprehension debt — modules AI changed a lot but you reviewed little",
    no_debt: "No comprehension-debt data yet.",
    drill_pre: "See debt breakdown · unreviewed decisions ", drill_mid: " · capsules to fill ", drill_post: " ▾",
    debt_hint1: "Review is a weak guardrail signal. The score combines change volume, time since review, and review/capsule coverage; it is not code quality.",
    pending_cap_label: "Capsule to fill",
    debt_hint2: "Record the actual outcome in Overview; do not mark Resolved just to change the score.",
    filetree_head: "File tree — working-tree changes + click to see “why”",
    expand_all: "Expand all", collapse_all: "Collapse all",
    ft_empty: "No files, or not a git repo.",
    ft_panel_empty: "Click a file on the left to see its decision history (zero LLM).",
    ft_no_narrative: "No narrative yet (uncommitted or no history).", deeper: "Deeper: ",
    no_prompts: "No prompts sent to AI captured in the last 7 days.",
    foot_read_pre: "Read ", foot_read_post: " narratives",
    foot_serve: " · serve: answers write back to cache.db instantly", foot_readonly: " · read-only",
    you: "You", chat_searching: "…grounding retrieval",
    degraded: "Zero-LLM list (no model call)", grounded_pre: "Grounded ", conv_word: " chats",
    discuss: "chat·", no_evidence: "(no evidence)",
    chat_err: "Error (backend down? check the codetalk web terminal)",
    chatwith_pre: "Why was “", chatwith_mid: "” (", chatwith_post: ") written this way?"
  }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang");
  if (s === "zh" || s === "en") return s;
  return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en";
} catch(e){ return "zh"; } })();
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
var OUTCOMES = [["out_overthought","想多了"],["out_resolved","已解决"],["out_worried","还在担心"]];
// 显示映射含后端第 4 值「忘记了」(仅经 vault markdown 手勾产生,前端不作按钮);未知则原样
var OUTLABELS = OUTCOMES.concat([["out_forgot","忘记了"]]);
function outLabel(canon){                 // 规范中文 outcome → 当前语言显示
  for (var i = 0; i < OUTLABELS.length; i++) if (OUTLABELS[i][1] === canon) return t(OUTLABELS[i][0]);
  return canon;
}
function applyLang(){
  document.documentElement.lang = LANG;
  document.title = "$project — CodeTalk " + t("console_label");
  document.querySelectorAll("[data-i18n]").forEach(function(el){ el.textContent = t(el.getAttribute("data-i18n")); });
  document.querySelectorAll("[data-i18n-ph]").forEach(function(el){ el.placeholder = t(el.getAttribute("data-i18n-ph")); });
  document.querySelectorAll("[data-i18n-title]").forEach(function(el){ el.title = t(el.getAttribute("data-i18n-title")); });
  document.querySelectorAll("[data-i18n-aria]").forEach(function(el){ el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria"))); });
  var lb = document.getElementById("langbtn"); if (lb) lb.textContent = LANG === "zh" ? "EN" : "中文";
  if (window.onLangChange) window.onLangChange();     // 动态视图(nav/hero/时光轴等)重渲染
}
function toggleLang(){ LANG = LANG === "zh" ? "en" : "zh";
  try { localStorage.setItem("codetalk.lang", LANG); } catch(e){}
  applyLang(); }

function esc(s){ return String(s == null ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function store(v){ try {
  if (v === undefined) return JSON.parse(localStorage.getItem(VKEY)) || {};
  localStorage.setItem(VKEY, JSON.stringify(v));
} catch (e) { return {}; } }
function post(path, payload){ if (!SERVE) return Promise.resolve(false);
  return fetch(path, {method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify(projectPayload(payload))}).then(function(r){ return r.ok; })
    .catch(function(){ return false; }); }
function agoText(n){ return n === 0 ? t("today") : n + " " + t("days_ago"); }
// 键盘可达:Enter / Space 激活;Space 阻止默认滚屏。给可点击非按钮元素接键。
function onActivate(el, fn){
  el.addEventListener("click", fn);
  el.addEventListener("keydown", function(e){
    if (e.key === "Enter" || e.key === " "){ e.preventDefault(); fn(e); }
  });
}
var visited = store();

// ---- 视图持久化 + 深链(hash 为单一真相源:刷新/分享/后退按钮都回到当前视图)----
var VVKEY = "codetalk.view.$project_key";
function validView(n){ return VIEWS.some(function(v){ return v[0] === n; }); }
function storeView(n){ try { localStorage.setItem(VVKEY, n); } catch (e) {} }
function loadView(){ try { return localStorage.getItem(VVKEY); } catch (e) { return null; } }
var TLQ = "";   // 时光轴搜索过滤词(已小写;空=不过滤)

// ---- 主题(初始偏好已在 head 解析;此处设值 + 同步图标 + 接线)----
function setTheme(theme){                 // 参数不叫 t:t() 是 i18n 翻译器,勿遮蔽
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("codetalk.theme", theme); } catch (e) {}
  var b = document.getElementById("themebtn");
  if (b) b.textContent = theme === "light" ? "🌙" : "☀";
}
function initTheme(){
  var b = document.getElementById("themebtn");
  if (!b) return;
  b.textContent = document.documentElement.getAttribute("data-theme") === "light"
    ? "🌙" : "☀";
  b.addEventListener("click", function(){
    setTheme(document.documentElement.getAttribute("data-theme") === "light"
      ? "dark" : "light"); });
}

// ---- 导航 ----
var currentView = null, viewScroll = {};
function show(name){
  document.body.dataset.consoleView = name;
  document.querySelector(".b-workspace").open = false;
  document.getElementById("room-mode-read").classList.toggle("active", name === "timeline" && !roomBookmarksOnly);
  var changed = currentView !== name;
  if (currentView && changed) viewScroll[currentView] = window.scrollY;
  currentView = name;
  VIEWS.forEach(function(v){
    document.getElementById("v"+"-"+v[0]).classList.toggle("on", v[0]===name);
  });
  document.querySelectorAll("#nav button").forEach(function(b){
    var on = b.getAttribute("data-v")===name;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;                  // tablist:只 Tab 进当前页签
  });
  if (changed) window.scrollTo(0, viewScroll[name] || 0);
}
