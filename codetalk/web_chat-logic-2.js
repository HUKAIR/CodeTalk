function renderDone(body, ev, acc){
  var provenance = document.createElement("span"); provenance.className = "badge"; provenance.textContent = t(ev.degraded ? "retrieved" : "generated"); body.parentNode.querySelector(".who").appendChild(provenance);
  if (ev.degraded){
    var b = document.createElement("span");
    b.className = "badge"; b.textContent = t("degraded");
    body.parentNode.querySelector(".who").appendChild(b);
  }
  var cp = document.createElement("button");            // 复制答案(127.0.0.1 = clipboard 安全上下文)
  cp.type = "button"; cp.className = "copybtn"; cp.textContent = t("copy");
  cp.addEventListener("click", function(){
    function ok(){ cp.textContent = t("copied");
      setTimeout(function(){ cp.textContent = t("copy"); }, 1200); }
    if (navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(acc).then(ok, function(){ cp.textContent = t("copy_fail"); });
    } else { cp.textContent = t("copy_fail"); }
  });
  body.parentNode.querySelector(".who").appendChild(cp);
  function setBody(html){ body.innerHTML = html; }      // 全文件唯一 innerHTML sink
  var H = ev.highlights || [];
  if (H.length){
    if (H.map(function(s){ return s.text; }).join("") !== acc){
      setBody(esc(acc));                                 // 段拼接≠累积答案 → 回退,仍转义
    } else {
      setBody(H.map(function(s){
        return s.cite_id == null ? esc(s.text)
          : '<mark class="vb" data-cite="' + String(s.cite_id) + '">' + esc(s.text) + '</mark>';
      }).join(""));
      var lg = document.createElement("div"); lg.className = "hl-legend";
      lg.textContent = t("hl_legend");
      body.parentNode.appendChild(lg);
    }
  }
  var cites = ev.citations || [];
  if (!cites.length) return;
  var readingY = null, readingTrigger = null;
  function rememberReading(trigger){ if (readingY === null) readingY = window.scrollY; readingTrigger = trigger; back.hidden = false; }
  function returnReading(){ panel.style.display = "none"; panel.dataset.cur = ""; back.hidden = true; if (readingTrigger) readingTrigger.focus({preventScroll:true}); if (readingY !== null) window.scrollTo(0, readingY); readingY = null; }
  function openCommit(sha, panel){                       // 点 SHA → 拉真实 commit 到就地面板
    panel.textContent = t("loading_commit"); panel.style.display = "block";
    panel.dataset.cur = "commit:" + sha;
    var requested = panel.dataset.cur;
    fetch(apiPath("/api/commit/" + encodeURIComponent(sha)))
      .then(function(r){ return r.ok ? r.json() : Promise.reject(); })
      .then(function(d){
        if (panel.dataset.cur !== requested) return;
        panel.textContent = (d.date ? d.date + "  " : "") + (d.subject || "")
          + (d.body ? "\n\n" + d.body : "") + (d.diff ? "\n\n" + d.diff : "");
      })
      .catch(function(){ if (panel.dataset.cur === requested) panel.textContent = t("commit_fail"); });
  }
  var box = document.createElement("div"); box.className = "cites";
  var panel = document.createElement("pre"); panel.className = "evid";
  panel.style.display = "none";
  var back = document.createElement("button"); back.type = "button"; back.className = "source-return"; back.textContent = t("return_reading"); back.hidden = true; back.onclick = returnReading;
  cites.forEach(function(c){
    var s = document.createElement("button"); s.type = "button"; s.className = "cite";
    s.textContent = (c.kind === "conversation" ? t("discuss") : "") + (c.sha || c.id) + " ▸";
    s.title = (c.evidence || "").slice(0, 280);          // hover 预览真实原话(GitLens 范式)
    s.dataset.cite = String(c.id);                       // <mark> 点击联动锚点
    s.addEventListener("click", function(){              // 点开就地核验真实记录,再点收起
      var cur = String(c.id);
      if (panel.dataset.cur === cur && panel.style.display !== "none"){
        returnReading();
      } else {
        rememberReading(s); panel.textContent = t("original") + "\n\n" + (c.evidence || t("no_evidence"));
        panel.style.display = "block"; panel.dataset.cur = cur;
      }
    });
    box.appendChild(s);
    if (c.sha && c.kind !== "conversation"){             // commit 引用:点开真实 git show 核验
      var d = document.createElement("button"); d.type = "button"; d.className = "cite";
      d.textContent = "diff ▾"; d.title = t("diff_title");
      d.setAttribute("role", "button"); d.tabIndex = 0;
      var open = function(){ rememberReading(d); openCommit(c.sha, panel); };
      d.addEventListener("click", open);

      box.appendChild(d);
    }
    (c.sources || []).forEach(function(src){             // PR 可点击跳真实源(新标签页)
      if (src.type === "pr" && src.url){
        var a = document.createElement("a"); a.className = "cite";
        a.href = src.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = "#" + src.number + " ↗"; box.appendChild(a);
      }
    });
  });
  body.parentNode.appendChild(box);
  body.parentNode.appendChild(panel); body.parentNode.appendChild(back);
  body.querySelectorAll("mark.vb").forEach(function(m){  // <mark> 点击 → 滚到并高亮对应 chip
    m.addEventListener("click", function(){
      var el = body.parentNode.querySelector('.cite[data-cite="' + CSS.escape(m.getAttribute("data-cite")) + '"]');
      if (el){ el.scrollIntoView({ block: "center" });
        el.classList.add("cite-hot");
        setTimeout(function(){ el.classList.remove("cite-hot"); }, 1200); }
    });
  });
}

