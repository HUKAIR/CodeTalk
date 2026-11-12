/* Original B layout, driven by the existing real Git/cache contract. */
function roomText(zh, en) { return LANG === "zh" ? zh : en; }
var roomKey = VKEY + ".reading", roomState = {};
try { roomState = JSON.parse(localStorage.getItem(roomKey)) || {}; } catch(e) {}
if (!roomState || typeof roomState !== "object" || Array.isArray(roomState)) roomState = {};
if (!Array.isArray(roomState.bookmarks)) roomState.bookmarks = [];
var roomBookmarksOnly = false, roomDiffRequest = 0, searchRequest = 0;
function saveRoom() { try { localStorage.setItem(roomKey, JSON.stringify(roomState)); } catch(e) {} }
function roomId(c) { return c.full_sha || c.sha; }
function roomIcon(name) {
  var paths = {layers:'m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 17l10 5 10-5',
    pin:'m8 3 8 0-1 6 4 4H5l4-4ZM12 13v9',arrow:'M5 12h14m-5-5 5 5-5 5',
    check:'m5 12 4 4L19 6',close:'m5 5 14 14M5 19 19 5',
    book:'M12 5v16M12 5C8 2 3 3 2 4v16c5-2 8 0 10 1 2-1 5-3 10-1V4c-5-2-8 0-10 1'};
  return '<svg class="b-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="'+paths[name]+'"/></svg>';
}
function renderTimeline() {
  var root = document.getElementById("v-timeline");
  root.replaceChildren(document.getElementById("room-template").content.cloneNode(true));
  root.querySelectorAll('[data-room-zh]').forEach(function(el){ el.textContent = roomText(el.dataset.roomZh,el.dataset.roomEn); });
  root.querySelectorAll('[data-room-icon]').forEach(function(el){ el.innerHTML = roomIcon(el.dataset.roomIcon); });
  var rows = DATA.timeline.filter(function(c){ return tlPass(c) && (!roomBookmarksOnly || roomState.bookmarks.indexOf(roomId(c)) >= 0); });
  var c = rows.find(function(r){ return roomId(r) === roomState.selected; }) || rows[0];
  function el(id){ return document.getElementById(id); }
  function put(id,text){ el(id).textContent = text; }
  [['room-prev','上一篇','Previous entry'],['room-next','下一篇','Next entry'],['room-citation','查看引用','View source'],['room-close','关闭对照','Close comparison'],['chapter-list','提交章节','Commit chapters']].forEach(function(a){el(a[0]).setAttribute('aria-label',roomText(a[1],a[2]));});
  put('room-total',rows.length+' / '+DATA.timeline.length+roomText(' 篇',' entries'));
  put('room-bookmark-count',roomState.bookmarks.length);
  put('room-mode-note',roomText(SERVE ? '阅读回执写入本机' : '静态档案 · 只读', SERVE ? 'Reading receipts saved locally' : 'Static archive · read only'));
  el('chapter-list').innerHTML = rows.map(function(r,i){ return '<button class="chapter '+(r===c?'active':'')+'" data-sha="'+esc(roomId(r))+'" aria-current="'+(r===c)+'"><span class="chapter-no">'+String(i+1).padStart(2,'0')+'</span><span><b>'+esc(r.subject)+'</b><small>'+esc(r.day)+' · '+esc(((r.source||{}).files||[])[0] || r.sha)+'</small></span></button>'; }).join('') || '<p class="b-tiny b-muted">'+roomText(roomBookmarksOnly?'还没有书签。先从阅读页留下一个书签。':'没有匹配的记录。','No matching records. Add bookmarks from the reading view.')+'</p>';
  el('room-mode-read').classList.toggle('active',!roomBookmarksOnly);
  el('room-mode-saved').classList.toggle('active',roomBookmarksOnly);
  el('room-review').href = apiPath('/review');
  if(!SERVE){ el('room-review').removeAttribute('href'); el('room-review').setAttribute('aria-disabled','true'); }
  ['room-diff','room-flow-diff','room-tray-diff','room-mode-compare','room-read'].forEach(function(id){ el(id).disabled = !SERVE || !c; });
  ['room-bookmark','room-folder','room-source-open','room-flow-source','room-citation','room-more-context','room-tray-source'].forEach(function(id){ el(id).disabled = !c; });
  el('room-flow-files').disabled = !c;
  put('room-receipt',roomText(SERVE ? '回看不等于批准；审查判断另有保存回执。' : '只读档案；运行 console --serve 可对照与写回。', SERVE ? 'Reading is not approval; judgments have a separate receipt.' : 'Read only; use console --serve for diffs and writes.'));
  if(c){
    roomState.selected = roomId(c); saveRoom();
    var source = c.source || {}, files = source.files || [], chosen = source.chosen || [], rejected = source.rejected || [];
    var pos = rows.indexOf(c), body = source.body || c.subject;
    put('room-chapter-label',files[0] || c.sha);
    put('room-number',String(pos+1).padStart(2,'0')); put('room-date',c.day);
    put('room-title',c.subject); put('room-file-count',String(files.length).padStart(2,'0'));
    put('room-summary',chosen[0] || roomText('这是一条原始提交记录。展开旁注，回读完整说明。','An original commit. Expand the source note to read its full message.'));
    put('room-cube-sha','SHA · '+c.sha);
    put('room-body-copy',chosen.join('\n\n') || roomText('这条提交未记录明确的决策理由。','No explicit decision rationale was recorded in this commit.'));
    put('room-note-title',roomText('回到这次提交','Back to this commit'));
    put('room-quote',chosen[0] || c.subject); put('room-note-source','Git · '+c.sha);
    put('room-context',body); put('room-sha',c.sha+' · '+(files.join(', ') || roomText('没有文件记录','No file records')));
    put('room-rejected',rejected.join('\n\n') || roomText('这条记录没有写下否决理由。','No rejected alternative was recorded.'));
    put('room-watches',(source.watches || []).length ? roomText('待验证\n','To verify\n')+source.watches.join('\n') : '');
    put('room-position',String(pos+1).padStart(2,'0')+' / '+String(rows.length).padStart(2,'0'));
    put('room-first-date',rows[rows.length-1].day.slice(5)); put('room-last-date',rows[0].day.slice(5));
    el('room-ruler-track').innerHTML = rows.map(function(r,i){ return '<button data-sha="'+esc(roomId(r))+'" class="'+(r===c?'active':'')+'" aria-label="'+esc(roomText('阅读第 ','Read entry ')+(i+1))+'"></button>'; }).join('');
    el('room-interpretation-body').innerHTML = rowBody(c);
    el('room-bookmark').setAttribute('aria-pressed',roomState.bookmarks.indexOf(roomId(c))>=0);
    el('room-bookmark').setAttribute('aria-label',roomText('切换书签','Toggle bookmark'));
    if(visited[c.sha]) put('room-read',roomText('已回看 · 再记一次','Read · record again'));
  } else {
    put('room-title',t(DATA.timeline.length ? 'no_hits' : 'no_commits'));
    put('room-summary',roomText('回到“阅读”或清空筛选，查看项目的原始记录。','Return to Read or clear filters to see the original records.'));
    root.querySelector('.artifact').hidden = true; root.querySelector('.page-body').hidden = true;
    root.querySelector('.archive-seal').hidden = true; root.querySelector('.margin-notes').hidden = true;
    root.querySelector('.room-interpretation').hidden = true;
  }
  ['room-next','room-next-page'].forEach(function(id){el(id).disabled = !c || rows.indexOf(c)===rows.length-1;});
  el('room-prev').disabled = !c || rows.indexOf(c)===0;
  wireRoom(root,rows,c);
}
