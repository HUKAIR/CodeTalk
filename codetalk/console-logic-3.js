function debtDrill(r, asks){
  var un = r.unreviewed || [], pc = r.pending_caps || [];
  if (!un.length && !pc.length) return '';
  var h = '<details class="dd"><summary>'+t("drill_pre")+un.length
    + t("drill_mid")+pc.length+t("drill_post")+'</summary>';
  un.forEach(function(u){
    h += '<div class="ddi"><span class="sha">'+esc(u.sha)+'</span> '+esc(u.subject);
    (u.decisions||[]).forEach(function(d){ h += '<div class="d">· '+esc(d)+'</div>'; });
    h += '<div class="ddh">'+t("debt_hint1")+'</div>';
    if (CHAT){ h += '<button class="askbtn" type="button">'+t("ask_decision")+'</button>';
      asks.push({sha:u.sha, subject:u.subject}); }
    h += '</div>';
  });
  pc.forEach(function(c){
    h += '<div class="ddi"><span class="imp">'+t("pending_cap_label")+'</span> '+esc(c.risk)
      + '<div class="ddh">'+t("debt_hint2")+'</div></div>';
  });
  return h + '</details>';
}
function renderDebt(){
  var D = DATA.debt || [], h = '<h2 class="vh">'+t("debt_head")+'</h2><p class="ro">'+t("debt_hint1")+'</p>';
  if (!D.length){ document.getElementById("v-debt").innerHTML = h
    + '<p class="empty">'+t("no_debt")+'</p>'; return; }
  var peak = D[0].debt || 1, asks = [];
  D.forEach(function(r){
    h += '<div class="debt"><span class="f">'+esc(r.file)+'</span>'
      + '<span class="sha">'+t("w_debt")+' '+r.debt+'</span>'
      + '<div class="bar2" style="width:'+Math.max(4, Math.round(r.debt/peak*100))+'%"></div>'
      + '<span class="meta">'+t("w_churn")+r.churn+' · '+t("w_reviewed")+r.reviewed+'/'+r.commits
      + (r.caps_total?' · '+t("w_caps")+r.caps_filled+'/'+r.caps_total:"")
      + (r.last_decision?' · '+t("w_last_decision")+esc(r.last_decision):"")+'</span>'
      + debtDrill(r, asks)+'</div>';
  });
  var el = document.getElementById("v-debt");
  el.innerHTML = h;
  if (CHAT) el.querySelectorAll(".dd .askbtn").forEach(function(b, i){
    b.addEventListener("click", function(){ openChatWith(asks[i].sha, asks[i].subject); });
  });
}

function renderFiletree(){
  var T = (DATA.tree && DATA.tree.nodes) || null;
  var G = (DATA.tree && DATA.tree.grounding) || [];
  var sec = document.getElementById("v-filetree");
  var head = '<h2 class="vh">'+t("filetree_head")
    + ' <button id="ftexpand" class="ftbtn" type="button">'+t("expand_all")+'</button>'
    + '<button id="ftcollapse" class="ftbtn" type="button">'+t("collapse_all")+'</button></h2>';
  if (!T || !T.children || !T.children.length){
    sec.innerHTML = head + '<p class="empty">'+t("ft_empty")+'</p>'; return; }
  var gmap = {}; G.forEach(function(e){ gmap[e.path] = e.commits || []; });
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
    return '<details class="ftd"'+(node.changed?" open":"")+'><summary'+pad+'>'
      + esc(node.name)+'</summary>'+kids+'</details>';
  }
  sec.innerHTML = head + '<div class="ftwrap"><div class="fttree">'
    + T.children.map(function(c){ return nodeHtml(c, 0); }).join("")
    + '</div><div class="ftpanel" id="ftpanel">'
    + '<p class="empty">'+t("ft_panel_empty")+'</p></div></div>';
  var eb = document.getElementById("ftexpand"), cb = document.getElementById("ftcollapse");
  if (eb) eb.addEventListener("click", function(){
    sec.querySelectorAll("details.ftd").forEach(function(d){ d.open = true; }); });
  if (cb) cb.addEventListener("click", function(){
    sec.querySelectorAll("details.ftd").forEach(function(d){ d.open = false; }); });
  function showPanel(path){
    var rows = gmap[path], p = document.getElementById("ftpanel");
    if (!rows || !rows.length){
      p.innerHTML = '<h3>'+esc(path)+'</h3>'
        + '<p class="empty">'+t("ft_no_narrative")+'</p>'
        + '<p class="hint">'+t("deeper")+'<code>codetalk blame '+esc(path)+'</code></p>'; return; }
    var h = '<h3>'+esc(path)+'</h3>';
    rows.forEach(function(r){
      h += '<div class="ftc"><span class="sha">'+esc(r.sha)+'</span> '+esc(r.subject)
        + ' <span class="meta">'+esc(r.date)+'</span>';
      (r.decisions||[]).forEach(function(d){ h += '<div class="dec">· '+esc(d)+'</div>'; });
      h += '</div>';
    });
    p.innerHTML = h;
  }
  sec.querySelectorAll(".ftf").forEach(function(el){
    function act(){ showPanel(el.getAttribute("data-path")); }
    el.addEventListener("click", act);
    el.addEventListener("keydown", function(e){
      if (e.key==="Enter" || e.key===" "){ e.preventDefault(); act(); } });
  });
}

