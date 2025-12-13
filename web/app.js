// Minimal utilities and UI wiring for the web UI (no external libs)
const API_BASE = '';

function _headers(opts){
  const h = { 'accept':'application/json' };
  const apiKey = localStorage.getItem('api_key');
  if (apiKey) h['x-api-key'] = apiKey;
  if (opts && opts.admin){
    const admin = sessionStorage.getItem('admin_token');
    if (admin) h['x-admin-token'] = admin;
  }
  return h;
}

async function getJSON(path, opts) {
  const r = await fetch(API_BASE + path, { headers: _headers(opts) });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return r.json();
}

async function postJSON(path, body, opts) {
  const h = _headers(opts); h['content-type'] = 'application/json';
  const r = await fetch(API_BASE + path, {
    method: 'POST',
    headers: h,
    body: JSON.stringify(body || {})
  });
  if (!r.ok) {
    let t = await r.text().catch(()=> '');
    throw new Error(`POST ${path} failed: ${r.status} ${t}`);
  }
  return r.json();
}

function $(sel, root=document){ return root.querySelector(sel); }
function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }

function qs() {
  const o = {}; const u = new URL(location.href);
  u.searchParams.forEach((v,k)=> o[k]=v);
  return o;
}

function setActiveNav() {
  const p = location.pathname;
  $all('.nav a').forEach(a => {
    if (p.endsWith(a.getAttribute('href'))) a.classList.add('active');
  });
}

async function renderBanner() {
  try {
    const [h, w] = await Promise.all([
      getJSON('/v1/health'),
      getJSON('/v1/whoami')
    ]);
    const el = $('.banner');
    if (!el) return;
    let net = 'Unknown';
    if (h.rpc_url && h.rpc_url.includes('coston2')) net = 'Coston2 Testnet';
    else if (h.rpc_url && h.rpc_url.includes('flare-api')) net = 'Flare Mainnet';
    const short = (x)=> x ? (x.slice(0,10)+'...'+x.slice(-6)) : '-';
    const proj = (w && w.project_id)
      ? `Scope: <span class="tag ok mono">${w.project_id}</span>`
      : 'Scope: <span class="tag">Public (all receipts)</span>';
    el.innerHTML = `Network: <b>${net}</b> · Contract: <span class="mono">${short(h.contract)}</span> · ${proj}`;
  } catch(e) {
    // ignore
  }
}

document.addEventListener('DOMContentLoaded', () => {
  setActiveNav();
  renderBanner();
  injectSettings();
});

function injectSettings(){
  // add Settings/Admin links if not present
  const nav = document.querySelector('.nav');
  if (nav && !document.getElementById('settings_link')){
    const a = document.createElement('a'); a.id='settings_link'; a.href='#'; a.textContent='Settings'; nav.appendChild(a);
    const b = document.createElement('a'); b.id='admin_link'; b.href='/web/admin.html'; b.textContent='Admin'; nav.appendChild(b);
    a.addEventListener('click', (e)=>{ e.preventDefault(); openSettings(); });
  }
}

function openSettings(){
  const wrap = document.createElement('div');
  wrap.style.position='fixed';wrap.style.inset='0';wrap.style.background='rgba(0,0,0,.5)';wrap.style.zIndex='9999';
  wrap.innerHTML = `
    <div style="max-width:520px;margin:10% auto;background:#151a22;border:1px solid #263042;border-radius:10px;padding:16px;">
      <h3 style="margin:0 0 12px 0">Settings</h3>
      <div class="split">
        <div class="col">
          <div class="label">Project API Key</div>
          <input id="set_api_key" placeholder="pk_..."/>
          <div class="small muted">Stored in this browser (localStorage)</div>
        </div>
        <div class="col">
          <div class="label">Admin Token</div>
          <input id="set_admin_tok" placeholder="admin token"/>
          <div class="small muted">Session only (not persisted)</div>
        </div>
      </div>
      <div class="row" style="gap:8px;margin-top:12px;justify-content:flex-end">
        <button class="btn" id="set_cancel">Close</button>
        <button class="btn primary" id="set_save">Save</button>
      </div>
    </div>`;
  document.body.appendChild(wrap);
  document.getElementById('set_api_key').value = localStorage.getItem('api_key')||'';
  document.getElementById('set_admin_tok').value = sessionStorage.getItem('admin_token')||'';
  document.getElementById('set_cancel').onclick = ()=> wrap.remove();
  document.getElementById('set_save').onclick = ()=>{
    const k = document.getElementById('set_api_key').value.trim();
    const t = document.getElementById('set_admin_tok').value.trim();
    if (k) localStorage.setItem('api_key', k); else localStorage.removeItem('api_key');
    if (t) sessionStorage.setItem('admin_token', t); else sessionStorage.removeItem('admin_token');
    wrap.remove();
    renderBanner();
  };
}
