/* Presentation only: existing renderers and endpoints retain data ownership. */
(function () {
  "use strict";
  var rail = document.querySelector(".ui-rail");
  if (!rail) return;
  function language() {
    var en = document.documentElement.lang.slice(0, 2) === "en";
    rail.querySelectorAll("[data-ui-zh]").forEach(function (el) {
      el.textContent = en ? el.dataset.uiEn : el.dataset.uiZh;
    });
  }
  language();
  new MutationObserver(language).observe(document.documentElement, {
    attributes: true, attributeFilter: ["lang"]
  });
  var cards = document.getElementById("cards");
  if (cards && document.body.dataset.uiPage === "review") {
    var index = document.createElement("div");
    index.className = "ui-record-index";
    rail.insertBefore(index, rail.lastElementChild);
    function refreshIndex() {
      index.replaceChildren();
      cards.querySelectorAll("article.card").forEach(function (card, i) {
        card.id = "ui-review-" + i;
        var label = card.querySelector(".location");
        var link = document.createElement("a");
        link.href = "#" + card.id;
        link.textContent = label ? label.textContent : String(i + 1);
        index.appendChild(link);
      });
    }
    refreshIndex();
    new MutationObserver(refreshIndex).observe(cards, { childList: true });
  }
  var reduced = matchMedia("(prefers-reduced-motion: reduce)");
  var spring = CommercialMotion.spring;
  var active = null, frame = 0, previous = 0;
  var x = { x: 0, v: 0 }, y = { x: 0, v: 0 }, target = { x: 0, y: 0 };
  function stop() {
    cancelAnimationFrame(frame); frame = 0; previous = 0;
    if (active) { active.style.transform = ""; active.classList.remove("ui-material"); }
    active = null; x = { x: 0, v: 0 }; y = { x: 0, v: 0 };
  }
  function tick(now) {
    frame = 0;
    if (!active || !active.isConnected || document.hidden || reduced.matches) { stop(); return; }
    var dt = Math.min((now - previous) / 1000 || 1 / 60, 1 / 30); previous = now;
    x = spring(x, target.x, dt); y = spring(y, target.y, dt);
    active.style.transform = "perspective(1200px) rotateX(" + x.x + "deg) rotateY(" + y.x + "deg)";
    if (Math.abs(x.x - target.x) + Math.abs(y.x - target.y) + Math.abs(x.v) + Math.abs(y.v) > .01) {
      frame = requestAnimationFrame(tick);
    } else { previous = 0; }
  }
  document.addEventListener("pointermove", function (event) {
    if (reduced.matches || event.pointerType === "touch") return;
    var el = event.target.closest(".row.open > .head");
    if (!el) { if (active) stop(); return; }
    if (active !== el) { stop(); active = el; active.classList.add("ui-material"); }
    var rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    target = { x: (.5 - (event.clientY - rect.top) / rect.height) * 1.4,
               y: ((event.clientX - rect.left) / rect.width - .5) * 1.8 };
    if (!frame) frame = requestAnimationFrame(tick);
  });
  document.addEventListener("keydown", stop, true);
  document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); });
  window.addEventListener("blur", stop);
  reduced.addEventListener("change", function () { if (reduced.matches) stop(); });
})();
