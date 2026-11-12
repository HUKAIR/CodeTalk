
    var DATA = $data;
    var STARTED = Date.now();
    if (DATA.workspace) {
      var back = document.createElement("a"); back.href = "/console#timeline";
      back.dataset.uiZh = "← 决策书房"; back.dataset.uiEn = "← Reading room";
      back.textContent = "← 决策书房";
      document.querySelector(".ui-sections").prepend(back);
    }
    var TEXT = {
      en: { local:"LOCAL / NO TELEMETRY", title:"Decision review",
        subtitle:"Resolve the evidence before the change ships.", total:"cards", resolved:"resolved",
        conflict:"Potential conflict", context:"Decision context", empty:"No decision evidence",
        changeTitle:"Current change", evidence:"Historical record", rejected:"Previously rejected", chosen:"Chosen direction",
        interpretation:"Generated interpretation - not evidence", provenance:"Provenance",
        sources:"Original sources", primary:"Primary source", supporting:"Supporting source",
        commit:"Commit", diff:"Diff", note:"Decision note", test:"Test", pr:"Pull request", session:"Session",
        judgment:"Maintainer judgment", confirmed:"Confirmed conflict", exception:"Intentional exception",
        unrelated:"Unrelated", insufficient:"Insufficient evidence", changed:"Did this change the proposed action?",
        yes:"Yes", no:"No", save:"Save judgment", saved:"Saved locally", saving:"Saving…", failed:"Could not save. Your selection is kept; retry.",
        choose:"Select a judgment", actionRequired:"Record whether the action changed",
        verified:"Verified interception", feedback:"Sanitized feedback", comment:"Optional comment",
        approve:"Include redacted comment", preview:"Preview feedback", export:"Export JSON",
        exported:"Downloaded locally", previewFailed:"Could not prepare feedback", none:"No review cards for this diff. Check your local changes and evidence coverage; this is not a safety verdict." },
      zh: { local:"仅本机 / 无遥测", title:"决策审查", subtitle:"在改动提交前完成人工判断。",
        total:"张卡片", resolved:"已判断", conflict:"潜在冲突", context:"决策上下文", empty:"没有决策证据",
        changeTitle:"这次改了什么", evidence:"历史记录", rejected:"曾否决", chosen:"当时选择", interpretation:"生成解释（非证据）",
        provenance:"溯源关联", sources:"原始来源", primary:"主要来源", supporting:"补充来源",
        commit:"Commit", diff:"Diff", note:"决策记录", test:"测试", pr:"Pull Request", session:"会话原话",
        judgment:"我的判断（人工）", confirmed:"确认冲突", exception:"有意例外", unrelated:"无关",
        insufficient:"证据不足", changed:"这次判断是否改变了原计划？", yes:"是", no:"否",
        save:"保存判断", saved:"已保存到本机", saving:"正在保存…", failed:"保存失败，已保留选择，请重试。", choose:"请选择一种判断",
        actionRequired:"请记录是否改变了原计划", verified:"已验证拦截", feedback:"脱敏反馈",
        comment:"可选评论", approve:"包含脱敏后的评论", preview:"预览反馈", export:"导出 JSON",
        exported:"已下载到本机", previewFailed:"无法生成反馈", none:"当前差异没有审查卡片。请检查本地改动和证据覆盖；这不代表改动已通过安全检查。" }
    };
    var LANG = (function(){ try { var saved = localStorage.getItem("codetalk.lang");
      if (saved === "en" || saved === "zh") return saved; } catch(e) {}
      return (navigator.language || "").slice(0,2).toLowerCase() === "zh" ? "zh" : "en"; })();
    function t(key){ return TEXT[LANG][key] || TEXT.en[key] || key; }
    function esc(value){ return String(value == null ? "" : value).replace(/&/g,"&amp;")
      .replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
    function arr(value){ return Array.isArray(value) ? value : []; }
    function list(items){ return arr(items).map(function(item){ return "<li>" + esc(item) + "</li>"; }).join(""); }
    function sourceRow(type, value, pre){ if (value == null || value === "" || (Array.isArray(value) && !value.length)) return "";
      var body = pre ? "<pre>" + esc(value) + "</pre>" : '<div class="source-value">' + esc(value) + "</div>";
      return '<div class="source-row"><div class="source-type">' + esc(type) + "</div>" + body + "</div>"; }
    function sourceRecord(source, title){
      if (!source) return "";
      var h = '<div class="source-group"><div class="source-title">' + esc(title) + "</div>";
      h += sourceRow(t("commit"), [source.sha, source.date, source.subject].filter(Boolean).join(" / "));
      var notes = source.decision_notes || {};
      arr(notes.rejected).forEach(function(v){ h += sourceRow(t("note"), t("rejected") + ": " + v); });
      arr(notes.chosen).forEach(function(v){ h += sourceRow(t("note"), t("chosen") + ": " + v); });
      arr(source.tests).forEach(function(v){ v = v || {}; h += sourceRow(t("test"), [v.path, arr(v.names).join(", ")].filter(Boolean).join(" / ")); });
      arr(source.pull_requests).forEach(function(v){ v = v || {}; h += sourceRow(t("pr"), [v.number ? "#" + v.number : "", v.title, v.snippet].filter(Boolean).join(" / ")); });
      arr(source.sessions).forEach(function(v){ v = v || {}; var parts = [v.source, v.ts];
        arr(v.prompts).forEach(function(p){ parts.push(p); }); arr(v.excerpts).forEach(function(p){ parts.push(p); });
        h += sourceRow(t("session"), parts.filter(Boolean).join("\n")); });
      return h + "</div>";
    }
    function sourcesHtml(card){
      var evidence = card.evidence || {}, h = "";
      h += sourceRecord(evidence.primary, t("primary"));
      arr(evidence.supporting).forEach(function(v, i){ h += sourceRecord(v, t("supporting") + " " + (i + 1)); });
      return '<details><summary>' + esc(t("sources")) + '</summary><div class="sources">' + h + "</div></details>";
    }
    function evidenceHtml(card){
      var primary = (card.evidence || {}).primary || {}, notes = primary.decision_notes || {}, h = "";
      arr(notes.rejected).forEach(function(v){ h += '<div class="decision"><b>' + esc(t("rejected")) + "</b>" + esc(v) + "</div>"; });
      arr(notes.chosen).forEach(function(v){ h += '<div class="decision chosen"><b>' + esc(t("chosen")) + "</b>" + esc(v) + "</div>"; });
      return h || '<div class="decision chosen">' + esc(primary.subject || t("empty")) + "</div>";
    }
    function interpretationHtml(value){ if (!value) return ""; var h = "";
      if (value.summary) h += "<p>" + esc(value.summary) + "</p>";
      if (arr(value.rejected).length || arr(value.decisions).length) h += "<ul>" + list(value.rejected) + list(value.decisions) + "</ul>";
      return '<section class="section" data-section="interpretation"><div class="label">' + esc(t("interpretation"))
        + '</div><div class="interpretation"><div class="notice">' + esc(t("interpretation")) + "</div>" + h + "</div></section>"; }
    function choice(name, value, label, checked){ return '<label class="choice"><input type="radio" name="' + esc(name)
      + '" value="' + esc(value) + '"' + (checked ? " checked" : "") + ">" + esc(label) + "</label>"; }
    function feedbackHtml(saved, i){ return '<section class="feedback' + (saved.status ? " visible" : "") + '" id="feedback-' + i + '"><div class="label">' + esc(t("feedback"))
      + '</div><label><span>' + esc(t("comment")) + '</span><textarea maxlength="500" id="comment-' + i + '"></textarea></label><label class="approve"><input type="checkbox" id="approve-' + i + '">' + esc(t("approve"))
      + '</label><div class="feedback-actions"><button class="preview-button" type="button" id="preview-button-' + i + '">' + esc(t("preview")) + '</button><button class="export-button" type="button" id="export-button-' + i + '" disabled>' + esc(t("export"))
      + '</button></div><div class="feedback-preview" id="feedback-preview-' + i + '"></div><a hidden id="download-' + i + '" download="codetalk-review-feedback.json"></a><div class="saved" id="feedback-status-' + i + '"></div></section>'; }
    function judgmentHtml(card, i){ var saved = DATA.judgments[card.id] || {}, name = "judgment-" + i;
      var h = '<form data-review-form="' + i + '"><fieldset><legend>' + esc(t("judgment")) + '</legend><div class="choices">';
      [["confirmed_conflict","confirmed"],["intentional_exception","exception"],["unrelated","unrelated"],["insufficient_evidence","insufficient"]]
        .forEach(function(v){ h += choice(name, v[0], t(v[1]), saved.status === v[0]); });
      h += '</div></fieldset><div class="action' + (saved.status === "confirmed_conflict" ? " visible" : "") + '" id="action-' + i + '"><div class="action-title">' + esc(t("changed")) + '</div><div class="binary">';
      h += choice("changed-" + i, "true", t("yes"), saved.action_changed === true);
      h += choice("changed-" + i, "false", t("no"), saved.action_changed === false);
      h += '</div></div><button class="save" type="submit">' + esc(t("save")) + '</button><div class="saved" role="status" id="saved-' + i + '">'
        + (saved.status ? esc(t("saved")) : "") + '</div><div class="verified' + (saved.verified_interception ? " visible" : "")
        + '" id="verified-' + i + '">' + esc(t("verified")) + "</div></form>"; return h; }
    function cardHtml(card, i){ var kindKey = card.kind === "potential_conflict" ? "conflict" : (card.kind === "decision_context" ? "context" : "empty");
      var change = card.change || {}, saved = DATA.judgments[card.id] || {}, location = (change.file || "") + ":" + (change.start || "") + "-" + (change.end || "");
      var h = '<article class="card"><header class="card-head"><div><div class="kind ' + esc(kindKey) + '">' + esc(t(kindKey))
        + '</div><div class="location">' + esc(location) + '</div></div><div class="card-id">' + esc(card.id) + "</div></header>";
      h += '<div class="card-body"><div class="main-column"><section class="section"><div class="label">' + esc(t("changeTitle")) + '</div><pre>' + esc(change.diff || t("empty")) + '</pre></section><section class="section" data-section="evidence"><div class="label">'
        + esc(t("evidence")) + "</div>" + evidenceHtml(card) + "</section>" + interpretationHtml(card.interpretation);
      h += sourcesHtml(card) + '</div><aside class="side-column"><section class="section" data-section="provenance"><div class="label">'
        + esc(t("provenance")) + '</div><div class="provenance"><strong>' + esc((card.provenance || {}).label || "")
        + "</strong>" + esc((card.association || {}).reason || "") + "</div></section>" + judgmentHtml(card, i) + "</aside></div>" + feedbackHtml(saved, i) + "</article>"; return h; }
    function updateCounts(){
      var resolved = Object.keys(DATA.judgments || {}).filter(function(k){ return DATA.judgments[k] && DATA.judgments[k].status; }).length;
      document.getElementById("counts").innerHTML = "<span><strong>" + DATA.cards.length + "</strong> " + esc(t("total")) + "</span><span><strong>" + resolved + "</strong> " + esc(t("resolved")) + "</span>";
    }
    function render(){ document.documentElement.lang = LANG; document.querySelectorAll("[data-i18n]").forEach(function(el){ el.textContent = t(el.dataset.i18n); });
      document.getElementById("lang").textContent = LANG === "en" ? "中" : "EN"; updateCounts();
      document.getElementById("cards").innerHTML = DATA.cards.length ? DATA.cards.map(cardHtml).join("") : '<div class="empty-state">' + esc(t("none")) + "</div>";
      wire(); }
    function feedbackPayload(card, i){ return {card_id:card.id,approved_comment:document.getElementById("approve-" + i).checked ? document.getElementById("comment-" + i).value : null}; }
    function wireFeedback(card, i){ var previewReady = false, box = document.getElementById("feedback-" + i), preview = document.getElementById("feedback-preview-" + i), status = document.getElementById("feedback-status-" + i), exportButton = document.getElementById("export-button-" + i);
      function invalidate(){ previewReady = false; exportButton.disabled = true; preview.innerHTML = ""; status.textContent = ""; }
      [document.getElementById("comment-" + i), document.getElementById("approve-" + i)].forEach(function(el){ el.addEventListener("input", invalidate); el.addEventListener("change", invalidate); });
      document.getElementById("preview-button-" + i).addEventListener("click", function(){ fetch(apiPath("/feedback/preview"), {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(feedbackPayload(card,i))}).then(function(r){ if(!r.ok) throw new Error(); return r.json(); }).then(function(body){ preview.innerHTML = Object.keys(body.feedback).map(function(k){ return '<div class="preview-row"><b>' + esc(k).replace(/_/g,"_<wbr>") + '</b><span>' + esc(JSON.stringify(body.feedback[k])).replace(/_/g,"_<wbr>") + '</span></div>'; }).join(""); previewReady = true; exportButton.disabled = false; }).catch(function(){ invalidate(); status.textContent = t("previewFailed"); }); });
      exportButton.addEventListener("click", function(){ if(!previewReady) return; fetch(apiPath("/feedback/export"), {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(feedbackPayload(card,i))}).then(function(r){ if(!r.ok) throw new Error(); return r.blob(); }).then(function(blob){ var link=document.getElementById("download-"+i), url=URL.createObjectURL(blob); link.href=url; link.click(); setTimeout(function(){ URL.revokeObjectURL(url); },0); status.textContent=t("exported"); }).catch(function(){ status.textContent=t("previewFailed"); }); });
      return {show:function(){ box.classList.add("visible"); invalidate(); },invalidate:invalidate}; }
    function wire(){ DATA.cards.forEach(function(card, i){ var form = document.querySelector('[data-review-form="' + i + '"]'), feedback = wireFeedback(card, i);
      var action = document.getElementById("action-" + i); form.querySelectorAll("input").forEach(function(input){ input.addEventListener("change", feedback.invalidate); }); form.querySelectorAll('input[name="judgment-' + i + '"]').forEach(function(input){ input.addEventListener("change", function(){ action.classList.toggle("visible", input.value === "confirmed_conflict" && input.checked); }); });
      form.addEventListener("submit", function(event){ event.preventDefault(); var picked = form.querySelector('input[name="judgment-' + i + '"]:checked');
        var message = document.getElementById("saved-" + i); if (form.dataset.saving === "true") return; if (!picked){ message.textContent = t("choose"); return; }
        var changed = null; if (picked.value === "confirmed_conflict"){ var actionInput = form.querySelector('input[name="changed-' + i + '"]:checked');
          if (!actionInput){ message.textContent = t("actionRequired"); return; } changed = actionInput.value === "true"; }
        var button = form.querySelector("button"); button.disabled = true; form.dataset.saving = "true"; document.getElementById("lang").disabled = true; form.querySelectorAll("input").forEach(function(input){ input.disabled = true; }); message.dataset.state = "pending"; message.textContent = t("saving"); button.textContent = t("saving");
        fetch(apiPath("/judgment"), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({card_id:card.id,status:picked.value,action_changed:changed,elapsed_seconds:(Date.now()-STARTED)/1000})})
          .then(function(response){ if (!response.ok) throw new Error(); return response.json(); })
          .then(function(body){ DATA.judgments[card.id] = body.judgment; message.textContent = t("saved"); message.dataset.state = "success";
            document.getElementById("verified-" + i).classList.toggle("visible", body.judgment.verified_interception); feedback.show(); updateCounts(); })
          .catch(function(){ message.textContent = t("failed"); message.dataset.state = "error"; }).finally(function(){ button.disabled = false; form.dataset.saving = "false"; document.getElementById("lang").disabled = !!document.querySelector('[data-saving="true"]'); form.querySelectorAll("input").forEach(function(input){ input.disabled = false; }); button.textContent = t("save"); }); }); }); }
    document.getElementById("lang").addEventListener("click", function(){ LANG = LANG === "en" ? "zh" : "en";
      try { localStorage.setItem("codetalk.lang", LANG); } catch(e) {} render(); });
    render();
