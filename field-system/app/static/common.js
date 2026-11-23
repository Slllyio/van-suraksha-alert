const IST = {timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false};
const fmt = s => { if (!s) return ''; const d = new Date(s); return d.toLocaleString('en-IN', d.getFullYear() === new Date().getFullYear() ? IST : {...IST, year: 'numeric'}); };
let CLOCK = 0;   // server clock minus phone clock (also lets a demo replay a past day)
const nowMs = () => Date.now() + CLOCK;
const setClock = me => { CLOCK = new Date(me.now_utc) - Date.now(); if (me.demo) document.body.insertAdjacentHTML('afterbegin', `<div class="banner" style="margin:0;border-radius:0">Demo replay of ${fmt(me.now_utc)} IST, with real alerts from that day</div>`); };
const ago = s => { const h = (nowMs() - new Date(s)) / 36e5; return h < 1 ? Math.round(h*60)+' min ago' : h < 48 ? h.toFixed(0)+' h ago' : (h/24).toFixed(0)+' days ago'; };
const STATUS = {new: 'Not visited', revisit: 'Visit again', visited: 'Visited, awaiting check', verified: 'Checked'};
const OUTCOME = {active_fire: 'Fire burning', burnt_out: 'Burnt, fire out', no_fire: 'No fire found', outside_forest: 'Fire outside forest', controlled_burn: 'Controlled burn', nothing_found: 'No fire, no fresh burn'};
// Patrol pilot: how old the burn is, and which answers each kind of task offers
const BURN_AGE = {now: 'Burning now', '1_2_days': 'Burnt 1-2 days ago', older: 'Older burn'};
const OUTCOMES_FOR = {alert: ['active_fire', 'burnt_out', 'no_fire', 'outside_forest', 'controlled_burn'],
  predicted: ['nothing_found', 'active_fire', 'burnt_out', 'controlled_burn'], chance: ['active_fire', 'burnt_out', 'controlled_burn']};
const KIND = i => i.kind || 'alert';
const CROSSED = {yes: 'Yes', no: 'No', unknown: "Don't know"};
const INSPECTION = {completed: 'inspected (2+ photos inside, 100 m apart)', arrived: 'arrived only, not counted as a check', not_shown: 'not shown inside the square'};
const STREAM = {ignition: 'patrol list', response: 'alert visit'};
const ENFORCEMENT = {none: 'None', warning: 'Warning given', fir_por: 'FIR / POR registered'};
const SUPPRESSION = {none: 'None', fire_line: 'Fire line', beating: 'Beating', water: 'Water', counter_fire: 'Counter-fire'};
const KNOWN = {satellite: 'Satellite alert (this app / FSI SMS)', watchtower: 'Watchtower', villager: 'Villager / informer', patrol: 'Own patrol', other: 'Other'};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, opts = {}) {
  const r = await fetch(path, {credentials: 'same-origin', ...opts});
  if (r.status === 401) { showLogin(); throw new Error('login'); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.headers.get('content-type')?.includes('json') ? r.json() : r.text();
}
function pill(i) { return `<span class="pill s-${i.status}">${STATUS[i.status]}</span>` + (i.overdue ? ' <span class="pill od">Overdue</span>' : '')
  + (i.large ? ' <span class="pill" style="background:#7b1fa2">Large fire</span>' : ''); }
const alsoBeats = i => (i.beats || []).length > 1 ? `<div class="muted">Junction alert, also sent to: ${i.beats.slice(1).map(esc).join(', ')}</div>` : '';
async function showLogin(onDone) {
  document.querySelectorAll('.app').forEach(e => e.style.display = 'none');
  const box = document.getElementById('login'); box.style.display = 'block';
  let last = ''; try { last = localStorage.getItem('fs-staff-no') || ''; } catch (e) {}
  box.innerHTML = `<div class="card"><h2 style="margin-top:0">Sign in</h2>
    <label>Your staff number<input id="lg-who" class="inp" type="number" min="1" inputmode="numeric" value="${esc(last)}"></label>
    <div class="muted">The number your admin gave you with your PIN.</div>
    <label>PIN<input id="lg-pin" type="password" inputmode="numeric" autocomplete="current-password"></label>
    <button class="btn" id="lg-go" style="width:100%">Sign in</button><p id="lg-err" class="muted"></p></div>`;
  document.getElementById('lg-go').onclick = async () => {
    const no = document.getElementById('lg-who').value, pin = document.getElementById('lg-pin').value, err = document.getElementById('lg-err');
    if (!(+no >= 1) || !pin) return err.textContent = 'Enter your staff number and PIN.';
    const r = await fetch('/api/login', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({staff_id: +no, pin})});
    if (r.ok) { try { localStorage.setItem('fs-staff-no', no); } catch (e) {} location.reload(); }
    else err.textContent = r.status === 429 ? 'Too many wrong PINs. Wait a few minutes, then try again.' : 'Wrong staff number or PIN, try again.';
  };
}
async function logout() { await fetch('/api/logout', {method: 'POST'}); location.reload(); }
