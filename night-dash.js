#!/usr/bin/env node
// night-dash.js — zero-dep localhost cockpit for a night-shift relay.
// Reads ~/night-logs/<date>/{status.json,events.ndjson,night-*.log} + the repo's
// NIGHT_QUEUE.md / AGENT_LOG.md / git, and renders a live monitoring view.
//
//   REPO=/path/to/repo PORT=4199 node night-dash.js
//   (REPO defaults to whatever the latest run's status.json points at)
//
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

const PORT = parseInt(process.env.PORT || '4199', 10);
const LOGROOT = path.join(os.homedir(), 'night-logs');

const read = (p) => { try { return fs.readFileSync(p, 'utf8'); } catch { return ''; } };
const jpar = (s) => { try { return JSON.parse(s); } catch { return null; } };

// newest run dir (by status.json mtime, else dir mtime)
function latestRunDir() {
  let dirs = [];
  try { dirs = fs.readdirSync(LOGROOT).map(d => path.join(LOGROOT, d)).filter(d => { try { return fs.statSync(d).isDirectory(); } catch { return false; } }); } catch { return null; }
  let best = null, bestT = -1;
  for (const d of dirs) {
    const sp = path.join(d, 'status.json');
    let t; try { t = fs.statSync(fs.existsSync(sp) ? sp : d).mtimeMs; } catch { continue; }
    if (t > bestT) { bestT = t; best = d; }
  }
  return best;
}

function repoFor(status) {
  return process.env.REPO || (status && status.repo) || process.argv[2] || process.cwd();
}
const git = (repo, args) => { try { return execSync(`git -C "${repo}" ${args}`, {encoding:'utf8', maxBuffer: 8*1024*1024}).trim(); } catch { return ''; } };

function nightBranch(repo, status) {
  if (status && status.branch) return status.branch;
  const b = git(repo, 'for-each-ref --sort=-committerdate --format=%(refname:short) refs/heads/night/');
  return b.split('\n').filter(Boolean)[0] || git(repo, 'rev-parse --abbrev-ref HEAD') || 'HEAD';
}

function parseTasks(repo) {
  const lines = read(path.join(repo, 'NIGHT_QUEUE.md')).split('\n');
  const tasks = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^- \[([ xX])\]\s*(?:\((claude|codex)\)\s*)?(.*)$/);
    if (!m) continue;
    let text = m[3];
    while (i + 1 < lines.length && /^\s+\S/.test(lines[i+1]) && !/^- \[/.test(lines[i+1])) text += ' ' + lines[++i].trim();
    tasks.push({ done: m[1].toLowerCase() === 'x', lane: m[2] || '', text: text.trim() });
  }
  return tasks;
}

