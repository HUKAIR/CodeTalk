function buildNav(){
  var nav = document.getElementById("nav");
  nav.setAttribute("role", "tablist");
  nav.innerHTML = VIEWS.map(function(v){
    return '<button role="tab" data-v="'+v[0]+'" aria-controls="v-'+v[0]+'"'
      + ' aria-selected="false">'+t("view_"+v[0])+'</button>'; }).join("");
  document.querySelectorAll("#nav button").forEach(function(b){
    b.addEventListener("click", function(){ location.hash = b.getAttribute("data-v"); });
  });
}

// ---- ① 开工概览 ----
// 答案区可在「选项组」与「已记录 + 改答↺」两态间来回切换:set_capsule_outcome 是
// UPDATE,改答只是再 post 一次新 outcome,后端天然支持改写。
function capBtnsHtml(k){
  var h = '<div class="btns">';
  OUTCOMES.forEach(function(o){         // data-out 恒为规范中文(稳定写回键),标签按语言译
    h += '<button class="btn" data-k="'+k+'" data-out="'+esc(o[1])+'"'
      + (SERVE?"":" disabled")+'>'+esc(t(o[0]))+'</button>';
  });
  return h + '</div>';
}
function capDoneHtml(outcome){
  return '<span class="ago">'+t("recorded")+'</span>'
    + '<span style="color:var(--ok)">' + esc(outLabel(outcome)) + '</span>'
    + ' <span class="reanswer" role="button" tabindex="0">'+t("reanswer")+'</span>';
}
function wireCapAns(k){           // 给答案区当前内容(按钮 或 改答链接)接事件
  var ans = document.getElementById("ov-ans-"+k);
  if (!ans) return;
  ans.querySelectorAll(".btn").forEach(function(b){
    if (!SERVE) return;
    b.addEventListener("click", function(){
      var p = DATA.overview.pending[k];
      answerCapsule(p.capsule_id, b.getAttribute("data-out"), k); });
  });
  var re = ans.querySelector(".reanswer");
  if (re) onActivate(re, function(){              // 改答:恢复选项组重选重 post
    ans.innerHTML = capBtnsHtml(k); wireCapAns(k); });
}
function answerCapsule(capId, outcome, k){
  // 只在服务器确认写回(res.ok)后才落地「已记录」,失败则保留选项 + 提示重试,
  // 杜绝乐观更新造成的「UI 假成功、库里其实没写」静默数据丢失。
  var ans = document.getElementById("ov-ans-"+k);
  post("/capsule", {capsule_id:capId, outcome:outcome}).then(function(ok){
    if (ok){ ans.innerHTML = capDoneHtml(outcome); wireCapAns(k); }
    else ans.insertAdjacentHTML("beforeend",
      '<div class="ro" style="color:var(--warn)">' + esc(t("writeback_fail")) + '</div>');
  });
}
function actRow(go, q, sub){   // 首页动作行:用户问句 + 一句话作用 + 去处(复用 .jump 键盘可达)
  return '<div class="act jump" role="button" tabindex="0" data-go="'+esc(go)+'">'
    + '<div class="act-q">'+esc(q)+'<span class="act-go">→</span></div>'
    + '<div class="act-sub">'+esc(sub)+'</div></div>';
}
function renderOverview(){
  var o = DATA.overview, h = '';
  // Hero:上次停在哪(大字引文,英文衬线)
  h += '<div class="hero">';
  if (o.last){
    h += '<p class="lead">'+esc(o.last.overview)+'</p>';
    if (o.last.decision) h += '<p class="lead-sub">'+t("last_decision_label")+esc(o.last.decision)+'</p>';
  } else {
    h += '<p class="lead">'+t("no_digest_yet")+'</p>'
      + '<p class="lead-sub">'+t("run_digest_pre")+'<code>codetalk digest</code>'+t("run_digest_post")+'</p>';
  }
  h += '</div>';
  // 今日提醒:今天跑过 digest 没?(零-LLM:据 usage.log 最近一次本项目 digest 运行日期)
  if (o.last_digest){
    if (o.last_digest === o.today)
      h += '<div class="ran ok">'+t("ran_ok_pre")+'<code>codetalk digest</code>'+t("ran_ok_post")+'</div>';
    else
      h += '<div class="ran due">'+t("ran_due_pre")+'<code>codetalk digest</code>'+t("ran_due_mid")
        + esc(o.last_digest) + t("ran_due_post")+'</div>';
  }
  // Summary counts follow the actionable content.
  var cov = o.coverage ? (o.coverage[0]+'/'+o.coverage[1]) : '—';
  var debtTop = (o.debt_top && o.debt_top[0]) ? o.debt_top[0].debt : '—';
  function tile(val, label, go){
    var a = go ? ' class="tile jump" role="button" tabindex="0" data-go="'+esc(go)+'"'
               : ' class="tile"';
    return '<div'+a+'><div class="tnum">'+esc(String(val))+'</div>'
      + '<div class="tlbl">'+esc(label)+'</div></div>';
  }
  // 待验证胶囊
  if ((o.pending||[]).length){
    h += '<div class="card"><h3>'+t("pending_pre")+o.pending.length+t("pending_post")+'</h3>';
    o.pending.forEach(function(p, k){
      h += '<div class="cap-q" id="ov-cap-'+k+'"><span class="ago">'
        + '('+p.sha.slice(0,7)+')'+t("you_worried")+'</span>'+t("worried_open")+esc(p.risk)+t("worried_close")
        + '<div class="ans" id="ov-ans-'+k+'">'+capBtnsHtml(k)+'</div></div>';
    });
    if (!SERVE) h += '<div class="ro">'+t("readonly_hint")+'</div>';
    h += '</div>';
  }
  // 理解债 top
  if ((o.debt_top||[]).length){
    h += '<div class="card"><h3>'+t("debt_top3")+'<span class="jump" role="button"'
      + ' tabindex="0" data-go="debt">'+t("see_all")+'</span></h3>';
    o.debt_top.forEach(function(r){
      h += '<p><span class="sha">'+esc(r.file)+'</span> · '+t("w_debt")+' '+r.debt
        + ' · '+t("w_churn")+r.churn+'·'+t("w_reviewed")+r.reviewed+'/'+r.commits+'</p>';
    });
    h += '</div>';
  }
  // 「想弄清什么?」—— 用用户的问句措辞替代裸视图名(贴近 JTBD「这段代码当初为什么这么写」)
  h += '<div class="card"><h3>'+t("want_to_know")+'</h3><div class="acts">';
  if (CHAT)
    h += actRow('chat', t("act_chat_q"), t("act_chat_sub"));
  h += actRow('graph', t("act_graph_q"), t("act_graph_sub"))
     + actRow('filetree', t("act_filetree_q"), t("act_filetree_sub"))
     + '</div></div>';
  h += '<div class="tiles">'
    + tile((DATA.timeline||[]).length, 'COMMIT', 'timeline')
    + tile((o.pending||[]).length, t("tile_pending"))
    + tile(cov, t("tile_coverage"))
    + tile(debtTop, t("tile_debt"), 'debt')
    + '</div>';
  var el = document.getElementById("v-overview"); el.innerHTML = h;
  el.querySelectorAll(".jump").forEach(function(j){
    onActivate(j, function(){
      var go = j.getAttribute("data-go");
      if (go === "chat") openChat(); else location.hash = go;
    }); });
  (o.pending||[]).forEach(function(p, k){ wireCapAns(k); });
}

