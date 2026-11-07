#!/usr/bin/env node
// SPDX-License-Identifier: LGPL-2.1-or-later
// A page on the local network where the session posts what it needs from the user (text and
// buttons) and the user answers from a phone; the session waits for the answer instead of
// polling the console. No dependencies; state lives in memory.
//
//   node tools/ask-server.js [port]                         (default 8787)
//   POST /ask    {"id","text","buttons":[...],"input":bool}   from this computer only
//   GET  /wait?after=N   blocks until answer N+1 exists, returns it (this computer only)
//   GET  /       the page; POST /answer {"id","button","text"} from the page
//   POST /message {"text"}  from the page: the user asks the session something. It is queued as an
//                answer with id "chat", so the session's /wait sees it like any other answer.
//   POST /reply  {"text"}   the session's reply, shown under the chat (this computer only)
'use strict';
const http = require('http');
const port = Number(process.argv[2] || 8787);
let question = null;           // {id, text, buttons, input, time}
const answers = [];            // [{n, id, button, text, time}]
const waiters = [];
const chat = [];               // [{from: 'vos'|'claude', text, time}], last 30 kept
function addChat(from, text) { chat.push({from, text, time: new Date().toISOString()}); if (chat.length > 30) chat.shift(); }

function local(req) {
  const a = req.socket.remoteAddress || '';
  return a === '127.0.0.1' || a === '::1' || a === '::ffff:127.0.0.1';
}
function body(req) {
  return new Promise((resolve, reject) => {
    // Bytes are joined before decoding: a multibyte character split across chunks stays whole.
    // A body that is not UTF-8 (Windows curl sends the ANSI code page) is refused, so accents
    // never reach the phone as replacement characters.
    const chunks = [];
    let size = 0;
    req.on('data', chunk => { chunks.push(chunk); size += chunk.length; if (size > 65536) req.destroy(); });
    req.on('end', () => {
      try {
        const data = new TextDecoder('utf-8', {fatal: true}).decode(Buffer.concat(chunks));
        resolve(data ? JSON.parse(data) : {});
      } catch (e) { reject(new Error('body is not UTF-8 JSON: ' + e.message)); }
    });
  });
}
function send(res, code, type, text) {
  res.writeHead(code, {'Content-Type': type, 'Cache-Control': 'no-store'});
  res.end(text);
}
function escape(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function page() {
  const q = question;
  const last = answers.length ? answers[answers.length - 1] : null;
  const content = q ? `
    <p class="q">${escape(q.text).replace(/\n/g, '<br>')}</p>
    <form id="f">
      ${q.input ? '<textarea name="text" rows="3" placeholder="Escribí acá (opcional)"></textarea>' : ''}
      <div class="b">${(q.buttons || []).map(b => `<button name="button" value="${escape(b)}">${escape(b)}</button>`).join('')}</div>
    </form>` : '<p class="q">No hay nada pendiente por ahora.</p>';
  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OrbisDesk</title>
<style>
 :root { --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --accent:#1f5fbf; --card:#fff; }
 @media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ececea; --muted:#9a9a94; --accent:#6ea2ff; --card:#21211f; } }
 body { margin:0; padding:16px; background:var(--bg); color:var(--fg); font:17px/1.4 -apple-system,system-ui,sans-serif; }
 .card { background:var(--card); border-radius:14px; padding:16px; max-width:560px; margin:0 auto; }
 h1 { font-size:15px; color:var(--muted); margin:0 0 8px; font-weight:600; }
 .q { white-space:normal; margin:0 0 16px; }
 textarea { width:100%; box-sizing:border-box; font:inherit; padding:10px; border-radius:10px; border:1px solid var(--muted); background:transparent; color:inherit; margin-bottom:12px; }
 .b { display:flex; flex-wrap:wrap; gap:10px; }
 button { flex:1 1 auto; min-height:48px; font:inherit; font-weight:600; border:0; border-radius:12px; background:var(--accent); color:#fff; padding:10px 14px; }
 button:not(:first-child) { background:transparent; color:var(--accent); border:2px solid var(--accent); }
 .chat { border-top:1px solid var(--muted); margin-top:16px; padding-top:12px; }
 .msg { margin:0 0 8px; } .msg.claude { color:var(--accent); }
 .last { color:var(--muted); font-size:14px; margin-top:14px; }
</style></head><body><div class="card">
<h1>OrbisDesk${q ? ' · ' + escape(q.id) : ''}</h1>${content}
<form id="m" class="chat">
  <h1>Preguntale a Claude</h1>
  ${chat.map(c => `<p class="msg ${c.from}"><b>${c.from === 'vos' ? 'Vos' : 'Claude'}:</b> ${escape(c.text).replace(/\n/g, '<br>')}</p>`).join('')}
  <textarea name="text" rows="2" placeholder="¿Cómo venís?"></textarea>
  <div class="b"><button>Enviar</button></div>
</form>
${last ? `<p class="last">Última respuesta: ${escape(last.button)}${last.text ? ' — ' + escape(last.text) : ''}</p>` : ''}
</div>
<script>
 const f = document.getElementById('f');
 if (f) f.addEventListener('submit', async e => {
   e.preventDefault();
   const button = e.submitter ? e.submitter.value : '';
   const text = f.text ? f.text.value : '';
   await fetch('/answer', {method:'POST', headers:{'Content-Type':'application/json'},
     body: JSON.stringify({id: ${JSON.stringify(q ? q.id : '')}, button, text})});
   location.reload();
 });
 const m = document.getElementById('m');
 m.addEventListener('submit', async e => {
   e.preventDefault();
   const text = m.text.value.trim();
   if (!text) return;
   await fetch('/message', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
   location.reload();
 });
 setTimeout(() => { if (!document.activeElement || document.activeElement.tagName !== 'TEXTAREA') location.reload(); }, 15000);
</script></body></html>`;
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  try {
    if (req.method === 'GET' && url.pathname === '/') return send(res, 200, 'text/html; charset=utf-8', page());
    if (req.method === 'POST' && url.pathname === '/answer') {
      const a = await body(req);
      if (!question || a.id !== question.id) return send(res, 409, 'text/plain', 'no such question');
      const entry = {n: answers.length + 1, id: question.id, button: String(a.button || '').slice(0, 200),
                     text: String(a.text || '').slice(0, 2000), time: new Date().toISOString()};
      answers.push(entry);
      question = null;
      console.log('answer ' + JSON.stringify(entry));
      while (waiters.length) waiters.shift()();
      return send(res, 200, 'text/plain', 'ok');
    }
    if (req.method === 'POST' && url.pathname === '/message') {
      const text = String((await body(req)).text || '').trim().slice(0, 2000);
      if (!text) return send(res, 400, 'text/plain', 'empty');
      const entry = {n: answers.length + 1, id: 'chat', button: 'Mensaje', text, time: new Date().toISOString()};
      answers.push(entry);
      addChat('vos', text);
      console.log('message ' + JSON.stringify(entry));
      while (waiters.length) waiters.shift()();
      return send(res, 200, 'text/plain', 'ok');
    }
    if (!local(req)) return send(res, 403, 'text/plain', 'forbidden');
    if (req.method === 'POST' && url.pathname === '/ask') {
      const q = await body(req);
      question = {id: String(q.id || 'q' + Date.now()), text: String(q.text || ''), buttons: q.buttons || ['Listo'],
                  input: !!q.input, time: new Date().toISOString()};
      console.log('ask ' + JSON.stringify(question));
      return send(res, 200, 'application/json', JSON.stringify({ok: true, answers: answers.length}));
    }
    if (req.method === 'POST' && url.pathname === '/reply') {
      const text = String((await body(req)).text || '').trim().slice(0, 4000);
      if (!text) return send(res, 400, 'text/plain', 'empty');
      addChat('claude', text);
      console.log('reply ' + JSON.stringify(text));
      return send(res, 200, 'application/json', JSON.stringify({ok: true}));
    }
    if (req.method === 'GET' && url.pathname === '/wait') {
      const after = Number(url.searchParams.get('after') || 0);
      const reply = () => send(res, 200, 'application/json', JSON.stringify(answers[after]));
      if (answers.length > after) return reply();
      waiters.push(reply);
      req.on('close', () => { const i = waiters.indexOf(reply); if (i >= 0) waiters.splice(i, 1); });
      return;
    }
    send(res, 404, 'text/plain', 'not found');
  } catch (e) {
    send(res, 400, 'text/plain', String(e));
  }
}).listen(port, '0.0.0.0', () => console.log('ask-server listening on ' + port));