function parseLog(repo) {
  const lines = read(path.join(repo, 'AGENT_LOG.md')).split('\n');
  const out = []; let cur = null;
  const isHead = (l) => /(claude|codex)/i.test(l) && (/^#{1,4}\s/.test(l) || /^\*\*.*\*\*\s*$/.test(l));
  for (const l of lines) {
    if (isHead(l)) { if (cur) out.push(cur); cur = { agent: /codex/i.test(l) ? 'codex' : 'claude', head: l.replace(/[#*]/g,'').trim(), body: [] }; }
    else if (cur) cur.body.push(l);
  }
  if (cur) out.push(cur);
  return out.map(e => ({ ...e, body: e.body.join('\n').trim() }));
}

function commits(repo, base, branch) {
  const range = base ? `${base}..${branch}` : `-15 ${branch}`;
  const out = git(repo, `log --format=%h%x09%ct%x09%s ${range}`);
  if (!out) return [];
  return out.split('\n').filter(Boolean).map(l => { const [h,t,...s] = l.split('\t'); return { sha:h, t:parseInt(t,10), subj:s.join('\t') }; });
}

function stats(repo, base, branch, log) {
  const ss = base ? git(repo, `diff --shortstat ${base}..${branch}`) : '';
  const files = (ss.match(/(\d+) files? changed/)||[])[1] || 0;
  const ins = (ss.match(/(\d+) insertions?/)||[])[1] || 0;
  const del = (ss.match(/(\d+) deletions?/)||[])[1] || 0;
  return { files:+files, ins:+ins, del:+del,
    byClaude: log.filter(e=>e.agent==='claude').length,
    byCodex: log.filter(e=>e.agent==='codex').length };
}

function events(dir) {
  const txt = read(path.join(dir, 'events.ndjson'));
  return txt.split('\n').filter(Boolean).map(jpar).filter(Boolean).slice(-40);
}

function transcriptTail(dir, n=120) {
  let logs = []; try { logs = fs.readdirSync(dir).filter(f=>/^night-.*\.log$/.test(f)); } catch {}
  if (!logs.length) return '';
  logs.sort(); const p = path.join(dir, logs[logs.length-1]);
  const lines = read(p).split('\n'); return lines.slice(-n).join('\n');
}

function snapshot() {
  const dir = latestRunDir();
  const status = dir ? jpar(read(path.join(dir,'status.json'))) : null;
  const repo = repoFor(status);
  const branch = nightBranch(repo, status);
  const base = status && status.base_sha;
  const tasks = parseTasks(repo);
  const log = parseLog(repo);
  const dirty = (git(repo,'status --porcelain').split('\n').filter(Boolean).length) || 0;
  return {
    now: Math.floor(Date.now()/1000),
    status, repo: path.basename(repo), repoPath: repo, branch, dirty,
    tasks, done: tasks.filter(t=>t.done).length, total: tasks.length,
    log, commits: commits(repo, base, branch),
    stats: stats(repo, base, branch, log),
    events: dir ? events(dir) : [],
    transcript: dir ? transcriptTail(dir) : '',
  };
}

function body(req){ return new Promise(r=>{ let b=''; req.on('data',d=>b+=d); req.on('end',()=>r(b)); }); }

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>night-shift cockpit</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{--bg:#0b0f14;--panel:#131a22;--line:#222c38;--mut:#8b98a8;--txt:#e6edf3;
--claude:#d98c4a;--codex:#3fb6a8;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
header{padding:12px 18px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center;
flex-wrap:wrap;position:sticky;top:0;background:var(--bg);z-index:5}
b{font-weight:600}.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px}
.mut{color:var(--mut)}.pill{border:1px solid var(--line);border-radius:99px;padding:2px 10px;font-size:12px}
.now{font-size:13px}.spin{animation:p 1.2s infinite}@keyframes p{50%{opacity:.4}}
.strip{display:flex;gap:8px;flex-wrap:wrap;padding:10px 18px;border-bottom:1px solid var(--line)}
.card{border:1px solid var(--line);border-radius:9px;padding:7px 11px;min-width:96px}
.card .k{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
.card .v{font-size:17px;margin-top:2px}.v.warn{color:var(--warn)}.v.bad{color:var(--bad)}.v.ok{color:var(--ok)}
.ctrls{display:flex;gap:8px;align-items:center;margin-left:auto}
input,button{font:inherit;background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:7px;padding:6px 10px}
button{cursor:pointer}button:hover{border-color:var(--mut)}button.stop{color:var(--bad);border-color:#5a2420}
.wrap{display:grid;grid-template-columns:360px 1fr;gap:0}@media(max-width:880px){.wrap{grid-template-columns:1fr}}
.col{padding:14px 18px}.col.l{border-right:1px solid var(--line)}
h2{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin:0 0 10px}
.bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin-bottom:12px}.bar>i{display:block;height:100%;background:var(--ok);transition:width .4s}
.task{display:flex;gap:9px;padding:8px 0;border-bottom:1px solid #1a222c;align-items:flex-start}
.task.done .t{color:var(--mut);text-decoration:line-through}.task .box{color:var(--mut)}.task.done .box{color:var(--ok)}
.lane{font-size:10.5px;padding:1px 7px;border-radius:99px;border:1px solid var(--line);white-space:nowrap}
.lane.claude{color:var(--claude);border-color:#5a3d22}.lane.codex{color:var(--codex);border-color:#1f4a45}.t{flex:1}
.msg{margin:0 0 14px;max-width:90%}.msg.codex{margin-left:auto}.who{font-size:11.5px;margin-bottom:3px;color:var(--mut)}
.msg.claude .who{color:var(--claude)}.msg.codex .who{color:var(--codex);text-align:right}
.bubble{border:1px solid var(--line);border-radius:12px;padding:9px 12px;background:var(--panel);white-space:pre-wrap;word-break:break-word;font-size:12.5px}
.msg.codex .bubble{background:#10211f;border-top-right-radius:3px}.msg.claude .bubble{border-top-left-radius:3px}
.bubble code{background:#0b0f14;padding:1px 5px;border-radius:5px}
.commit{padding:6px 0;border-bottom:1px solid #1a222c;font-size:12.5px;cursor:pointer}.commit:hover{color:#fff}
.sha{color:var(--codex)}.diff{white-space:pre-wrap;font-size:11.5px;background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:9px;margin:6px 0;display:none;overflow:auto;max-height:340px}
.diff .add{color:var(--ok)}.diff .del{color:var(--bad)}.diff .hh{color:var(--mut)}
.ev{font-size:12px;padding:3px 0;color:var(--mut)}.ev .kind{display:inline-block;width:62px;color:var(--txt)}
.ev.cap .kind,.ev.warn .kind{color:var(--warn)}.ev.stop .kind,.ev.error .kind{color:var(--bad)}.ev.round .kind{color:var(--codex)}
details summary{cursor:pointer;color:var(--mut);margin:6px 0}pre.tr{white-space:pre-wrap;font-size:11px;background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:300px;overflow:auto}
.empty{color:var(--mut);padding:16px 0}
</style></head><body>
<header>
  <b>🌙 night-shift</b>
  <span class="pill" id="repo">…</span><span class="pill" id="branch">…</span>
  <span class="now"><span class="dot" id="dot"></span><span id="state">…</span></span>
  <span class="mut" id="nowline"></span>
  <div class="ctrls">
    <input id="addbox" placeholder="add task… e.g. (claude) fix footer" size="34">
    <button onclick="addTask()">+ Task</button>
    <button class="stop" onclick="stopRun()">■ Stop</button>
  </div>
</header>
<div class="strip" id="strip"></div>
<div class="wrap">
  <div class="col l">
    <h2>Tasks <span id="count" class="mut"></span></h2>
    <div class="bar"><i id="prog"></i></div>
    <div id="tasklist"></div>
    <h2 style="margin-top:22px">Commits <span class="mut">(click = diff)</span></h2>
    <div id="commits"></div>
    <h2 style="margin-top:22px">Events</h2>
    <div id="events"></div>
  </div>
  <div class="col">
    <h2>AI ⇄ AI conversation</h2>
    <div id="feed"></div>
    <details><summary>▸ live transcript (raw agent output)</summary><pre class="tr" id="tr"></pre></details>
  </div>
</div>
<script>
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const md=s=>esc(s).replace(/\`([^\`]+)\`/g,'<code>$1</code>');
const ago=t=>{const s=Math.max(0,D.now-t);return s<60?s+'s':s<3600?(s/60|0)+'m':(s/3600|0)+'h';};
const hms=s=>{s=Math.max(0,s|0);const h=s/3600|0,m=(s%3600)/60|0;return h?h+'h'+m+'m':m+'m'+(s%60)+'s';};
let D={now:0}, open={};
function card(k,v,cls){return '<div class="card"><div class="k">'+k+'</div><div class="v '+(cls||'')+'">'+v+'</div></div>';}
async function tick(){
  let d; try{ d=await (await fetch('/api')).json(); }catch{ return; } D=d;
  const st=d.status||{}; repo.textContent=d.repo; branch.textContent=d.branch;
  const age=d.now-(st.last_update_epoch||0);
  let label,color,spin='';
  if(!d.status){label='no run yet';color='#666';}
  else if(!st.running){label='finished';color='var(--ok)';}
  else if(['claude','codex','starting'].includes(st.phase)){ if(age>180){label='stalled? '+st.phase;color='var(--bad)';}else{label=(st.note||st.phase);color='var(--claude)';spin='spin';} }
  else {label=st.note||st.phase;color='var(--warn)';}
  dot.style.background=color; state.textContent=label; state.className=spin;
  nowline.textContent = st.running ? ('round '+(st.round||0)+' · up '+hms(d.now-(st.started_epoch||d.now))+' · budget left '+hms((st.stop_epoch||d.now)-d.now)) : (st.branch?('ended · '+ago(st.last_update_epoch)+' ago'):'');
  // strip
  const s=d.stats||{}; const elapsedH=Math.max(.001,(d.now-(st.started_epoch||d.now))/3600);
  strip.innerHTML =
    card('done', d.done+'/'+d.total, d.done===d.total&&d.total?'ok':'') +
    card('commits', d.commits.length) +
    card('lines', '<span style="color:var(--ok)">+'+(s.ins||0)+'</span> <span style="color:var(--bad)">-'+(s.del||0)+'</span>') +
    card('files', s.files||0) +
    card('rounds', (st.rounds_done!=null?st.rounds_done:'–')) +
    card('cap hits', st.cap_events||0, (st.cap_events>0)?'warn':'') +
    card('uncommitted', d.dirty, d.dirty>0?'warn':'') +
    card('Claude / Codex', (s.byClaude||0)+' / '+(s.byCodex||0));
  // tasks
  count.textContent=d.total?('· '+d.done+'/'+d.total):''; prog.style.width=(d.total?100*d.done/d.total:0)+'%';
  tasklist.innerHTML=d.tasks.length?d.tasks.map(t=>'<div class="task '+(t.done?'done':'')+'"><span class="box">'+(t.done?'✓':'○')+'</span>'+(t.lane?'<span class="lane '+t.lane+'">'+t.lane+'</span>':'')+'<span class="t">'+md(t.text)+'</span></div>').join(''):'<div class="empty">no tasks — add one above</div>';
  // commits + diff toggles
  commits.innerHTML=d.commits.length?d.commits.map(c=>'<div><div class="commit" onclick="diff(\\''+c.sha+'\\')"><span class="sha">'+esc(c.sha)+'</span> '+esc(c.subj)+' <span class="mut">· '+ago(c.t)+' ago</span></div><div class="diff" id="d_'+c.sha+'">'+(open[c.sha]||'')+'</div></div>').join(''):'<div class="empty">no commits yet</div>';
  for(const k in open){const el=document.getElementById('d_'+k); if(el){el.style.display='block';el.innerHTML=open[k];}}
  // events
  events.innerHTML=d.events.length?d.events.slice().reverse().map(e=>'<div class="ev '+e.kind+'"><span class="kind">'+esc(e.kind)+'</span> <span class="mut">'+ago(e.t)+' '+(e.agent?'· '+e.agent:'')+'</span> '+esc(e.msg)+'</div>').join(''):'<div class="empty">no events</div>';
  // conversation
  feed.innerHTML=d.log.length?d.log.map(e=>'<div class="msg '+e.agent+'"><div class="who">'+(e.agent==='codex'?'Codex ▸':'◂ Claude')+' · '+esc(e.head)+'</div><div class="bubble">'+md(e.body||'(no detail)')+'</div></div>').join(''):'<div class="empty">no handoffs yet…</div>';
  tr.innerHTML=esc(d.transcript||'(no transcript)');
}
function colorDiff(t){return esc(t).split('\\n').map(l=>{if(/^\\+/.test(l)&&!/^\\+\\+\\+/.test(l))return '<span class="add">'+l+'</span>';if(/^-/.test(l)&&!/^---/.test(l))return '<span class="del">'+l+'</span>';if(/^@@|^diff |^index /.test(l))return '<span class="hh">'+l+'</span>';return l;}).join('\\n');}
async function diff(sha){const el=document.getElementById('d_'+sha);if(open[sha]){open[sha]='';el.style.display='none';el.innerHTML='';return;}const t=await (await fetch('/api/diff?sha='+sha)).text();open[sha]=colorDiff(t);el.innerHTML=open[sha];el.style.display='block';}
async function addTask(){const v=addbox.value.trim();if(!v)return;await fetch('/api/task',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text:v})});addbox.value='';tick();}
async function stopRun(){if(!confirm('Stop the night-shift loop after the current step?'))return;await fetch('/api/stop',{method:'POST'});tick();}
addbox.addEventListener('keydown',e=>{if(e.key==='Enter')addTask();});
tick(); setInterval(tick,2500); setInterval(()=>{D.now++;},1000);
</script></body></html>`;

http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname === '/api') { res.writeHead(200,{'content-type':'application/json'}); return res.end(JSON.stringify(snapshot())); }
  if (u.pathname === '/api/diff') {
    const sha = (u.searchParams.get('sha')||'').replace(/[^0-9a-f]/gi,'').slice(0,40);
    const snap = snapshot(); res.writeHead(200,{'content-type':'text/plain'});
    return res.end(sha ? git(snap.repoPath, `show ${sha} --stat -p --no-color`) || '(no diff)' : '(bad sha)');
  }
  if (u.pathname === '/api/task' && req.method === 'POST') {
    const b = jpar(await body(req)) || {}; const t = (b.text||'').replace(/[\r\n]+/g,' ').trim();
    if (t) { const snap = snapshot(); const f = path.join(snap.repoPath,'NIGHT_QUEUE.md');
      const line = /^- \[/.test(t) ? t : `- [ ] ${t}`;
      try { fs.appendFileSync(f, (read(f).endsWith('\n')?'':'\n') + line + '\n'); } catch {} }
    res.writeHead(200,{'content-type':'application/json'}); return res.end('{"ok":true}');
  }
  if (u.pathname === '/api/stop' && req.method === 'POST') {
    const dir = latestRunDir(); if (dir) { try { fs.writeFileSync(path.join(dir,'STOP'),'stop'); } catch {} }
    res.writeHead(200,{'content-type':'application/json'}); return res.end('{"ok":true}');
  }
  res.writeHead(200,{'content-type':'text/html'}); res.end(PAGE);
}).listen(PORT,'127.0.0.1',()=>console.log(`night-dash cockpit → http://localhost:${PORT}`));
