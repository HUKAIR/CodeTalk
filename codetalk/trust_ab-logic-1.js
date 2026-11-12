
var DATA = $data;
var I18N = {
  zh: { tagline:"真实记录 vs AI 从 diff 反推 · 零 LLM · SHA 可验证",
    lead:"同一段代码,两个「为什么」。一个是逐字真实记录,一个是 AI 只看 diff 反推的。你更信哪个?",
    lead_sub:"每条先选 A 或 B(别偷看),全选完点「看真相」——看看你几次选中了真实记录。",
    reveal_btn:"看真相", trust_a:"信 A", trust_b:"信 B", src:"来源",
    real_tag:"← 真实记录(CodeTalk 逐字)", other_tag:"← AI 从 diff 反推",
    score:"本次 {n} 道示例中选中 {x} 条原始记录；这不是能力或准确率评测。",
    pitch:"真实记录 = CodeTalk 零-LLM 逐字引 commit/会话,点 SHA 可核验;另一侧 = AI 只凭 diff 反推(未给 commit message)。" },
  en: { tagline:"real records vs AI inference from diff · zero-LLM · SHA-verifiable",
    lead:"Same code, two “whys”. One is a verbatim real record; the other is AI inferring from the diff alone. Which do you trust?",
    lead_sub:"Pick A or B for each (no peeking), then hit “Reveal” — see how often you trusted the real record.",
    reveal_btn:"Reveal", trust_a:"Trust A", trust_b:"Trust B", src:"Source",
    real_tag:"← real record (CodeTalk, verbatim)", other_tag:"← AI inference from diff",
    score:"Selected {x} original records in {n} examples. This is not an ability or accuracy benchmark.",
    pitch:"Real record = CodeTalk zero-LLM verbatim citation of the commit/session, SHA-verifiable; the other = AI inferring from the diff alone (no commit message given)." }
};
var LANG = (function(){ try { var s = localStorage.getItem("codetalk.lang");
  if (s === "zh" || s === "en") return s;
  return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en";
} catch(e){ return "zh"; } })();
function t(k){ return (I18N[LANG] && I18N[LANG][k] != null) ? I18N[LANG][k] : I18N.zh[k]; }
function esc(s){ return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
var picks = {};              // idx -> "a"|"b"
function render(){
  var box = document.getElementById("items"), items = DATA.items || [];
  box.innerHTML = items.map(function(it, i){
    return '<div class="item"><p class="subj"><span class="sha">['+esc(it.sha)+']</span> '
      + esc(it.date) + ' ' + esc(it.subject) + '</p>'
      + '<div class="pair">'
      + '<div class="src" data-side="a"><h4>' + t("src") + ' A</h4><pre>'+esc(it.a)+'</pre></div>'
      + '<div class="src" data-side="b"><h4>' + t("src") + ' B</h4><pre>'+esc(it.b)+'</pre></div>'
      + '</div>'
      + '<div class="choose"><button data-i="'+i+'" data-p="a">'+t("trust_a")+'</button>'
      + '<button data-i="'+i+'" data-p="b">'+t("trust_b")+'</button></div>'
      + '<div class="reveal" data-i="'+i+'"></div></div>';
  }).join("");
  box.querySelectorAll(".choose button").forEach(function(b){
    b.addEventListener("click", function(){
      var i = b.getAttribute("data-i");
      picks[i] = b.getAttribute("data-p");
      b.parentNode.querySelectorAll("button").forEach(function(x){ x.classList.remove("pick"); });
      b.classList.add("pick");
      document.getElementById("revealbtn").disabled =
        Object.keys(picks).length < items.length;
    });
  });
}
function reveal(){
  var items = DATA.items || [], correct = 0;
  items.forEach(function(it, i){
    if (picks[i] === it.real) correct++;
    var r = document.querySelector('.reveal[data-i="'+i+'"]');
    var realUp = it.real.toUpperCase(), otherUp = (it.real === "a" ? "B" : "A");
    r.innerHTML = '<span class="real">' + realUp + ' ' + t("real_tag") + '</span> · '
      + '<span class="other">' + otherUp + ' ' + t("other_tag") + '</span>';
    r.classList.add("show");
  });
  var sc = document.getElementById("score");
  sc.textContent = t("score").replace("{n}", items.length).replace("{x}", correct);
  sc.classList.add("show");
  document.getElementById("revealbtn").disabled = true;
}
function applyLang(){
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(function(el){ el.textContent = t(el.getAttribute("data-i18n")); });
  var lb = document.getElementById("langbtn"); if (lb) lb.textContent = LANG === "zh" ? "EN" : "中文";
  render();                  // 重渲染(按钮文案/来源标签随语言)
}
document.getElementById("langbtn").addEventListener("click", function(){
  LANG = LANG === "zh" ? "en" : "zh";
  try { localStorage.setItem("codetalk.lang", LANG); } catch(e){}
  picks = {}; applyLang(); document.getElementById("revealbtn").disabled = true;
  var sc = document.getElementById("score"); sc.classList.remove("show");
});
document.getElementById("revealbtn").addEventListener("click", reveal);
applyLang();
