function wireDueButtons(){
  if (!SERVE) return;
  var due = dueCaps();
  due.forEach(function(d, k){ wireDueAns(k, due); });
}

function renderFooter(){
  var read = DATA.filter(function(c){ return visited[c.sha]; }).length;
  document.getElementById("foot").textContent =
    t("foot_p1") + read + "/" + DATA.length + t("foot_p2")
    + (SERVE ? t("foot_serve") : t("foot_readonly"));
}

// 语言切换:静态元素由 applyLang 换,动态时间轴/胶囊经 onLangChange 重渲染
window.onLangChange = renderTimeline;
var _lb = document.getElementById("langbtn");
if (_lb) _lb.addEventListener("click", toggleLang);
applyLang();
document.addEventListener("keydown", function(e){     // j/k 在 commit 行头间移焦点
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  var tag = e.target && e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (e.key !== "j" && e.key !== "k") return;
  var heads = [].slice.call(document.querySelectorAll(".head"));
  if (!heads.length) return;
  var cur = heads.indexOf(document.activeElement);
  var nx = cur < 0 ? 0 : (e.key === "j" ? cur + 1 : cur - 1);
  nx = Math.max(0, Math.min(heads.length - 1, nx));
  e.preventDefault(); heads[nx].focus();
});
