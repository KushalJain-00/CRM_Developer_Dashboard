/* frontend/eml.js — fresh EML feature (upload, contacts, emails, LLM chain, export, push) */
(function () {
  const API = window.CRM_API_BASE || '';
  const e = (s) => (s == null ? '' : String(s))
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const notify = (m, t) => { if (window.showNotification) showNotification(m, t || 'info'); };

  const CHAIN_KEY = 'EML_LLM_CHAIN';
  // Static lists sourced from models.dev (Sep 2026) — retired IDs removed.
  // OpenRouter is fetched live below; its static list is only a fallback.
  const PROVIDERS = [
    { id: 'gemini', label: 'Google Gemini', models: ['gemini-3.8-flash', 'gemini-flash-latest', 'gemini-3.7-flash', 'gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-3.1-pro-preview', 'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemma-4-31b-it', 'gemma-4-26b-a4b-it'] },
    { id: 'openrouter', label: 'OpenRouter', models: ['openai/gpt-4o-mini', 'anthropic/claude-sonnet-4-6', 'google/gemini-2.5-flash'] },
    { id: 'groq', label: 'Groq', models: ['qwen/qwen3.8-27b', 'qwen/qwen3.6-27b', 'openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'allam-2-7b'] },
    { id: 'openai', label: 'OpenAI', models: ['gpt-5.6-sol', 'gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6', 'gpt-5.5-pro', 'gpt-5.5', 'gpt-5.4-mini', 'gpt-5.4-nano', 'gpt-5.4', 'gpt-4o-mini', 'gpt-4o'] },
    { id: 'deepseek', label: 'DeepSeek', models: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-flash', 'deepseek-v4-flash-vision-exp'] },
    { id: 'anthropic', label: 'Anthropic', models: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1', 'claude-opus-5', 'claude-sonnet-5', 'claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5', 'claude-opus-4-6'] },
  ];

  let orModels = null; // { free: [...], paid: [...] } — live from openrouter.ai, cached per session
  async function ensureOrModels() {
    if (orModels) return orModels;
    try {
      const res = await fetch('https://openrouter.ai/api/v1/models');
      const data = await res.json();
      const isFree = m => parseFloat(m.pricing?.prompt) <= 0 && parseFloat(m.pricing?.completion) <= 0;
      const text = (data.data || []).filter(m => (m.architecture?.output_modalities || ['text']).includes('text'));
      orModels = {
        free: text.filter(isFree).map(m => m.id).sort(),
        paid: text.filter(m => !isFree(m)).map(m => m.id).sort(),
      };
    } catch { orModels = { free: [], paid: [] }; }
    return orModels;
  }

  function getChain() {
    try { return JSON.parse(localStorage.getItem(CHAIN_KEY) || '[]'); } catch { return []; }
  }
  function saveChainLocal(chain) { localStorage.setItem(CHAIN_KEY, JSON.stringify(chain)); }

  async function authHeaders() {
    const h = {};
    if (window.getAuthToken) {
      try { const t = await getAuthToken(); if (t) h['Authorization'] = `Bearer ${t}`; } catch {}
    }
    return h;
  }

  const state = { contacts: [], contactPage: 1, contactTotal: 0, emails: [], emailPage: 1, emailTotal: 0, selected: new Set() };

  // Ride out Render cold-starts/deploys: gateway 502/503/504 (or a dropped
  // connection) while the instance boots → retry with backoff (~110s budget,
  // enough for a full Render deploy window or a cold start).
  async function fetchRetry(url, opts, onRetry) {
    const delays = [5000, 15000, 30000, 60000];
    for (let i = 0; ; i++) {
      try {
        const res = await fetch(url, opts);
        if ([502, 503, 504].includes(res.status) && i < delays.length) {
          if (onRetry) onRetry(i + 1, delays.length + 1);
          await new Promise(r => setTimeout(r, delays[i]));
          continue;
        }
        return res;
      } catch (err) {
        if (i >= delays.length) throw err;
        if (onRetry) onRetry(i + 1, delays.length + 1);
        await new Promise(r => setTimeout(r, delays[i]));
      }
    }
  }

  // ── Upload ──────────────────────────────────────────────
  async function processFiles(fileList) {
    const files = Array.from(fileList).filter(f => /\.eml$/i.test(f.name));
    if (!files.length) return notify('No .eml files selected', 'error');
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    fd.append('chain', JSON.stringify(getChain()));
    const bar = document.getElementById('emlProgressBar');
    const label = document.getElementById('emlProgressLabel');
    const results = document.getElementById('emlResults');
    document.getElementById('emlProgress').style.display = 'block';
    results.innerHTML = '';
    bar.style.width = '10%';
    label.textContent = `Uploading ${files.length} file(s)…`;
    try {
      const res = await fetchRetry(`${API}/api/eml/process`, { method: 'POST', body: fd },
        (n, total) => { label.textContent = `Server waking up — retry ${n}/${total}…`; });
      bar.style.width = '100%';
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || res.statusText);
      label.textContent = `Done — ${data.counts.new} new · ${data.counts.duplicate} dupes · ${data.counts.error} errors`;
      renderResults(data.results);
      notify(`Processed ${files.length} file(s)`, 'success');
    } catch (err) {
      label.textContent = 'Failed';
      notify('Process failed: ' + err.message, 'error');
      bar.style.width = '0%';
    }
  }

  function renderResults(results) {
    const el = document.getElementById('emlResults');
    el.innerHTML = `<div style="border:1px solid var(--border);border-radius:10px;overflow:auto">
      <table class="data-table"><thead><tr>
        <th>File</th><th>Status</th><th>Extraction</th><th>Name</th><th>Email</th><th>Phone</th><th>Company</th><th>Designation</th>
      </tr></thead><tbody>
      ${results.map(r => {
        const c = r.contact || {};
        const color = r.status === 'NEW' ? '#16A34A' : r.status === 'DUPLICATE' ? '#D97706' : '#E11D48';
        return `<tr><td>${e(r.file)}</td>
          <td style="color:${color};font-weight:600">${e(r.status)}</td>
          <td>${e(r.extraction)}</td>
          <td>${e(c.name)}</td><td>${e(c.email)}</td><td>${e(c.phone_primary)}</td>
          <td>${e(c.company)}</td><td>${e(c.designation)}</td></tr>`;
      }).join('')}
      </tbody></table></div>
      <div style="margin-top:12px"><button class="btn btn-primary" onclick="showView('eml-contacts')">View all contacts →</button></div>`;
  }

  // ── Contacts ───────────────────────────────────────────
  async function loadContacts(page) {
    state.contactPage = page || 1;
    const search = document.getElementById('emlCSearch')?.value || '';
    const status = document.getElementById('emlCStatus')?.value || '';
    const pushed = document.getElementById('emlCPushed')?.value || '';
    const qs = new URLSearchParams({ page: state.contactPage, page_size: 50 });
    if (search) qs.set('search', search);
    if (status) qs.set('status', status);
    if (pushed) qs.set('pushed', pushed);
    try {
      const res = await fetchRetry(`${API}/api/eml/contacts?${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      state.contacts = data.items; state.contactTotal = data.total;
      state.selected = new Set();
      renderContacts();
    } catch (err) { notify('Load contacts failed: ' + err.message, 'error'); }
  }

  function renderContacts() {
    const table = document.getElementById('emlContactsTable');
    const cols = ['name','email','phone_primary','phone_secondary','company','designation','city','source_file','dedup_status','pushed_to_crm'];
    table.querySelector('thead').innerHTML = `<tr><th><input type="checkbox" id="emlSelAll"></th>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
    table.querySelector('tbody').innerHTML = state.contacts.map(r => `<tr>
      <td><input type="checkbox" class="eml-row-sel" value="${e(r.id)}" ${state.selected.has(r.id)?'checked':''}></td>
      ${cols.map(c => `<td>${e(r[c])}</td>`).join('')}
    </tr>`).join('') || `<tr><td colspan="11" style="padding:20px;text-align:center;color:var(--text-2)">No contacts yet</td></tr>`;
    document.getElementById('emlSelAll')?.addEventListener('change', ev => {
      table.querySelectorAll('.eml-row-sel').forEach(cb => {
        cb.checked = ev.target.checked;
        if (ev.target.checked) state.selected.add(cb.value); else state.selected.delete(cb.value);
      });
    });
    table.querySelectorAll('.eml-row-sel').forEach(cb => cb.addEventListener('change', () => {
      if (cb.checked) state.selected.add(cb.value); else state.selected.delete(cb.value);
    }));
    const pages = Math.max(1, Math.ceil(state.contactTotal / 50));
    document.getElementById('emlContactsPager').innerHTML =
      `<button class="btn btn-secondary btn-sm" ${state.contactPage<=1?'disabled':''} onclick="EmlUI.loadContacts(${state.contactPage-1})">← Prev</button>
       <span style="font-size:12px;color:var(--text-2)">Page ${state.contactPage} / ${pages} · ${state.contactTotal} total</span>
       <button class="btn btn-secondary btn-sm" ${state.contactPage>=pages?'disabled':''} onclick="EmlUI.loadContacts(${state.contactPage+1})">Next →</button>`;
  }

  async function exportExcel() {
    const search = document.getElementById('emlCSearch')?.value || '';
    const status = document.getElementById('emlCStatus')?.value || '';
    const pushed = document.getElementById('emlCPushed')?.value || '';
    try {
      let all = [], page = 1, total = Infinity;
      while (all.length < total) {
        const qs = new URLSearchParams({ page, page_size: 500 });
        if (search) qs.set('search', search);
        if (status) qs.set('status', status);
        if (pushed) qs.set('pushed', pushed);
        const res = await fetchRetry(`${API}/api/eml/contacts?${qs}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || res.statusText);
        total = data.total;
        if (!data.items.length) break;
        all = all.concat(data.items);
        page++;
      }
      if (!all.length) return notify('No contacts to export', 'error');
      const cols = ['name','email','phone_primary','phone_secondary','company','designation','address','city','pincode','website','source_file','dedup_status','pushed_to_crm'];
      const rows = all.map(r => cols.map(c => r[c] ?? ''));
      const ws = XLSX.utils.aoa_to_sheet([cols, ...rows]);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'EML Contacts');
      XLSX.writeFile(wb, `eml_contacts_${Date.now()}.xlsx`);
    } catch (err) { notify('Export failed: ' + err.message, 'error'); }
  }

  function exportCsv() {
    const search = document.getElementById('emlCSearch')?.value || '';
    const status = document.getElementById('emlCStatus')?.value || '';
    const pushed = document.getElementById('emlCPushed')?.value || '';
    const qs = new URLSearchParams({ format: 'csv' });
    if (search) qs.set('search', search);
    if (status) qs.set('status', status);
    if (pushed) qs.set('pushed', pushed);
    window.location.href = `${API}/api/eml/contacts/export?${qs}`;
  }

  async function pushSelected() {
    const ids = [...state.selected];
    if (!ids.length) return notify('Select contacts first', 'error');
    try {
      const headers = Object.assign({ 'Content-Type': 'application/json' }, await authHeaders());
      const res = await fetchRetry(`${API}/api/eml/contacts/push-bulk`, {
        method: 'POST', headers, body: JSON.stringify({ ids }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      notify(`Pushed ${data.pushed} contact(s)${data.failed?.length ? `, ${data.failed.length} failed` : ''}`, data.failed?.length ? 'info' : 'success');
      loadContacts(state.contactPage);
    } catch (err) { notify('Push failed: ' + err.message, 'error'); }
  }

  // ── Emails ─────────────────────────────────────────────
  async function loadEmails(page) {
    state.emailPage = page || 1;
    try {
      const res = await fetchRetry(`${API}/api/eml/emails?page=${state.emailPage}&page_size=50`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      state.emails = data.items; state.emailTotal = data.total;
      renderEmails();
    } catch (err) { notify('Load emails failed: ' + err.message, 'error'); }
  }

  function renderEmails() {
    const list = document.getElementById('emlEmailsList');
    list.innerHTML = state.emails.map(m => `
      <div class="eml-mail-row" style="border:1px solid var(--border);border-radius:10px;padding:12px 14px;cursor:pointer;background:var(--bg-1)"
           onclick="EmlUI.openEmail('${e(m.id)}')">
        <div style="display:flex;justify-content:space-between;gap:12px">
          <strong style="font-size:14px">${e(m.subject || '(no subject)')}</strong>
          <span style="font-size:12px;color:var(--text-2);white-space:nowrap">${e(m.date)}</span>
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-top:4px">
          From: ${e(m.sender_name)} &lt;${e(m.sender_email)}&gt; → ${e(m.receiver_email)}
          ${m.has_signature ? ' · ✍ signature' : ''}
        </div>
      </div>`).join('') || `<div class="empty-state">No emails processed yet</div>`;
    const pages = Math.max(1, Math.ceil(state.emailTotal / 50));
    document.getElementById('emlEmailsPager').innerHTML =
      `<button class="btn btn-secondary btn-sm" ${state.emailPage<=1?'disabled':''} onclick="EmlUI.loadEmails(${state.emailPage-1})">← Prev</button>
       <span style="font-size:12px;color:var(--text-2)">Page ${state.emailPage} / ${pages} · ${state.emailTotal}</span>
       <button class="btn btn-secondary btn-sm" ${state.emailPage>=pages?'disabled':''} onclick="EmlUI.loadEmails(${state.emailPage+1})">Next →</button>`;
  }

  async function openEmail(id) {
    try {
      const res = await fetchRetry(`${API}/api/eml/emails/${id}`);
      const m = await res.json();
      if (!res.ok) throw new Error(m.detail || 'Not found');
      const body = (m.body_text || '').slice(0, 4000);
      notify(`${m.subject || 'Email'} — ${(m.contacts || []).length} contact(s) extracted`, 'info');
      alert(
        `Subject: ${m.subject || ''}\nFrom: ${m.sender_name} <${m.sender_email}>\nTo: ${m.receiver_email}\nSignature: ${m.has_signature ? 'yes' : 'no'}\n\n` +
        `Contacts: ${(m.contacts || []).map(c => c.name || c.email).join(', ') || 'none'}\n\n---\n${body}`
      );
    } catch (err) { notify(err.message, 'error'); }
  }

  // ── LLM chain settings ─────────────────────────────────
  async function renderChain() {
    const chain = getChain();
    const box = document.getElementById('emlChainList');
    if (!chain.length) {
      box.innerHTML = `<div class="empty-state" style="border:1px dashed var(--border);border-radius:10px;padding:24px;text-align:center;color:var(--text-2)">
        No providers yet — extraction will use local regex fallback only. Add at least one provider.</div>`;
      return;
    }
    const or = chain.some(c => c.provider === 'openrouter') ? await ensureOrModels() : null;
    const opt = (m, sel) => `<option ${m === sel ? 'selected' : ''}>${e(m)}</option>`;
    const modelOptions = (c) => {
      const p = PROVIDERS.find(x => x.id === c.provider) || PROVIDERS[0];
      if (c.provider === 'openrouter' && or && (or.free.length || or.paid.length)) {
        const all = [...or.free, ...or.paid];
        return `<optgroup label="Free (no cost)">${or.free.map(m => opt(m, c.model)).join('')}</optgroup>`
          + `<optgroup label="Paid">${or.paid.map(m => opt(m, c.model)).join('')}</optgroup>`
          + (c.model && !all.includes(c.model) ? opt(c.model, c.model) : '');
      }
      return p.models.map(m => opt(m, c.model)).join('')
        + (c.model && !p.models.includes(c.model) ? opt(c.model, c.model) : '');
    };
    box.innerHTML = chain.map((c, i) => {
      return `<div style="border:1px solid var(--border);border-radius:10px;padding:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:var(--bg-1)">
        <span style="font-weight:600;font-size:12px;color:var(--text-2);min-width:24px">#${i + 1}</span>
        <select class="tbl-select eml-p" data-i="${i}" onchange="EmlUI.onProviderChange(${i})">
          ${PROVIDERS.map(x => `<option value="${x.id}" ${x.id===c.provider?'selected':''}>${x.label}</option>`).join('')}
        </select>
        <select class="tbl-select eml-m" data-i="${i}">
          ${modelOptions(c)}
        </select>
        <input type="password" class="tbl-select eml-k" data-i="${i}" placeholder="API key" value="${e(c.api_key || '')}" style="flex:1;min-width:160px">
        <button class="btn btn-secondary btn-sm" onclick="EmlUI.moveChain(${i},${i-1})" ${i===0?'disabled':''}>↑</button>
        <button class="btn btn-secondary btn-sm" onclick="EmlUI.moveChain(${i},${i+1})" ${i===chain.length-1?'disabled':''}>↓</button>
        <button class="btn btn-danger btn-sm" onclick="EmlUI.removeChainItem(${i})">✕</button>
      </div>`;
    }).join('');
  }

  function syncChainFromDom() {
    const chain = getChain();
    document.querySelectorAll('#emlChainList .eml-p').forEach(sel => {
      const i = +sel.dataset.i;
      if (chain[i]) chain[i].provider = sel.value;
    });
    document.querySelectorAll('#emlChainList .eml-m').forEach(sel => {
      const i = +sel.dataset.i;
      if (chain[i]) chain[i].model = sel.value;
    });
    document.querySelectorAll('#emlChainList .eml-k').forEach(inp => {
      const i = +inp.dataset.i;
      if (chain[i]) chain[i].api_key = inp.value.trim();
    });
    return chain;
  }

  function addChainItem() {
    const chain = syncChainFromDom();
    chain.push({ provider: 'gemini', model: 'gemini-3.8-flash', api_key: '' });
    saveChainLocal(chain);
    renderChain();
  }
  function removeChainItem(i) {
    const chain = syncChainFromDom();
    chain.splice(i, 1);
    saveChainLocal(chain);
    renderChain();
  }
  function moveChain(from, to) {
    const chain = syncChainFromDom();
    if (to < 0 || to >= chain.length) return;
    const [item] = chain.splice(from, 1);
    chain.splice(to, 0, item);
    saveChainLocal(chain);
    renderChain();
  }
  async function onProviderChange(i) {
    const chain = syncChainFromDom();
    const p = PROVIDERS.find(x => x.id === chain[i].provider);
    if (p) {
      if (p.id === 'openrouter') {
        const or = await ensureOrModels();
        chain[i].model = or.free[0] || p.models[0];
      } else {
        chain[i].model = p.models[0];
      }
    }
    saveChainLocal(chain);
    renderChain();
  }
  function saveChain() {
    const chain = syncChainFromDom().filter(c => c.provider && c.model);
    saveChainLocal(chain);
    const missing = chain.filter(c => !c.api_key).length;
    notify(missing ? `Saved — ${missing} provider(s) missing keys (will be skipped)` : 'LLM chain saved', missing ? 'info' : 'success');
  }

  // ── boot ───────────────────────────────────────────────
  function initUpload() {
    const input = document.getElementById('emlFileInput');
    const zone = document.getElementById('emlDropZone');
    if (!input || !zone) return;
    document.getElementById('emlPickBtn')?.addEventListener('click', ev => { ev.stopPropagation(); input.click(); });
    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => { if (input.files.length) processFiles(input.files); input.value = ''; });
    zone.addEventListener('dragover', ev => { ev.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', ev => {
      ev.preventDefault(); zone.classList.remove('drag-over');
      if (ev.dataTransfer.files.length) processFiles(ev.dataTransfer.files);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUpload);
  } else { initUpload(); }

  window.EmlUI = {
    loadContacts, exportExcel, exportCsv, pushSelected,
    loadEmails, openEmail,
    renderChain, addChainItem, removeChainItem, moveChain, onProviderChange, saveChain,
  };
})();