// ---- ② 时光轴 ----
function capTag(cap){
  if (cap.outcome) return '<span class="tag done">✓ '+esc(outLabel(cap.outcome))+'</span>';
  if (cap.opened) return '<span class="tag due">'+t("tag_due")+'</span>';
  return '<span class="tag">'+t("tag_notdue")+'</span>';
}
function rowBody(c){
  var h = '<p class="ro">'+(LANG === "zh" ? "以下为缓存解释，非原始记录。核对原始提交：" : "Cached interpretation, not source records. Inspect the original commit: ")+ '<code>git show '+esc(c.sha)+'</code></p>';
  if (c.what) h += '<div class="lbl">'+t("lbl_what")+'</div><p>'+esc(c.what)+'</p>';
  if (c.why) h += '<div class="lbl">'+t("lbl_why")+'</div><p>'+esc(c.why)+'</p>';
  if (c.decisions.length){ h += '<div class="lbl">'+t("lbl_decisions")+'</div><ol>';
    c.decisions.forEach(function(d){ h += '<li>'+esc(d)+'</li>'; }); h += '</ol>'; }
  if (c.risks.length){ h += '<div class="lbl">'+t("lbl_risks")+'</div><ol class="risks">';
    c.risks.forEach(function(r){ h += '<li>'+esc(r)+'</li>'; }); h += '</ol>'; }
  (c.capsules||[]).forEach(function(cap){
    h += '<div style="margin-top:6px">'+capTag(cap)+esc(cap.risk)+'</div>'; });
  if (!c.what && !c.why) h += '<p class="empty">'+t("no_narrative")+'</p>';
  if (CHAT) h += '<button class="askbtn" type="button">'+t("ask_this")+'</button>';
  return h;
}
function tlMatch(c){   // sha/subject/what/why/决策/待验证 任一含 TLQ(子串,已小写)
  var s = (c.sha+" "+c.subject+" "+(c.what||"")+" "+(c.why||"")+" "
    +(c.decisions||[]).join(" ")+" "+(c.risks||[]).join(" ")+" "+JSON.stringify(c.source||{})).toLowerCase();
  return s.indexOf(TLQ) >= 0;
}
var TLF = { crumb:false, risk:false, cap:false };   // 时光轴快捷过滤(与搜索 AND 组合)
function tlActive(){ return !!(TLQ || TLF.crumb || TLF.risk || TLF.cap); }
function tlPass(c){
  if (TLQ && !tlMatch(c)) return false;
  if (TLF.crumb && !((c.decisions||[]).length || ((c.source||{}).chosen||[]).length || ((c.source||{}).rejected||[]).length)) return false;
  if (TLF.risk && !((c.risks||[]).length || ((c.source||{}).watches||[]).length)) return false;
  if (TLF.cap && !((c.capsules||[]).length)) return false;
  return true;
}
function clearFilters(){    // Esc 一键清空:搜索词 + 全部 chip
  TLQ = ""; TLF.crumb = TLF.risk = TLF.cap = false;
  var q = document.getElementById("q"); if (q) q.value = "";
  document.querySelectorAll("#chips .chip").forEach(function(b){
    b.classList.remove("on"); b.setAttribute("aria-pressed", "false"); });
  renderTimeline();
}
// ---- ③ 决策图(渐进式:决策 → 点开下游影响)----
function renderGraph(){
  var g = DATA.graph || {nodes:[],edges:[]};
  var byId = {}; g.nodes.forEach(function(n){ byId[n.id] = n; });
  var down = {}; g.edges.forEach(function(e){ (down[e.from]=down[e.from]||[]).push(e.to); });
  var decs = g.nodes.filter(function(n){ return n.text; });
  var h = '<h2 class="vh">'+t("graph_head")+'</h2><p class="ro">'+(LANG === "zh" ? "连线表示后续提交触及相同文件，不代表已证实的因果关系。" : "Links mean later commits touched the same files, not proven causation.")+'</p><button id="clear-graph" type="button">'+(LANG === "zh" ? "清除选择" : "Clear selection")+'</button>';
  if (!decs.length){ document.getElementById("v-graph").innerHTML = h
    + '<p class="empty">'+t("no_decisions")+'</p>'; return; }
  decs.forEach(function(n, i){
    var d = down[n.id] || [];
    h += '<div class="dec '+(n.kind==="narrative"?"narrative":"")+'" id="gd'+i+'">'
      + '<div class="t" id="gt'+i+'" role="button" tabindex="0" aria-expanded="false"'
      + ' aria-controls="gdown'+i+'"><span class="meta">'+n.id+' · '+n.date+' · '
      + (n.kind==="breadcrumb"?t("kind_breadcrumb"):t("kind_narrative"))+(n.badge?" · "+esc(n.badge):"")+'</span><br>'
      + esc(n.text)+' <span class="imp">'+t("affects_pre")+d.length+t("affects_post")+'</span></div>'
      + '<div class="down" id="gdown'+i+'">'+(d.length?d.map(function(tgt){
          var tn = byId[tgt] || {subject:tgt};
          return '<div>'+tgt+' '+esc(tn.subject||"")+'</div>'; }).join(""):'<div>'+t("no_downstream")+'</div>')
      + (CHAT?'<button class="askbtn" type="button">'+t("ask_decision")+'</button>':'')
      + '</div></div>';
  });
  document.getElementById("v-graph").innerHTML = h;
  document.getElementById("clear-graph").onclick = function(){ document.querySelectorAll("#v-graph .dec.open").forEach(function(el){ el.classList.remove("open"); el.querySelector("[aria-expanded]").setAttribute("aria-expanded", "false"); }); };
  decs.forEach(function(n, i){ var el = document.getElementById("gt"+i);  // 不叫 t(i18n 翻译器)
    onActivate(el, function(){
      var open = document.getElementById("gd"+i).classList.toggle("open");
      el.setAttribute("aria-expanded", open ? "true" : "false"); });
    if (CHAT){ var ab = document.getElementById("gdown"+i).querySelector(".askbtn");
      if (ab) ab.addEventListener("click", function(){ openChatWith(n.id, n.text); }); }
  });
}

// ---- ④ 理解债 ----
// 下钻成真实构成(零-LLM 重派生):未回看的决策 commit + 到期待填胶囊。
// 降债只认真处理:填胶囊『已解决』为主信号;回看(点开即记账)显式标护栏弱信号。
// askbtn 经 asks 数组按 DOM 序闭包接线,不把决策原文塞进 HTML 属性(esc 不转义引号)。
