var _lb = document.getElementById("langbtn"); if (_lb) _lb.addEventListener("click", toggleLang);
applyLang();

// ---- 开屏 + 深链 + 键盘导航 ----
(function initNav(){
  var start = validView((location.hash || "").slice(1)) ? location.hash.slice(1)
            : (validView(loadView()) ? loadView() : "timeline");
  show(start); storeView(start);
  if (location.hash.slice(1) !== start) {
    try { history.replaceState(null, "", "#" + start); } catch (e) { location.hash = start; }
  }
  window.addEventListener("hashchange", function(){
    var n = location.hash.slice(1);
    if (validView(n)) { show(n); storeView(n); }
  });
  document.addEventListener("keydown", function(e){     // 数字键 1-7 切视图
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = e.target && e.target.tagName;             // 输入/文本域内不劫持
    if (tag === "INPUT" || tag === "TEXTAREA" || (e.target && e.target.isContentEditable)) return;
    if (e.key === "/") { var qf = document.getElementById("q");
      if (qf) { e.preventDefault(); document.querySelector(".b-search").open = true; qf.focus(); } return; }
    var i = "1234567".indexOf(e.key);     // 7 个视图(含会话摘要),数字键 1-7 全覆盖
    if (i >= 0 && i < VIEWS.length) { e.preventDefault(); location.hash = VIEWS[i][0]; }
  });
  var qel = document.getElementById("q");        // 搜索框:实时过滤时光轴
  if (qel) {
    qel.addEventListener("input", function(){
      TLQ = qel.value.trim().toLowerCase(); renderTimeline();
      if (TLQ && location.hash.slice(1) !== "timeline") location.hash = "timeline";
    });
    qel.addEventListener("keydown", function(e){
      if (e.key === "Escape") { clearFilters(); ftHide(); qel.blur(); }
      else if (e.key === "Enter") { e.preventDefault(); ftSearch(qel.value.trim()); }
    });
  }
  var ftc = document.getElementById("ftclose");
  if (ftc) ftc.addEventListener("click", ftHide);
  document.querySelectorAll("#chips .chip").forEach(function(b){
    b.addEventListener("click", function(){
      var f = b.getAttribute("data-f"); TLF[f] = !TLF[f];
      b.classList.toggle("on", TLF[f]);
      b.setAttribute("aria-pressed", TLF[f] ? "true" : "false");
      renderTimeline();
      if (tlActive() && location.hash.slice(1) !== "timeline") location.hash = "timeline";
    });
  });
})();