function renderPrompts(){
  var md = DATA.prompts_md || "";
  var sec = document.getElementById("v-prompts");
  if (!md || md.indexOf("没有抓到指令") >= 0) {
    sec.innerHTML = '<h2 class="vh">'+t("view_prompts")+'</h2><p style="opacity:.6;padding:24px">'
      + t("no_prompts")+'</p>';
    return;
  }
  var html = esc(md)
    .replace(/^### (.+)$$/gm, '<h4>$$1</h4>')
    .replace(/^## (.+)$$/gm, '<h3 style="margin-top:20px">$$1</h3>')
    .replace(/^# (.+)$$/gm, '<h2 class="vh">$$1</h2>')
    .replace(/^- (.+)$$/gm, '<div style="padding:2px 0 2px 16px;border-left:2px solid var(--line)">$$1</div>')
    .replace(/^ {2}&gt; (.+)$$/gm, '<div style="padding:2px 0 2px 24px;opacity:.7;font-style:italic">$$1</div>')
    .replace(/^ {2}\*\*AI responded:\*\*$$/gm, '<div style="padding:4px 0 2px 16px;font-weight:600;font-size:12px;opacity:.5">AI responded:</div>')
    .replace(/→ (.+)$$/gm, '<div style="padding:2px 0 2px 16px;opacity:.8">→ $$1</div>')
    .replace(/\n/g, '<br>');
  sec.innerHTML = html;
}

function renderRecap(){
  // 第 7 视图:最近一次 Claude Code 会话的结论先行摘要(数据由 recap.console_payload
  // 装配,有界、无全文;完整版走 codetalk recap 静态页)。无会话 → 空态提示。
  var sec = document.getElementById("v-recap"), r = DATA.recap;
  if (!r || !r.turns || !r.turns.length){
    sec.innerHTML = '<h2 class="vh">'+t("view_recap")+'</h2><p style="opacity:.6;padding:24px">'
      + t("no_recap")+'</p>';
    return;
  }
  var h = '<h2 class="vh">'+t("view_recap")+' · '+esc(String(r.session_id).slice(0,8))
    + ' · '+r.turns.length+' '+t("recap_turns")+'</h2>';
  r.turns.forEach(function(tn, i){
    var meta = (tn.files||[]).map(function(f){ return '<span class="chip">'+esc(f)+'</span>'; }).join(" ");
    if (tn.tools && tn.tools.length)
      meta += ' <span style="opacity:.55;font-family:var(--mono);font-size:12px">'
        + tn.tools.map(function(p){ return esc(p[0])+"×"+p[1]; }).join(" ")+'</span>';
    h += '<div class="card" id="rc'+(i+1)+'">'
      + '<div style="font-family:var(--mono);font-size:12px;opacity:.5">#'+(i+1)
      + (tn.kind==="command" ? " ⌘" : "")+'</div>'
      + '<div style="opacity:.65;font-size:13px;white-space:pre-wrap;word-break:break-word">'+esc(tn.ask)+'</div>'
      + '<div style="font-weight:700;margin:4px 0;word-break:break-word">'+esc(tn.concl || t("recap_no_text"))+'</div>'
      + (meta ? '<div>'+meta+'</div>' : '')+'</div>';
  });
  sec.innerHTML = h;
}

function renderFoot(){
  var read = DATA.timeline.filter(function(c){ return visited[c.sha]; }).length;
  document.getElementById("foot").textContent = t("foot_read_pre")+read+"/"+DATA.timeline.length
    + t("foot_read_post") + (SERVE?t("foot_serve"):t("foot_readonly"));
}

// ---- 接地对话 dock(去 silo:console 内嵌 chat;链 A 从记录原地追问)----
var chatConv = "console-" + Date.now(), chatTurn = 0;
function chatAdd(who, cls){
  var d = document.createElement("div"); d.className = "m " + cls;
  d.innerHTML = '<div class="who">'+who+'</div><div class="bd"></div>';
  var log = document.getElementById("chatlog"); log.appendChild(d);
  log.scrollTop = log.scrollHeight; return d.querySelector(".bd");
}
function chatDone(bd, ev){
  var who = bd.parentNode.querySelector(".who"), g = ev.grounding || {};
  var b = document.createElement("span");
  if (ev.degraded){ b.className = "badge warn"; b.textContent = t("degraded"); }
  else { b.className = "badge"; b.textContent = t("grounded_pre")+(g.commits||0)+" commit"
    + (g.conversations ? " · "+g.conversations+t("conv_word") : ""); }
  who.appendChild(b);
  var cites = ev.citations || []; if (!cites.length) return;
  var box = document.createElement("div"); box.className = "cites";
  var panel = document.createElement("pre"); panel.className = "evid"; panel.style.display = "none";
  cites.forEach(function(c){
    var s = document.createElement("span"); s.className = "cite";
    s.textContent = (c.kind==="conversation"?t("discuss"):"") + (c.sha||c.id) + " ▸";
    s.title = (c.evidence || "").slice(0, 280);     // hover 预览真实原话(GitLens 范式)
    s.addEventListener("click", function(){
      var cur = String(c.id);
      if (panel.dataset.cur===cur && panel.style.display!=="none"){
        panel.style.display="none"; panel.dataset.cur=""; }
      else { panel.textContent = c.evidence || t("no_evidence");
        panel.style.display="block"; panel.dataset.cur=cur; }
    });
    box.appendChild(s);
    (c.sources || []).forEach(function(src){        // PR 可点击跳真实源(新标签页)
      if (src.type === "pr" && src.url){
        var a = document.createElement("a"); a.className = "cite";
        a.href = src.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = "#" + src.number + " ↗"; box.appendChild(a);
      }
    });
  });
  bd.parentNode.appendChild(box); bd.parentNode.appendChild(panel);
}
function chatSend(q){
  q = (q||"").trim(); if (!q || document.getElementById("chatsend").disabled) return;
  chatAdd(t("you"),"user").textContent = q;
  var bd = chatAdd("codetalk","bot"); bd.textContent = t("chat_searching");
  var btn = document.getElementById("chatsend"); btn.disabled = true;
  fetch("/api/chat/stream", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(projectPayload({question:q, conv_id:chatConv, turn_seq:chatTurn++}))})
   .then(function(resp){
     var rd = resp.body.getReader(), dec = new TextDecoder(), buf = "", started = false;
     function pump(){ return rd.read().then(function(r){
       if (r.done){ btn.disabled = false; return; }
       buf += dec.decode(r.value, {stream:true});
       var parts = buf.split("\n\n"); buf = parts.pop();
       parts.forEach(function(p){ var line = p.trim();
         if (line.indexOf("data:")!==0) return;
         var ev; try { ev = JSON.parse(line.slice(5).trim()); } catch(e){ return; }
         if (ev.type==="token"){ var lg = document.getElementById("chatlog"), follow = lg.scrollHeight - lg.scrollTop - lg.clientHeight < 80; if(!started){ bd.textContent=""; started=true; }
           bd.textContent += ev.text;
           if (follow) lg.scrollTop = lg.scrollHeight; document.getElementById("chatlatest").hidden = follow; }
         else if (ev.type==="done"){ chatDone(bd, ev); } });
       return pump(); }); }
     return pump();
   })
   .catch(function(){ bd.textContent = t("chat_err");
     btn.disabled = false; });
}
function openChat(){ document.getElementById("chatdock").classList.add("on");
  document.getElementById("chatfab").hidden = true; document.getElementById("chatq").focus(); }
function closeChat(){ document.getElementById("chatdock").classList.remove("on");
  document.getElementById("chatfab").hidden = false; document.getElementById("chatfab").focus(); }
function openChatWith(sha, subject){     // 链 A:从某条记录原地唤起,开场按该节点定制
  openChat();
  document.getElementById("chatq").value = t("chatwith_pre")+subject+t("chatwith_mid")+sha+t("chatwith_post");
  document.getElementById("chatq").focus();
}
function initChat(){
  document.getElementById("chatlatest").onclick = function(){ var log = document.getElementById("chatlog"); log.scrollTop = log.scrollHeight; this.hidden = true; };
  if (!CHAT) return;                     // 非 codetalk web 服务 → 无 /api/chat,不挂 UI
  document.getElementById("chatfab").hidden = false;
  document.getElementById("chatfab").addEventListener("click", openChat);
  document.getElementById("chatclose").addEventListener("click", closeChat);
  document.getElementById("chatform").addEventListener("submit", function(e){
    e.preventDefault(); var q = document.getElementById("chatq").value;
    document.getElementById("chatq").value = ""; chatSend(q); });
}

buildNav(); initTheme(); renderOverview(); renderTimeline(); renderGraph(); renderDebt();
renderFiletree(); renderPrompts(); renderRecap(); renderFoot(); initChat();

// 语言切换:静态元素由 applyLang 换属性,动态视图(nav/概览/时光轴/决策图/债/文件树/指令/footer)重渲染
window.onLangChange = function(){
  var cur = validView((location.hash || "").slice(1)) ? location.hash.slice(1) : "overview";
  buildNav(); renderOverview(); renderTimeline(); renderGraph(); renderDebt();
  renderFiletree(); renderPrompts(); renderRecap(); renderFoot();
  show(cur);
};