document.getElementById("f").addEventListener("submit", function(e){
  e.preventDefault();
  var q = document.getElementById("q").value.trim();
  if (!q || document.getElementById("send").disabled) return;
  add(t("you"), "user").textContent = q;
  document.getElementById("q").value = "";
  var btn = document.getElementById("send"); btn.disabled = true;
  var body = add("codetalk", "bot"); body.textContent = t("searching"); scrollEnd();
  var acc = "";                                          // 累积完整答案,供 done 切段重渲染
  fetch("/api/chat/stream", { method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(projectPayload({ question:q, conv_id:convId, turn_seq:turn++, target: pendingTarget })) })
    .then(function(resp){
      if (!resp.ok || !resp.body) throw new Error("Request failed");
      var reader = resp.body.getReader(), dec = new TextDecoder(), buf = "", started = false;
      function pump(){
        return reader.read().then(function(res){
          if (res.done){ btn.disabled = false; return; }
          buf += dec.decode(res.value, { stream:true });
          var parts = buf.split("\n\n"); buf = parts.pop();
          parts.forEach(function(p){
            var line = p.trim();
            if (line.indexOf("data:") !== 0) return;
            var ev; try { ev = JSON.parse(line.slice(5).trim()); } catch(e){ return; }
            if (ev.type === "token"){
              var wasBottom = atBottom();                    // 流式期间贴底,除非用户上滚
              if (!started){ body.textContent = ""; started = true; }
              body.textContent += ev.text; acc += ev.text;   // 逐块蹦字(流式)+ 累积
              if (wasBottom) scrollEnd(); else document.getElementById("latest").hidden = false;
            } else if (ev.type === "done"){ var follow = atBottom(); renderDone(body, ev, acc); if (follow) scrollEnd(); }
          });
          return pump();
        });
      }
      return pump();
    })
    .catch(function(){ body.textContent = t("err");
      btn.disabled = false; });
  pendingTarget = null;
});

// 语言切换:静态元素由 applyLang 换,动态内容(建议行 + 文件树)经 onLangChange 重渲染
window.onLangChange = function(){ showSuggest(); renderFiletree(); };
var _lb = document.getElementById("langbtn");
if (_lb) _lb.addEventListener("click", toggleLang);
applyLang();
