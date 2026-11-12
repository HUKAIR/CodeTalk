/* Keep original B interactions; all writes use existing real-backend contracts. */
function wireRoom(root,rows,c){
  function el(id){return document.getElementById(id);}
  function select(id){roomState.selected=id;renderTimeline();var chapter=document.querySelector('.chapter[aria-current="true"]');if(chapter)chapter.focus();}
  function source(){
    el('room-context').hidden=false;el('room-note').classList.add('lit');
    el('room-more-context').lastElementChild.textContent='−';
    el('room-more-context').focus();el('room-note').scrollIntoView({block:'nearest'});
  }
  el('room-mode-read').onclick=function(){roomBookmarksOnly=false;clearFilters();location.hash='timeline';el('room-mode-read').focus();};
  el('room-mode-saved').onclick=function(){roomBookmarksOnly=true;renderTimeline();location.hash='timeline';el('room-mode-saved').focus();};
  el('room-close').onclick=function(){el('room-compare').close();};
  root.querySelectorAll('[data-sha]').forEach(function(button){button.onclick=function(){select(button.dataset.sha);};});
  if(!c)return;
  var id=roomId(c);
  el('room-prev').onclick=function(){select(roomId(rows[rows.indexOf(c)-1]));};
  el('room-next-page').onclick=el('room-next').onclick=function(){select(roomId(rows[rows.indexOf(c)+1]));};
  el('room-bookmark').onclick=function(){var i=roomState.bookmarks.indexOf(id);if(i<0)roomState.bookmarks.push(id);else roomState.bookmarks.splice(i,1);saveRoom();renderTimeline();el('room-bookmark').focus();};
  ['room-folder','room-source-open','room-flow-source','room-citation','room-tray-source'].forEach(function(key){el(key).onclick=source;});
  el('room-more-context').onclick=function(){var closed=!el('room-context').hidden;el('room-context').hidden=closed;this.lastElementChild.textContent=closed?'＋':'−';el('room-note').classList.toggle('lit',!closed);};
  ['room-diff','room-flow-diff','room-tray-diff','room-mode-compare'].forEach(function(key){el(key).onclick=function(){location.hash='timeline';showRoomDiff(id);};});
  el('room-flow-files').onclick=function(){location.hash='filetree';};
  var ask=root.querySelector('.askbtn');if(ask)ask.onclick=function(){openChatWith(c.sha,c.subject);};
  el('room-read').onclick=function(){
    var button=this,receipt=el('room-receipt');button.disabled=true;
    post('/reviewed',{sha:id}).then(function(ok){
      button.disabled=false;
      if(ok){visited[c.sha]=1;store(visited);renderFoot();button.textContent=roomText('已回看 · 再记一次','Read · record again');button.classList.add('selected');receipt.textContent=roomText('已保存本机回看回执；这不是审查批准。','Reading receipt saved locally; this is not approval.');}
      else receipt.textContent=t('writeback_fail');
    });
  };
}
function roomDiffSides(diff){
  var before=[],after=[];
  (diff||'').split('\n').forEach(function(line){
    if(line[0]!=='+'||line.startsWith('+++'))before.push(line);
    if(line[0]!=='-'||line.startsWith('---'))after.push(line);
  });
  return {before:before.join('\n'),after:after.join('\n')};
}
function showRoomDiff(sha){
  if(!SERVE)return;
  var dialog=document.getElementById('room-compare'),body=document.getElementById('room-diff-body'),request=++roomDiffRequest;
  if(!dialog.open)dialog.showModal();body.innerHTML='<p class="compare-status">'+esc(t('searching'))+'</p>';
  fetch(apiPath('/api/commit/'+encodeURIComponent(sha))).then(function(r){if(!r.ok)throw Error();return r.json();}).then(function(data){
    if(request!==roomDiffRequest||!body.isConnected)return;
    var sides=roomDiffSides(data.diff),empty=roomText('此提交没有文本差异。','No text diff for this commit.');
    body.innerHTML='<div class="comparison"><div class="compare-layer b-after"><div class="compare-content"><span class="compare-stamp">'+roomText('改动后','After')+'</span><pre>'+esc(sides.after||empty)+'</pre></div></div><div class="compare-layer b-before" id="room-before"><div class="compare-content"><span class="compare-stamp">'+roomText('改动前','Before')+'</span><pre>'+esc(sides.before||empty)+'</pre></div></div><div class="compare-divider" id="room-divider"><span>↔</span></div></div><div class="compare-controls"><label for="room-range">'+roomText('拖动分界，对照真实增删行。','Drag the divider to compare changed lines.')+'</label><input class="compare-range" id="room-range" type="range" min="0" max="100" value="48"></div><details class="compare-original"><summary>'+roomText('原始统一 diff','Original unified diff')+'</summary><pre>'+esc(data.diff||empty)+'</pre></details>';
    document.getElementById('room-range').oninput=function(){document.getElementById('room-before').style.clipPath='inset(0 '+(100-this.value)+'% 0 0)';document.getElementById('room-divider').style.left=this.value+'%';var before=document.querySelector('#room-before .compare-content'),after=document.querySelector('#room-compare .b-after .compare-content');before.style.width=this.value+'%';after.style.marginLeft=this.value+'%';after.style.width=(100-this.value)+'%';};
  }).catch(function(){if(request===roomDiffRequest&&body.isConnected)body.innerHTML='<p class="compare-status">'+esc(t('search_fail'))+'</p>';});
}
function ftHide(){ searchRequest++; var p = document.getElementById("ftres"); if(p) p.hidden = true; document.querySelector(".b-search").open = true; document.getElementById("q").focus(); }
function ftSearch(q){
  if(!SERVE) return;
  q = (q || "").trim(); if(q.length < 2){ ftHide(); return; }
  var request = ++searchRequest, panel = document.getElementById("ftres"), body = document.getElementById("ftbody");
  panel.hidden = false; body.textContent = t("searching"); body.focus();
  fetch(apiPath("/api/search?q="+encodeURIComponent(q))).then(function(r){ if(!r.ok) throw Error(); return r.json(); }).then(function(data){
    if(request !== searchRequest) return;
    body.innerHTML = (data.results || []).map(function(row,i){
      var label = row.kind === "source" ? roomText("原始记录", "Original record") : row.kind === "conversation" ? roomText("会话记录", "Conversation") : roomText("缓存解释", "Cached interpretation");
      return '<article class="room-search-hit"><small>'+label+' / '+esc(row.sha)+'</small><h3>'+esc(row.title)+'</h3><pre>'+esc(row.text)+'</pre>'+(row.kind !== 'conversation' ? '<button data-result="'+i+'">'+roomText("打开原始提交", "Open original commit")+'</button>' : '')+'</article>';
    }).join('') || esc(t("no_result"));
    body.querySelectorAll('[data-result]').forEach(function(button){ button.onclick = function(){
      var row = data.results[Number(button.dataset.result)], record = DATA.timeline.find(function(c){ return roomId(c).startsWith(row.sha); });
      if(record){ roomState.selected = roomId(record); roomBookmarksOnly = false; clearFilters(); ftHide(); location.hash = 'timeline'; }
      else { location.hash = 'timeline'; showRoomDiff(row.sha); }
    }; });
  }).catch(function(){ if(request === searchRequest) body.textContent = t("search_fail"); });
}

document.addEventListener("keydown", function(event){
  if(event.key === "Escape" && !document.getElementById("ftres").hidden){ event.preventDefault(); ftHide(); }
});
