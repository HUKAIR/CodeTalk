
(function () {
  "use strict";
  document.querySelectorAll("#back-index, #back-index-rail").forEach(function(back) {
    try { if (new URL(document.referrer).href === back.href) back.onclick = function(e){ e.preventDefault(); history.back(); }; } catch(e) {}
  });
  document.getElementById("themebtn").addEventListener("click", function () {
    var root = document.documentElement;
    var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("codetalk.theme", next); } catch (e) {}
  });
  var chips = document.querySelectorAll(".fchip");
  var cards = document.querySelectorAll(".card");
  var links = document.querySelectorAll(".tgroup a");
  var bars = document.querySelectorAll(".daybar");
  var groups = document.querySelectorAll(".tgroup");
  var vcount = document.querySelector("#vcount b");
  function match(el, f) {
    if (f === "all") return true;
    if (f === "ask") return el.dataset.kind === "real";
    if (f === "cmd") return el.dataset.kind === "command";
    return el.dataset.edit === "1";           /* edit */
  }
  function apply(f) {
    var n = 0;
    cards.forEach(function (c) {
      var ok = match(c, f);
      c.classList.toggle("hide", !ok);
      if (ok) n++;
    });
    links.forEach(function (a) { a.classList.toggle("hide", !match(a, f)); });
    groups.forEach(function (g) {           /* 组内全隐时连组头一起藏 */
      g.classList.toggle("hide", !g.querySelector("a:not(.hide)"));
    });
    bars.forEach(function (b) {             /* 该日无可见卡片时藏分割条 */
      var el = b.nextElementSibling, any = false;
      while (el && !el.classList.contains("daybar")) {
        if (el.classList.contains("card") && !el.classList.contains("hide")) {
          any = true; break;
        }
        el = el.nextElementSibling;
      }
      b.classList.toggle("hide", !any);
    });
    vcount.textContent = n;
  }
  chips.forEach(function (ch) {
    ch.addEventListener("click", function () {
      chips.forEach(function (o) { o.classList.remove("on"); });
      ch.classList.add("on");
      apply(ch.dataset.f);
    });
  });
  apply("all");
})();
