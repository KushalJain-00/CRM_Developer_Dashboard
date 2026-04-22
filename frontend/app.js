const API_BASE = (window.CRM_API_BASE || '').replace(/\/$/, '');
const API_KEY  = window.CRM_API_KEY || '';
const SUPABASE_URL = window.CRM_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = window.CRM_SUPABASE_ANON_KEY || '';
// FIX: Renamed from "supabase" to "crmClient" to avoid SyntaxError conflict
// with the window.supabase global injected by the Supabase CDN script.
// The CDN registers a top-level "supabase" identifier which clashed with
// this const, crashing app.js entirely and making ALL functions undefined.
const crmClient = (SUPABASE_URL && SUPABASE_ANON_KEY && window.supabase)
  ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

const S = {
  rawData:[], headers:[], mapping:{}, clean:[],
  fileName:'', sheetName:'',
  filtered:[], page:1, pageSize:50, sortCol:null, sortDir:1,
  charts:[], currentView:'upload',
  dupGroups:[],
  validation: {dropped:0, invalidEmails:0, landlines:0, foreign:0, total:0},
  dbContacts: [], sessionId: null, userEmail: null,
};

const FT = {
  company: {label:'Company Name',       icon:'🏢', color:'#3B82F6'},
  contact: {label:'Contact Person',     icon:'👤', color:'#8B5CF6'},
  phone:   {label:'Phone / Mobile',     icon:'📞', color:'#10B981'},
  email:   {label:'Email Address',      icon:'📧', color:'#F59E0B'},
  address: {label:'Address',            icon:'📍', color:'#F43F5E'},
  city:    {label:'City / District',    icon:'🏙', color:'#06B6D4'},
  pincode: {label:'PIN / ZIP Code',     icon:'🔢', color:'#94A3B8'},
  website: {label:'Website / URL',      icon:'🌐', color:'#10B981'},
  product: {label:'Product / Service',  icon:'📦', color:'#F97316'},
  industry:{label:'Industry / Category',icon:'🏭', color:'#8B5CF6'},
  amount:  {label:'Amount / Value',     icon:'💰', color:'#10B981'},
  date:    {label:'Date / Time',        icon:'📅', color:'#3B82F6'},
  status:  {label:'Status / Stage',     icon:'🏷', color:'#F97316'},
  id:      {label:'Serial / ID',        icon:'🔑', color:'#94A3B8'},
  keyword: {label:'Keyword / Tag',      icon:'🔖', color:'#8B5CF6'},
  location:{label:'Location / Area',    icon:'📌', color:'#06B6D4'},
  facebook:{label:'Social Media',       icon:'🔗', color:'#3B82F6'},
  member:  {label:'Member Flag',        icon:'✅', color:'#10B981'},
  fax:     {label:'Fax Number',         icon:'📠', color:'#94A3B8'},
  whatsapp:{label:'WhatsApp',           icon:'💬', color:'#10B981'},
  stdcode: {label:'STD Code',           icon:'☎️', color:'#94A3B8'},
  other:   {label:'Other / Custom',     icon:'📌', color:'#64748B'},
  skip:    {label:'✕ Skip Field',      icon:'✕',  color:'#F43F5E'},
};

const PALETTE = ['#3B82F6','#8B5CF6','#10B981','#F59E0B','#F43F5E','#F97316','#06B6D4','#6366F1','#34D399','#FCD34D','#A78BFA','#60A5FA'];

function apiHeaders() {
  const h = {'Content-Type':'application/json'};
  if (API_KEY) h['X-API-Key'] = API_KEY;
  return h;
}

function apiUploadHeaders() {
  const h = {};
  if (API_KEY) h['X-API-Key'] = API_KEY;
  return h;
}

function getValidSheets(wb) {
  return wb.SheetNames.filter(name => {
    const ws = wb.Sheets[name];
    if (!ws['!ref']) return false;
    const range = XLSX.utils.decode_range(ws['!ref']);
    const rows = range.e.r - range.s.r;
    const cols = range.e.c - range.s.c + 1;
    if (cols <= 2) return false;
    const lname = name.toLowerCase();
    if (/mob no|email id|phone list|mobile list|index|lookup/.test(lname)) return false;
    return rows > 0;
  });
}

function detectField(col, samples) {
  const n = String(col||'').toLowerCase().replace(/[^a-z0-9]/g,'');
  const nonEmpty = samples.filter(v => v != null && v !== '');
  const strs = nonEmpty.map(v => String(v).trim());

  if (/^(srno|sno|serialno|srnumber|slno|rowno|s\.?no\.?|no\.|#|sr\.|sr$)/.test(n)) return ['id',96];
  if (nonEmpty.length > 2 && nonEmpty.every(v => !isNaN(v) && +v > 0 && +v < 100000)) {
    const nums = nonEmpty.map(Number).sort((a,b)=>a-b);
    if (nums[0] <= 5 && (nums[nums.length-1]-nums[0]) <= nums.length+2) return ['id',82];
  }
  if (/email|e-mail|emailid|mail/.test(n)) return ['email',97];
  if (strs.some(v => /^[\w.+%-]+@[\w.-]+\.[a-z]{2,}$/i.test(v))) return ['email',92];
  if (/facebook|fb\.com|social/.test(n)) return ['facebook',98];
  if (/web|site|url|www/.test(n)) return ['website',94];
  if (strs.some(v => /https?:\/\/|www\./i.test(v))) return ['website',88];
  if (/whatsapp|whats|wa\.?no/.test(n)) return ['whatsapp',98];
  if (/fax/.test(n)) return ['fax',98];
  if (/stdcode|std/.test(n)) return ['stdcode',95];
  if (/mob|mobile|cell|phone|tel|ph\.?no|phno|contact.*no|landline|fmob|fcontact.*mob/.test(n)) return ['phone',96];
  if (strs.some(v => /^[\+]?[\d\s\-\/\.]{8,18}$/.test(v.trim()))) return ['phone',82];
  if (/pin|zip|postal/.test(n)) return ['pincode',96];
  if (nonEmpty.every(v => /^\d{5,6}$/.test(String(v).trim()))) return ['pincode',88];
  if (/amount|value|price|cost|revenue|sales|deal|invoice|payment|total|salary|ctc/.test(n)) return ['amount',92];
  if (/date|dt|time|year|month|day|extracted/.test(n)) return ['date',92];
  if (/member|memb/.test(n)) return ['member',96];
  if (/status|stage|state|active/.test(n)) return ['status',88];
  if (/keyword|tag|category(?!.*busi)|type(?!.*product)/.test(n)) return ['keyword',90];
  if (/^location$/.test(n)) return ['location',95];
  if (/city|town|district|dist|taluka|state|region|zone|area/.test(n)) return ['city',94];
  if (/address|addr|factory|office|street|road|plot|shop|floor|phase/.test(n)) return ['address',91];
  if (/product|prod|service|item|goods|material|dealing|mfg|manufactur/.test(n)) return ['product',89];
  if (/industry|sector|busi.*categ|category|segment|business|trade/.test(n)) return ['industry',88];
  if (/contact.*person|fcontact|person|director|proprietor|owner|manager|^partner/.test(n)) return ['contact',89];
  if (/company|firm|party|organisation|organization|nameofcompany|businessname|name.*party|name.*company/.test(n)) return ['company',93];
  if (strs.length > 0) {
    const avgLen = strs.reduce((a,v)=>a+v.length,0)/strs.length;
    if (avgLen > 50) return ['address',62];
    if (avgLen > 20) return ['product',55];
    if (strs.every(v=>/^[A-Za-z\s\.,&\-]+$/.test(v)) && avgLen > 8 && avgLen < 35) return ['company',55];
  }
  return ['other',45];
}

document.addEventListener('DOMContentLoaded', () => {
  syncAuthSession();

  const dz = document.getElementById('dropZone');
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('drag'); handleMultipleFiles(e.dataTransfer.files); });

  // Initialize theme from localStorage
  const savedTheme = localStorage.getItem('crm-theme') || 'nexus-light';
  setTheme(savedTheme, true);

  // BUG FIX: Restore sidebar collapsed state across page reloads
  if (localStorage.getItem('crm-sb-collapsed') === '1') {
    document.body.classList.add('sb-collapsed');
    const btn = document.getElementById('sbToggleBtn');
    if (btn) btn.innerHTML = '›';
  }

  // Populate sidebar user info from session
  try {
    const session = JSON.parse(localStorage.getItem('crm-session') || '{}');
    S.userEmail = session.email || null;
    const fullName = [session.firstName, session.lastName].filter(Boolean).join(' ') || session.email || 'User';
    const initials = fullName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || 'U';
    const el = (id) => document.getElementById(id);
    if (el('sbUserName'))    el('sbUserName').textContent = fullName;
    if (el('sbUserRole'))    el('sbUserRole').textContent = session.email || 'CRM Member';
    if (el('sbAvatarInitials')) el('sbAvatarInitials').textContent = initials;
  } catch(e) {}
});

async function syncAuthSession() {
  if (!crmClient) return;
  try {
    const { data, error } = await crmClient.auth.getUser();
    if (error) throw error;
    const user = data.user;
    if (!user) {
      S.userEmail = null;
      localStorage.removeItem('crm-session');
      window.location.replace('signin.html');
      return;
    }
    const fullName = user.user_metadata?.full_name || '';
    const parts = fullName.trim().split(/\s+/).filter(Boolean);
    const session = {
      firstName: parts[0] || '',
      lastName: parts.slice(1).join(' ') || '',
      email: user.email,
      provider_uid: user.id,
      signedInAt: Date.now(),
    };
    S.userEmail = user.email || null;
    localStorage.setItem('crm-session', JSON.stringify(session));
  } catch (e) {
    console.warn('Supabase session sync failed:', e);
  }
}

/* ── UI Toggles ─────────────────────────────────────────────────────── */
function isDarkTheme() {
  const t = document.documentElement.getAttribute('data-theme');
  return t && t !== 'nexus-light';
}

function setTheme(name, skipCharts) {
  const root = document.documentElement;
  if (name === 'nexus-light') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', name);
  }
  localStorage.setItem('crm-theme', name);

  // Update theme picker dots
  document.querySelectorAll('.theme-dot').forEach(d => {
    d.classList.toggle('active', d.getAttribute('data-theme') === name);
  });

  // Re-render charts to pick up new colors
  if (!skipCharts && S.clean && S.clean.length) {
    killCharts();
    buildMainCharts();
    if (document.getElementById('analyticsTabs')) {
      buildAnalytics();
    }
  }
}

// Legacy compat
function toggleTheme() { setTheme(isDarkTheme() ? 'nexus-light' : 'nexus-dark'); }

async function signOut() {
  if (!confirm('Sign out of CRM Engine?')) return;
  if (crmClient) {
    try { await crmClient.auth.signOut(); } catch (e) { console.warn('Supabase signout failed:', e); }
  }
  localStorage.removeItem('crm-session');
  window.location.replace('signin.html');
}

function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('sbOverlay');
  sb.classList.toggle('open');
  ov.classList.toggle('open');
}

async function handleFile(file) {
  if (!file) return;
  S.fileName = file.name;
  const ext = file.name.split('.').pop().toLowerCase();

  if (ext === 'eml') {
    handleEmlFile(file);
    return;
  }

  if (ext === 'txt') {
    const reader = new FileReader();
    reader.onload = e => {
      const lines = e.target.result.split('\n').map(l=>l.trim())
        .filter(l => l && l.replace(/[\+\d\s\-]/g,'').length < 3);
      if (!lines.length) { showError('No phone numbers detected in file.'); return; }
      S.rawData = lines.map((l,i) => ({'SR': i+1, 'Phone Number': l}));
      S.headers = ['SR','Phone Number'];
      S.sheetName = 'Phone List';
      buildMapping();
    };
    reader.readAsText(file);
    return;
  }

  if (ext === 'csv') {
    const reader = new FileReader();
    reader.onload = e => {
      const lines = e.target.result.split('\n').filter(l=>l.trim());
      if (lines.length < 2) { showError('CSV appears empty.'); return; }
      const headers = lines[0].split(',').map(h=>h.trim().replace(/^"|"$/g,''));
      const rows = lines.slice(1).map(line => {
        const vals = line.split(',').map(v=>v.trim().replace(/^"|"$/g,''));
        const obj = {};
        headers.forEach((h,i) => obj[h] = vals[i] || '');
        return obj;
      }).filter(r => Object.values(r).some(v=>v));
      S.rawData = rows; S.headers = headers; S.sheetName = 'CSV Data';
      buildMapping();
    };
    reader.readAsText(file);
    return;
  }

  if (ext === 'xlsx') {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const wb = XLSX.read(e.target.result, {type:'array', cellDates:true});
        const validSheets = getValidSheets(wb);
        if (!validSheets.length) { showError('No valid data sheets found.'); return; }
        S.sheetName = validSheets.length > 1 ? validSheets.join(' + ') : validSheets[0];
        let allJson = [], allHeaders = [];
        validSheets.forEach(sn => {
          const ws = wb.Sheets[sn];
          const json = XLSX.utils.sheet_to_json(ws, {defval:null, raw:false});
          if (!json.length) return;
          const keys = Object.keys(json[0]);
          const merged = mergeUnnamedCols(keys, json);
          merged.forEach(h => {
            if (!allHeaders.includes(h)) {
              const vals = json.map(r=>r[h]).filter(v=>v!=null&&v!=='');
              if (vals.length > 0 && !String(h).startsWith('__EMPTY')) allHeaders.push(h);
            }
          });
          allJson = allJson.concat(json);
        });
        if (!allJson.length) { showError('All sheets appear empty.'); return; }
        S.headers = allHeaders;
        S.rawData = allJson;
        buildMapping();
      } catch(err) {
        showError('Could not read file: ' + err.message);
      }
    };
    reader.readAsArrayBuffer(file);
    return;
  }

  if (ext === 'xls' || ext === 'pdf') {
    await handleViaBackend(file, ext);
    return;
  }

  showError(`Unsupported file type: .${ext}`);
}

/* ── Multi-File Handler ────────────────────────────────────────────── */
async function handleMultipleFiles(fileList) {
  // Intercept .eml files and route to the EML extractor
  const emlFiles = Array.from(fileList).filter(f => /\.eml$/i.test(f.name));
  if (emlFiles.length === 1) { handleEmlFile(emlFiles[0]); return; }
  if (emlFiles.length > 1) { handleBulkEml(emlFiles); return; }

  const files = Array.from(fileList).filter(f => /\.(xlsx|xls|csv|txt|pdf|eml)$/i.test(f.name));
  if (!files.length) { showError('No supported files found. Drop .xlsx, .xls, .csv, .txt, .pdf, or .eml files.'); return; }

  // If only 1 file, use normal flow
  if (files.length === 1) { handleFile(files[0]); return; }

  // Multiple files — merge them all
  let mergedRaw = [], mergedHeaders = [], fileNames = [];

  for (const file of files) {
    const ext = file.name.split('.').pop().toLowerCase();
    fileNames.push(file.name);

    try {
      if (ext === 'xlsx') {
        const data = await readFileAsArrayBuffer(file);
        const wb = XLSX.read(data, {type:'array', cellDates:true});
        const validSheets = getValidSheets(wb);
        validSheets.forEach(sn => {
          const ws = wb.Sheets[sn];
          const json = XLSX.utils.sheet_to_json(ws, {defval:null, raw:false});
          if (!json.length) return;
          const keys = Object.keys(json[0]);
          const merged = mergeUnnamedCols(keys, json);
          merged.forEach(h => {
            if (!mergedHeaders.includes(h)) {
              const vals = json.map(r=>r[h]).filter(v=>v!=null&&v!=='');
              if (vals.length > 0 && !String(h).startsWith('__EMPTY')) mergedHeaders.push(h);
            }
          });
          mergedRaw = mergedRaw.concat(json);
        });
      } else if (ext === 'csv') {
        const text = await readFileAsText(file);
        const lines = text.split('\n').filter(l=>l.trim());
        if (lines.length < 2) continue;
        const headers = lines[0].split(',').map(h=>h.trim().replace(/^"|"$/g,''));
        headers.forEach(h => { if (!mergedHeaders.includes(h)) mergedHeaders.push(h); });
        const rows = lines.slice(1).map(line => {
          const vals = line.split(',').map(v=>v.trim().replace(/^"|"$/g,''));
          const obj = {};
          headers.forEach((h,i) => obj[h] = vals[i] || '');
          return obj;
        }).filter(r => Object.values(r).some(v=>v));
        mergedRaw = mergedRaw.concat(rows);
      } else if (ext === 'xls' || ext === 'pdf') {
        // These need backend parsing — handle one at a time via API
        if (API_BASE) {
          const fd = new FormData();
          fd.append('file', file);
          const res = await fetch(`${API_BASE}/api/parse`, { method:'POST', headers:{'x-api-key':API_KEY}, body:fd });
          if (res.ok) {
            const result = await res.json();
            if (result.headers) result.headers.forEach(h => { if (!mergedHeaders.includes(h)) mergedHeaders.push(h); });
            if (result.rows) mergedRaw = mergedRaw.concat(result.rows);
          }
        }
      }
    } catch(err) {
      console.warn(`Failed to parse ${file.name}:`, err);
    }
  }

  if (!mergedRaw.length) { showError('No data could be extracted from the dropped files.'); return; }

  S.fileName = fileNames.length <= 3 ? fileNames.join(' + ') : `${fileNames.length} files merged`;
  S.sheetName = `${fileNames.length} files`;
  S.rawData = mergedRaw;
  S.headers = mergedHeaders;
  buildMapping();
  showNotification(`📂 Merged ${mergedRaw.length} records from ${fileNames.length} files`, 'success');
}

function readFileAsArrayBuffer(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = e => resolve(e.target.result);
    r.onerror = reject;
    r.readAsArrayBuffer(file);
  });
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = e => resolve(e.target.result);
    r.onerror = reject;
    r.readAsText(file);
  });
}

async function handleViaBackend(file, ext) {
  if (!API_BASE) {
    showError('Backend not configured. Set CRM_API_BASE in config.js');
    return;
  }
  showUploadProgress(true, ext);
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch(`${API_BASE}/api/parse`, {
      method: 'POST',
      headers: apiUploadHeaders(),
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({detail: res.statusText}));
      throw new Error(err.detail || 'Parse failed');
    }
    const data = await res.json();
    S.sheetName = data.sheet;
    S.headers   = data.headers.filter(h => h && !String(h).startsWith('__EMPTY'));
    S.rawData   = data.rows;
    buildMapping();
  } catch (err) {
    showError(`Could not parse file: ${err.message}`);
  } finally {
    showUploadProgress(false, ext);
  }
}

function showUploadProgress(on, ext) {
  const btn = document.getElementById('chooseFileBtn');
  if (!btn) return;
  if (on) {
    btn.innerHTML = `<span class="spinner-inline"></span> Parsing ${ext.toUpperCase()}…`;
    btn.disabled = true;
  } else {
    btn.innerHTML = 'Choose File';
    btn.disabled = false;
  }
}

function showError(msg) {
  const el = document.getElementById('uploadError');
  if (el) { el.textContent = msg; el.classList.remove('hidden'); setTimeout(() => el.classList.add('hidden'), 6000); }
  else alert(msg);
}

function mergeUnnamedCols(keys, data) {
  const result = [];
  let i = 0;
  while (i < keys.length) {
    const key = keys[i];
    const isUnnamed = /^Unnamed:\s*\d+$/.test(key);
    if (!isUnnamed) {
      const type = detectField(key, data.slice(0,20).map(r=>r[key]).filter(v=>v));
      const isProductish = ['product','address','industry'].includes(type[0]);
      let j = i + 1;
      const unnamedGroup = [];
      while (j < keys.length && /^Unnamed:\s*\d+$/.test(keys[j])) { unnamedGroup.push(keys[j]); j++; }
      if (isProductish && unnamedGroup.length > 0) {
        data.forEach(row => {
          const parts = [row[key]];
          unnamedGroup.forEach(uk => { if (row[uk] != null && row[uk] !== '') parts.push(row[uk]); });
          row[key] = parts.filter(Boolean).join(' ').trim();
        });
        result.push(key);
        i = j;
        continue;
      }
      result.push(key);
    }
    i++;
  }
  return result;
}

function buildMapping() {
  const mapping = {};
  S.headers.forEach(h => {
    const samples = S.rawData.slice(0,40).map(r=>r[h]).filter(v=>v!=null&&v!=='');
    const [type, conf] = detectField(h, samples);
    const fill = Math.round(S.rawData.filter(r=>r[h]!=null&&r[h]!=='').length / S.rawData.length * 100);
    mapping[h] = {type, confidence:conf, fill, keep: type !== 'skip'};
  });
  S.mapping = mapping;

  showView('mapping');
  document.getElementById('mappingSub').textContent =
    `${S.fileName}  ·  Sheet: "${S.sheetName}"  ·  ${S.rawData.length.toLocaleString()} records  ·  ${S.headers.length} columns`;

  const detected = Object.values(mapping).filter(m=>m.type!=='other'&&m.type!=='skip').length;
  document.getElementById('mappingAlert').innerHTML =
    `🤖 Auto-detected <strong>${detected}/${S.headers.length}</strong> field types. Review and confirm — or override using the dropdowns.`;

  document.getElementById('mapStatsRow').innerHTML = `
    <div class="map-stat"><div class="map-stat-val">${S.rawData.length.toLocaleString()}</div><div class="map-stat-lbl">Total Records</div></div>
    <div class="map-stat"><div class="map-stat-val">${S.headers.length}</div><div class="map-stat-lbl">Columns Found</div></div>
    <div class="map-stat"><div class="map-stat-val">${detected}</div><div class="map-stat-lbl">Auto-Mapped</div></div>
    <div class="map-stat"><div class="map-stat-val">${Math.round(Object.values(mapping).reduce((a,m)=>a+m.fill,0)/S.headers.length)}%</div><div class="map-stat-lbl">Avg Fill Rate</div></div>
  `;

  const container = document.getElementById('mappingRows');
  container.innerHTML = '';
  S.headers.forEach(h => {
    const m = mapping[h];
    const fillColor = m.fill>70?'#10B981':m.fill>40?'#F59E0B':'#F43F5E';
    const confColor = m.confidence>=85?'#10B981':m.confidence>=65?'#F59E0B':'#F43F5E';
    const samples = S.rawData.slice(0,3).map(r=>r[h]).filter(v=>v!=null&&v!=='').map(v=>String(v).slice(0,28)).join(', ');
    const opts = Object.entries(FT).map(([k,v])=>`<option value="${k}"${m.type===k?' selected':''}>${v.icon} ${v.label}</option>`).join('');
    const div = document.createElement('div');
    div.className = 'mt-row';
    div.innerHTML = `
      <div>
        <div class="orig-col">${h}</div>
        <div class="fill-bar-outer">
          <div class="fill-bar-bg"><div class="fill-bar-fg" style="width:${m.fill}%;background:${fillColor}"></div></div>
          <span class="fill-pct">${m.fill}%</span>
        </div>
        <div class="sample-txt">${samples}</div>
      </div>
      <div class="arr-icon" style="opacity:${m.confidence < 65 ? '1' : '0.4'}">→</div>
      <select class="map-sel" style="${m.confidence < 65 ? 'border-color:var(--amber);box-shadow:0 0 0 2px rgba(245,158,11,0.15)' : ''}" data-col="${h}" onchange="S.mapping['${h}'].type=this.value;S.mapping['${h}'].keep=this.value!=='skip';this.style.borderColor='';this.style.boxShadow='';">${opts}</select>
      <div class="conf-num" style="color:${confColor}">${m.confidence}%</div>
      <div><input type="checkbox" class="incl-chk" ${m.keep?'checked':''} onchange="S.mapping['${h}'].keep=this.checked"></div>
    `;
    container.appendChild(div);
  });
}

async function startProcessing() {
  showView('processing');
  const steps = [
    [10,'Parsing raw data structure...'],
    [25,'Running adaptive field detection...'],
    [42,'Cleaning & normalizing values...'],
    [58,'Merging multi-value cells...'],
    [70,'Running deduplication analysis...'],
    [82,'Computing analytics & metrics...'],
    [92,'Building charts and insights...'],
    [100,'Dashboard ready!'],
  ];
  document.getElementById('procSteps').innerHTML = '';
  const stepEls = steps.map(([,msg]) => {
    const div = document.createElement('div');
    div.className = 'ps-row';
    div.innerHTML = `<div class="ps-dot"></div>${msg}`;
    document.getElementById('procSteps').appendChild(div);
    return div;
  });
  for (let i = 0; i < steps.length; i++) {
    const [pct, msg] = steps[i];
    document.getElementById('progFill').style.width = pct + '%';
    document.getElementById('procSub').textContent = msg;
    if (stepEls[i-1]) stepEls[i-1].className = 'ps-row done';
    stepEls[i].className = 'ps-row active';
    await sleep(240);
  }
  processData();
  findDuplicates();
  buildAllViews();
  document.getElementById('topActions').style.display = 'flex';
  document.getElementById('sbFileCard').classList.remove('hidden');
  document.getElementById('sbFileName').textContent = S.fileName;
  document.getElementById('sbFileMeta').textContent = `${S.clean.length.toLocaleString()} records · ${keepCols().length} fields`;
  document.getElementById('dashUpdated').textContent = `Generated ${new Date().toLocaleString()}`;
  showView('dashboard');
}

function processData() {
  const keep = keepCols();
  S.validation = {dropped:0, invalidEmails:0, landlines:0, foreign:0, total:S.rawData.length};

  // Step 1: Clean & normalize values
  const cleaned = S.rawData.map(row => {
    const out = { _phoneCountry: 'IN' };
    keep.forEach(h => {
      const type = S.mapping[h].type;
      let v = row[h];
      if (v == null || v === '') { out[h] = ''; return; }
      v = String(v).trim();
      if (type === 'email') {
        if (v.includes('/')) {
          const parts = v.split('/').map(p=>p.trim()).filter(p=>p.includes('@'));
          out[h] = parts[0] || v.toLowerCase();
          if (parts[1]) out[h+'_2'] = parts[1];
        } else {
          out[h] = v.toLowerCase().replace(/\s+/g,'');
        }
        // Strict email validation — discard invalid
        if (out[h] && !isValidEmail(out[h])) {
          out[h] = '';
          S.validation.invalidEmails++;
        }
        if (out[h+'_2'] && !isValidEmail(out[h+'_2'])) out[h+'_2'] = '';
      } else if (type === 'phone' || type === 'whatsapp') {
        const sep = v.includes('/') ? '/' : v.includes(',') ? ',' : v.includes(' & ') ? '&' : null;
        let nums = sep ? v.split(sep).map(p=>p.trim()).filter(p=>p.length>=7) : [v.trim()];
        // Classify each phone number
        const validNums = [];
        nums.forEach(n => {
          const cls = classifyPhone(n);
          if (cls.valid) {
            validNums.push(n);
            if (cls.type !== 'IN') {
              out._phoneCountry = cls.type;
              S.validation.foreign++;
            }
          } else if (cls.type === 'LANDLINE') {
            S.validation.landlines++;
          }
        });
        out[h] = validNums[0] || '';
        if (validNums[1]) out[h+'_2'] = validNums[1];
      } else if (type === 'company' || type === 'contact' || type === 'city') {
        out[h] = toTitle(v);
      } else if (type === 'website') {
        out[h] = (v && !v.startsWith('http') && v.includes('.')) ? 'http://'+v : v;
      } else if (type === 'pincode' || type === 'id') {
        out[h] = v.replace(/\.0$/,'');
      } else {
        out[h] = v;
      }
    });
    return out;
  }).filter(row => Object.values(row).some(v => v !== '' && !String(v).startsWith('_')));

  // Step 2: Enforce mandatory rule — must have email OR valid mobile
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];
  S.clean = cleaned.filter(row => {
    const hasEmail = emailCols.some(c => row[c] && row[c] !== '' && isValidEmail(row[c]));
    const hasPhone = phoneCols.some(c => row[c] && row[c] !== '');
    if (!hasEmail && !hasPhone) {
      S.validation.dropped++;
      return false;
    }
    return true;
  });

  S.filtered = [...S.clean];
}

function findDuplicates() {
  S.dupGroups = [];
  const companyCols = colsByType('company');
  if (companyCols.length) {
    const cc = companyCols[0];
    const groups = {};
    S.clean.forEach((row, idx) => {
      const name = (row[cc]||'').toLowerCase().replace(/[^a-z0-9]/g,'').slice(0,20);
      if (!name || name.length < 4) return;
      if (!groups[name]) groups[name] = [];
      groups[name].push(idx);
    });
    S.dupGroups = Object.values(groups).filter(g => g.length > 1).slice(0, 50);
  }

  // Also deduplicate by email across all records
  const emailCols = colsByType('email');
  if (emailCols.length) {
    const ec = emailCols[0];
    const emailGroups = {};
    S.clean.forEach((row, idx) => {
      const email = (row[ec] || '').toLowerCase().trim();
      if (!email) return;
      if (!emailGroups[email]) emailGroups[email] = [];
      emailGroups[email].push(idx);
    });
    Object.values(emailGroups).forEach(indices => {
      if (indices.length > 1) {
        const rows = indices.map(i => S.clean[i]);
        S.dupGroups.push(rows);
      }
    });
  }
}

function keepCols()    { return S.headers.filter(h=>S.mapping[h]&&S.mapping[h].keep&&S.mapping[h].type!=='skip'); }
function colsByType(t) { return S.headers.filter(h=>S.mapping[h]&&S.mapping[h].type===t&&S.mapping[h].keep); }
function hasType(t)    { return colsByType(t).length > 0; }
function firstCol(t)   { return colsByType(t)[0]; }
function countFilled(col) { return S.clean.filter(r=>r[col]&&r[col]!=='').length; }
function countWithAny(cols){ return S.clean.filter(r=>cols.some(c=>r[c]&&r[c]!=='')).length; }
function groupBy(col, limit=10) {
  const counts = {};
  S.clean.forEach(r => {
    let v = r[col] || '';
    if (!v) return;
    if (v.length > 40) v = v.split(/[,;:]/)[0].trim().slice(0,35);
    counts[v] = (counts[v]||0)+1;
  });
  return Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,limit);
}
function toTitle(s) { return s.replace(/\w\S*/g, w=>w.charAt(0).toUpperCase()+w.slice(1).toLowerCase()); }
function sleep(ms)  { return new Promise(r=>setTimeout(r,ms)); }

/* ── Validation Helpers (Phase 2) ──────────────────────────────────── */
const INDIAN_MOBILE_RE = /^(\+91[\s\-]?)?[6-9]\d{9}$/;
const INTL_PHONE_RE    = /^\+(?!91)\d{1,3}[\s\-]?\d{5,14}$/;
const STRICT_EMAIL_RE  = /^[\w.+%-]+@[\w.-]+\.[a-z]{2,}$/i;

function isValidEmail(v) {
  return v ? STRICT_EMAIL_RE.test(v.trim()) : false;
}

function classifyPhone(v) {
  if (!v) return {valid:false, type:'INVALID', cleaned:''};
  const cleaned = v.trim().replace(/[\s\-\(\)]/g, '');
  // Indian mobile (with or without +91)
  if (INDIAN_MOBILE_RE.test(cleaned)) return {valid:true, type:'IN', cleaned};
  // Bare 10-digit Indian mobile
  if (/^[6-9]\d{9}$/.test(cleaned)) return {valid:true, type:'IN', cleaned};
  // International number
  if (INTL_PHONE_RE.test(cleaned)) {
    const m = cleaned.match(/^\+(\d{1,3})/);
    return {valid:true, type: m ? '+'+m[1] : 'INTL', cleaned};
  }
  // Generic number ≥10 digits (probably landline or invalid)
  if (/^\d{10,}$/.test(cleaned)) return {valid:false, type:'LANDLINE', cleaned};
  // Too short or garbage
  return {valid:false, type:'INVALID', cleaned};
}

function buildAllViews() {
  buildDashboard();
  buildAnalytics();
  buildTableControls();
  buildQuality();
  buildDedup();
}

function buildDashboard() { buildKPIs(); buildInsights(); buildMainCharts(); }

function buildKPIs() {
  const total = S.clean.length;
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];
  const webCols   = colsByType('website');
  const keep      = keepCols();
  const withEmail = emailCols.length ? countWithAny(emailCols) : null;
  const withPhone = phoneCols.length ? countWithAny(phoneCols) : null;
  const withWeb   = webCols.length   ? countWithAny(webCols)   : null;
  const completeness = Math.round(S.clean.reduce((sum,row)=>{
    const f = keep.filter(c=>row[c]&&row[c]!=='').length;
    return sum + f/keep.length;
  },0)/total*100);

  const kpis = [
    {label:'Total Records',    val:total.toLocaleString(), sub:'after cleaning', pill:'', cls:'kpi-blue',   icon:'📋'},
    {label:'Fields Mapped',    val:keep.length,            sub:`of ${S.headers.length} detected`, pill:'', cls:'kpi-indigo', icon:'🗂'},
    {label:'Data Completeness',val:completeness+'%',       sub:'avg fields filled',
     pill:`<span class="kpi-pill ${completeness>75?'pill-green':completeness>50?'pill-amber':'pill-red'}">${completeness>75?'Good':completeness>50?'Fair':'Needs Work'}</span>`,
     cls:'kpi-emerald', icon:'📊'},
  ];
  if (withEmail!==null) kpis.push({label:'With Email',val:withEmail.toLocaleString(),sub:`${Math.round(withEmail/total*100)}% coverage`,pill:`<span class="kpi-pill pill-blue">${Math.round(withEmail/total*100)}%</span>`,cls:'kpi-amber',icon:'📧'});
  if (withPhone!==null) kpis.push({label:'With Phone',val:withPhone.toLocaleString(),sub:`${Math.round(withPhone/total*100)}% coverage`,pill:`<span class="kpi-pill pill-green">${Math.round(withPhone/total*100)}%</span>`,cls:'kpi-cyan',icon:'📞'});
  if (withWeb!==null)   kpis.push({label:'With Website',val:withWeb.toLocaleString(),sub:`${Math.round(withWeb/total*100)}% have URL`,pill:'',cls:'kpi-violet',icon:'🌐'});
  if (S.dupGroups.length) kpis.push({label:'Possible Duplicates',val:S.dupGroups.length,sub:'groups — review',pill:`<span class="kpi-pill pill-red">Review</span>`,cls:'kpi-rose',icon:'🧹'});

  document.getElementById('kpiGrid').innerHTML = kpis.map(k=>`
    <div class="kpi-card ${k.cls}">
      <div class="kpi-icon">${k.icon}</div>
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.val}</div>
      <div class="kpi-footer">${k.pill}<span>${k.sub}</span></div>
    </div>`).join('');
}

function buildInsights() {
  const total = S.clean.length;
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];
  const iconMap = {
    target:{wrap:'ic-blue',icon:'🎯'}, warn:{wrap:'ic-rose',icon:'⚠️'},
    box:{wrap:'ic-amber',icon:'📦'},   web:{wrap:'ic-green',icon:'🌐'},
    pin:{wrap:'ic-violet',icon:'📍'},  check:{wrap:'ic-green',icon:'✅'},
    dedup:{wrap:'ic-rose',icon:'🧹'},
  };
  const insights = [];
  if (emailCols.length && phoneCols.length) {
    const both = S.clean.filter(r=>emailCols.some(c=>r[c]&&r[c].includes('@'))&&phoneCols.some(c=>r[c]&&r[c].length>5)).length;
    insights.push({t:'target',title:'Highly Contactable Records',desc:`${both.toLocaleString()} records (${Math.round(both/total*100)}%) have both email and phone — ideal for outreach campaigns.`});
    const neither = S.clean.filter(r=>!emailCols.some(c=>r[c]&&r[c].includes('@'))&&!phoneCols.some(c=>r[c]&&r[c].length>5)).length;
    if (neither>0) insights.push({t:'warn',title:'Missing Contact Details',desc:`${neither.toLocaleString()} records (${Math.round(neither/total*100)}%) lack both email and phone.`});
  }
  const prodCol = firstCol('product');
  if (prodCol) {
    const wp = countFilled(prodCol);
    insights.push({t:'box',title:'Product Coverage',desc:`${wp.toLocaleString()} records (${Math.round(wp/total*100)}%) have product/service information.`});
  }
  const webCols = colsByType('website');
  if (webCols.length) {
    const ww = countWithAny(webCols);
    insights.push({t:'web',title:'Online Presence',desc:`${ww.toLocaleString()} companies (${Math.round(ww/total*100)}%) have website data.`});
  }
  const cityCols = colsByType('city');
  if (cityCols.length) {
    const top = groupBy(cityCols[0],1);
    if (top.length) insights.push({t:'pin',title:'Top Location',desc:`"${top[0][0]}" is the most common city with ${top[0][1].toLocaleString()} records.`});
  }
  if (S.dupGroups.length) insights.push({t:'dedup',title:'Duplicate Records Detected',desc:`${S.dupGroups.length} potential duplicate groups found. Go to Deduplication to review.`});
  if (insights.length < 2) insights.push({t:'check',title:'Clean Dataset',desc:`${total.toLocaleString()} records processed and normalized. Ready for export.`});

  document.getElementById('insightGrid').innerHTML = insights.map(i=>{
    const ic = iconMap[i.t]||iconMap.check;
    return `<div class="insight-card"><div class="insight-icon-wrap ${ic.wrap}">${ic.icon}</div><div><div class="insight-title">${i.title}</div><div class="insight-desc">${i.desc}</div></div></div>`;
  }).join('');
}

function buildMainCharts() {
  killCharts();
  const sect1 = document.getElementById('dashCharts1');
  const sect2 = document.getElementById('dashCharts2');
  if (sect1) sect1.style.display = 'none';
  if (sect2) sect2.style.display = 'none';
  const r1 = document.getElementById('chartsRow1');
  const r2 = document.getElementById('chartsRow2');
  if (r1) r1.innerHTML = '';
  if (r2) r2.innerHTML = '';
  const cityCol = firstCol('city') || firstCol('location');
  if (cityCol) { const data=groupBy(cityCol,12); if(data.length>1) addBarChart(r1,'Records by '+cityCol,data.map(d=>d[0]),data.map(d=>d[1]),'#3B82F6','h260'); }
  const indCol=firstCol('industry')||firstCol('keyword'), prodCol=firstCol('product');
  if (indCol) { const data=groupBy(indCol,8); if(data.length>1) addDonutChart(r1,'By Industry',data.map(d=>d[0]),data.map(d=>d[1]),'h260'); }
  else if (prodCol) { const data=groupBy(prodCol,8); if(data.length>1) addDonutChart(r1,'By Product',data.map(d=>d[0]),data.map(d=>d[1]),'h260'); }
  const emailCols=colsByType('email'), phoneCols=[...colsByType('phone'),...colsByType('whatsapp')];
  if (emailCols.length&&phoneCols.length) {
    const total=S.clean.length;
    const both=S.clean.filter(r=>emailCols.some(c=>r[c]&&r[c].includes('@'))&&phoneCols.some(c=>r[c]&&r[c].length>5)).length;
    const emailOnly=S.clean.filter(r=>emailCols.some(c=>r[c]&&r[c].includes('@'))&&!phoneCols.some(c=>r[c]&&r[c].length>5)).length;
    const phoneOnly=S.clean.filter(r=>!emailCols.some(c=>r[c]&&r[c].includes('@'))&&phoneCols.some(c=>r[c]&&r[c].length>5)).length;
    addDonutChart(r2,'Contact Reachability',['Email + Phone','Email Only','Phone Only','Neither'],[both,emailOnly,phoneOnly,total-both-emailOnly-phoneOnly],'h260',['#3B82F6','#10B981','#F59E0B','#F43F5E']);
  }
  const webCols=colsByType('website');
  if (webCols.length) { const total=S.clean.length,withWeb=countWithAny(webCols); addDonutChart(r2,'Website Presence',['Has Website','No Website'],[withWeb,total-withWeb],'h260',['#10B981','#E2E8F0']); }

  // Show chart sections only if they actually have child nodes generated without crashing
  if (sect1 && r1 && r1.hasChildNodes()) sect1.style.display = 'block';
  if (sect2 && r2 && r2.hasChildNodes()) sect2.style.display = 'block';
}

function buildAnalytics() {
  const tabs = [];
  if (colsByType('city').length||colsByType('location').length) tabs.push({id:'geo',label:'📍 Geographic'});
  if (colsByType('industry').length||colsByType('keyword').length||colsByType('product').length) tabs.push({id:'seg',label:'🏭 Segments'});
  if (colsByType('email').length||colsByType('phone').length) tabs.push({id:'reach',label:'📞 Reachability'});
  tabs.push({id:'top',label:'🏆 Top Records'});
  tabs.push({id:'dist',label:'📊 Distribution'});
  document.getElementById('analyticsTabs').innerHTML = tabs.map((t,i)=>`<div class="tab-pill${i===0?' on':''}" onclick="switchTab('${t.id}',this)">${t.label}</div>`).join('');
  const content=document.getElementById('analyticsContent');
  content.innerHTML='';
  tabs.forEach((t,i)=>{ const div=document.createElement('div'); div.id='atab-'+t.id; div.style.display=i===0?'block':'none'; content.appendChild(div); renderAnalyticsTab(t.id,div); });
}

function switchTab(id, el) {
  document.querySelectorAll('.tab-pill').forEach(t=>t.classList.remove('on'));
  el.classList.add('on');
  document.querySelectorAll('[id^="atab-"]').forEach(d=>d.style.display='none');
  document.getElementById('atab-'+id).style.display='block';
}

function renderAnalyticsTab(id, c) {
  if (id==='geo') renderGeoTab(c);
  else if (id==='seg') renderSegTab(c);
  else if (id==='reach') renderReachTab(c);
  else if (id==='top') renderTopTab(c);
  else if (id==='dist') renderDistTab(c);
}

function renderGeoTab(c) {
  const cityCols=[...colsByType('city'),...colsByType('location')];
  if (!cityCols.length) { c.innerHTML='<div class="empty-state"><div class="es-icon">🗺</div>No geographic columns detected.</div>'; return; }
  const grid=document.createElement('div'); grid.className='chart-grid-2'; c.appendChild(grid);
  cityCols.slice(0,2).forEach(col=>{ const data=groupBy(col,15); if(data.length>1) addBarChart(grid,'Distribution by '+col,data.map(d=>d[0]),data.map(d=>d[1]),'#06B6D4','h320'); });
  if (cityCols[0]) {
    const data=groupBy(cityCols[0],20);
    const div=document.createElement('div'); div.className='chart-card span2'; div.style.marginTop='18px';
    const total=data.reduce((a,d)=>a+d[1],0);
    div.innerHTML=`<div class="chart-card-title">Top Cities / Locations</div><div class="top-list">${data.map((d,i)=>`
      <div class="tl-row">
        <div class="tl-rank ${i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':''}">${i+1}</div>
        <div class="tl-name">${d[0]}</div>
        <div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(d[1]/data[0][1]*100)}%"></div></div>
        <div class="tl-count">${d[1]}</div>
        <div class="tl-pct">${Math.round(d[1]/total*100)}%</div>
      </div>`).join('')}</div>`;
    c.appendChild(div);
  }
}

function renderSegTab(c) {
  const indCol=firstCol('industry')||firstCol('keyword'), prodCol=firstCol('product');
  const grid=document.createElement('div'); grid.className='chart-grid-2'; c.appendChild(grid);
  if (indCol) { const data=groupBy(indCol,12); addBarChart(grid,'By Industry',data.map(d=>d[0]),data.map(d=>d[1]),'#8B5CF6','h320'); addDonutChart(grid,'Industry Share',data.slice(0,8).map(d=>d[0]),data.slice(0,8).map(d=>d[1]),'h320'); }
  if (prodCol&&!indCol) { const data=groupBy(prodCol,12); addBarChart(grid,'By Product',data.map(d=>d[0]),data.map(d=>d[1]),'#F97316','h320'); addDonutChart(grid,'Product Share',data.slice(0,8).map(d=>d[0]),data.slice(0,8).map(d=>d[1]),'h320'); }
}

function renderReachTab(c) {
  const emailCols=colsByType('email'), phoneCols=[...colsByType('phone'),...colsByType('whatsapp')], webCols=colsByType('website');
  const total=S.clean.length;
  const grid=document.createElement('div'); grid.className='chart-grid-3'; c.appendChild(grid);
  const withBoth=S.clean.filter(r=>emailCols.some(c=>r[c]&&r[c].includes('@'))&&phoneCols.some(c=>r[c]&&r[c].length>5)).length;
  const emailOnly=S.clean.filter(r=>emailCols.some(c=>r[c]&&r[c].includes('@'))&&!phoneCols.some(c=>r[c]&&r[c].length>5)).length;
  const phoneOnly=S.clean.filter(r=>!emailCols.some(c=>r[c]&&r[c].includes('@'))&&phoneCols.some(c=>r[c]&&r[c].length>5)).length;
  addDonutChart(grid,'Contact Reachability',['Email + Phone','Email Only','Phone Only','Neither'],[withBoth,emailOnly,phoneOnly,total-withBoth-emailOnly-phoneOnly],'h260',['#3B82F6','#10B981','#F59E0B','#F43F5E']);
  if (emailCols.length) {
    const domains={};
    S.clean.forEach(r=>{ const e=emailCols.map(c=>r[c]).find(v=>v&&v.includes('@')); if(e){const d=e.split('@')[1];if(d) domains[d]=(domains[d]||0)+1;} });
    const top=Object.entries(domains).sort((a,b)=>b[1]-a[1]).slice(0,8);
    if (top.length>1) addBarChart(grid,'Top Email Domains',top.map(d=>d[0]),top.map(d=>d[1]),'#F59E0B','h260');
  }
  if (webCols.length) { const withWeb=countWithAny(webCols); addDonutChart(grid,'Website Presence',['Has Website','No Website'],[withWeb,total-withWeb],'h260',['#10B981','#E2E8F0']); }
}

function renderTopTab(c) {
  const companyCols=colsByType('company'), keep=keepCols();
  const grid=document.createElement('div'); grid.className='chart-grid-2'; c.appendChild(grid);
  const withScore=S.clean.map(row=>{ const filled=keep.filter(col=>row[col]&&row[col]!=='').length; return {...row,_score:Math.round(filled/keep.length*100)}; }).sort((a,b)=>b._score-a._score);
  const topCard=document.createElement('div'); topCard.className='chart-card';
  topCard.innerHTML=`<div class="chart-card-title">Most Complete Records</div><div class="top-list">${withScore.slice(0,10).map((row,i)=>{ const name=companyCols.length?row[companyCols[0]]||`Record ${i+1}`:`Record ${i+1}`; return `<div class="tl-row"><div class="tl-rank ${i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':''}">${i+1}</div><div class="tl-name">${name}</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${row._score}%"></div></div><div class="tl-count">${row._score}%</div></div>`; }).join('')}</div>`;
  grid.appendChild(topCard);
  const btmCard=document.createElement('div'); btmCard.className='chart-card';
  btmCard.innerHTML=`<div class="chart-card-title">Least Complete Records</div><div class="top-list">${withScore.slice(-10).reverse().map((row,i)=>{ const name=companyCols.length?row[companyCols[0]]||`Record ${i+1}`:`Record ${i+1}`; return `<div class="tl-row"><div class="tl-rank">${i+1}</div><div class="tl-name">${name}</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${row._score}%;background:var(--rose)"></div></div><div class="tl-count" style="color:var(--rose)">${row._score}%</div></div>`; }).join('')}</div>`;
  grid.appendChild(btmCard);
}

function renderDistTab(c) {
  const keep=keepCols().filter(h=>S.mapping[h].type!=='id');
  const grid=document.createElement('div'); grid.className='chart-grid-2'; c.appendChild(grid);
  const vals=keep.map(col=>Math.round(S.clean.filter(r=>r[col]&&r[col]!=='').length/S.clean.length*100));
  addBarChart(grid,'Fill Rate by Column (%)',keep,vals,'#6366F1','h320');
  const buckets={'0–25%':0,'26–50%':0,'51–75%':0,'76–100%':0};
  S.clean.forEach(row=>{ const f=keep.filter(c=>row[c]&&row[c]!=='').length/keep.length*100; if(f<=25)buckets['0–25%']++;else if(f<=50)buckets['26–50%']++;else if(f<=75)buckets['51–75%']++;else buckets['76–100%']++; });
  addBarChart(grid,'Records by Completeness',Object.keys(buckets),Object.values(buckets),'#10B981','h320');
}

function buildQuality() {
  const keep=keepCols(), total=S.clean.length, c=document.getElementById('qualityContent');
  c.innerHTML='';
  const avgFill=Math.round(S.clean.reduce((sum,row)=>{ const f=keep.filter(col=>row[col]&&row[col]!=='').length; return sum+f/keep.length; },0)/total*100);
  const scoreColor=avgFill>75?'var(--emerald)':avgFill>50?'var(--amber)':'var(--rose)';
  const topRow=document.createElement('div');
  topRow.style.cssText='display:grid;grid-template-columns:220px 1fr;gap:20px;margin-bottom:22px';
  topRow.innerHTML=`
    <div class="chart-card" style="display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center">
      <div style="font-size:64px;font-weight:900;color:${scoreColor};font-family:var(--font-d);line-height:1">${avgFill}%</div>
      <div style="font-size:14px;font-weight:700;margin:8px 0 4px;color:var(--text)">Quality Score</div>
      <div style="font-size:12px;color:var(--text-3)">Average completeness across ${total.toLocaleString()} records</div>
    </div>
    <div class="chart-card">
      <div class="chart-card-title">Field-by-Field Fill Rate</div>
      <div class="qual-grid" id="qualGrid"></div>
    </div>`;
  c.appendChild(topRow);
  const botRow=document.createElement('div');
  botRow.style.cssText='display:grid;grid-template-columns:1fr 1fr;gap:18px';
  botRow.innerHTML=`<div class="chart-card"><div class="chart-card-title">Email Validation</div><div id="emailQual"></div></div><div class="chart-card"><div class="chart-card-title">Phone Validation</div><div id="phoneQual"></div></div>`;
  c.appendChild(botRow);
  const qg=document.getElementById('qualGrid');
  keep.forEach(col=>{ const filled=S.clean.filter(r=>r[col]&&r[col]!=='').length,pct=Math.round(filled/total*100),color=pct>75?'var(--emerald)':pct>40?'var(--amber)':'var(--rose)',ft=FT[S.mapping[col].type]; qg.innerHTML+=`<div class="qual-row"><div class="qual-label">${ft?ft.icon:''} ${col}</div><div class="qual-bar-bg"><div class="qual-bar-fg" style="width:${pct}%;background:${color}"></div></div><div class="qual-val" style="color:${color}">${pct}%</div></div>`; });
  const emailCols=colsByType('email'), eq=document.getElementById('emailQual');
  if (emailCols.length) {
    let valid=0,invalid=0,empty=0;
    S.clean.forEach(r=>{ const e=emailCols.map(c=>r[c]).find(v=>v); if(!e)empty++;else if(/^[\w.+%-]+@[\w.-]+\.[a-z]{2,}$/i.test(e))valid++;else invalid++; });
    eq.innerHTML=`<div class="top-list"><div class="tl-row"><div class="tl-name" style="color:var(--emerald)">✅ Valid</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(valid/total*100)}%;background:var(--emerald)"></div></div><div class="tl-count" style="color:var(--emerald)">${valid}</div></div><div class="tl-row"><div class="tl-name" style="color:var(--rose)">❌ Invalid</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(invalid/total*100)}%;background:var(--rose)"></div></div><div class="tl-count" style="color:var(--rose)">${invalid}</div></div><div class="tl-row"><div class="tl-name" style="color:var(--text-4)">⬜ Missing</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(empty/total*100)}%;background:var(--border-2)"></div></div><div class="tl-count" style="color:var(--text-4)">${empty}</div></div></div>`;
  } else eq.innerHTML='<div class="empty-state" style="padding:20px">No email columns detected</div>';
  const phoneCols=[...colsByType('phone'),...colsByType('whatsapp')], pq=document.getElementById('phoneQual');
  if (phoneCols.length) {
    let single=0,multi=0,empty=0;
    S.clean.forEach(r=>{ const p=phoneCols.map(c=>r[c]).find(v=>v); if(!p)empty++;else if(p.includes('/')&&p.length>12)multi++;else single++; });
    pq.innerHTML=`<div class="top-list"><div class="tl-row"><div class="tl-name" style="color:var(--emerald)">✅ Single</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(single/total*100)}%;background:var(--emerald)"></div></div><div class="tl-count" style="color:var(--emerald)">${single}</div></div><div class="tl-row"><div class="tl-name" style="color:var(--amber)">📞 Multi (split)</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(multi/total*100)}%;background:var(--amber)"></div></div><div class="tl-count" style="color:var(--amber)">${multi}</div></div><div class="tl-row"><div class="tl-name" style="color:var(--text-4)">⬜ Missing</div><div class="tl-bar-bg"><div class="tl-bar-fg" style="width:${Math.round(empty/total*100)}%;background:var(--border-2)"></div></div><div class="tl-count" style="color:var(--text-4)">${empty}</div></div></div>`;
  } else pq.innerHTML='<div class="empty-state" style="padding:20px">No phone columns detected</div>';
}

function buildDedup() {
  const c=document.getElementById('dedupContent');
  c.innerHTML='';
  document.getElementById('dedupCount').textContent = S.dupGroups.length?`${S.dupGroups.length} duplicate groups found`:'';
  if (!S.dupGroups.length) { c.innerHTML='<div class="empty-state"><div class="es-icon">✅</div>No duplicate company records detected. Your data looks clean.</div>'; return; }
  const companyCols=colsByType('company'), phoneCols=colsByType('phone'), emailCols=colsByType('email'), cc=companyCols[0];
  const notice=document.createElement('div'); notice.className='alert-banner alert-warn'; notice.style.marginBottom='18px';
  notice.innerHTML=`⚠️ ${S.dupGroups.length} groups of potential duplicates found. Review and remove as needed. <strong>Changes apply to the clean dataset and reflect in exports.</strong>`;
  c.appendChild(notice);
  S.dupGroups.forEach((group,gi)=>{
    const rows=group.map(idx=>S.clean[idx]);
    const companyName=cc?rows[0][cc]:`Group ${gi+1}`;
    const card=document.createElement('div'); card.className='dedup-card'; card.id=`dg-${gi}`;
    card.innerHTML=`<div class="dedup-header"><div><div class="dedup-title">🏢 ${companyName}</div><div class="dedup-meta">${rows.length} similar records</div></div><div style="display:flex;gap:8px"><button class="btn btn-danger btn-sm" onclick="keepFirst(${gi})">Keep First, Remove Others</button></div></div><div class="dedup-rows">${rows.map((row,ri)=>{const phone=phoneCols.length?row[phoneCols[0]]||'—':'—';const email=emailCols.length?row[emailCols[0]]||'—':'—';return `<div class="dedup-row-item ${ri===0?'primary':'dupe'}"><span class="badge ${ri===0?'b-blue':'b-rose'}" style="width:54px;justify-content:center">${ri===0?'KEEP':'DUPE'}</span><span style="flex:1;font-weight:${ri===0?700:400}">${cc?row[cc]||'—':'Row '+(ri+1)}</span><span style="color:var(--text-3);font-size:11px;min-width:120px">📞 ${phone}</span><span style="color:var(--text-3);font-size:11px;min-width:160px">📧 ${email}</span></div>`;}).join('')}</div>`;
    c.appendChild(card);
  });
}

function keepFirst(gi) {
  const toRemove=new Set(S.dupGroups[gi].slice(1));
  S.clean=S.clean.filter((_,idx)=>!toRemove.has(idx));
  S.filtered=[...S.clean];
  S.dupGroups.splice(gi,1);
  document.getElementById(`dg-${gi}`).style.opacity='0.4';
  document.getElementById(`dg-${gi}`).style.pointerEvents='none';
  document.getElementById('dedupCount').textContent=S.dupGroups.length?`${S.dupGroups.length} duplicate groups remaining`:'✅ All cleaned!';
  document.getElementById('sbFileMeta').textContent=`${S.clean.length.toLocaleString()} records · ${keepCols().length} fields`;
}

function removeAllDupes() {
  if (!S.dupGroups.length) return;
  const toRemove=new Set();
  S.dupGroups.forEach(g=>g.slice(1).forEach(idx=>toRemove.add(idx)));
  S.clean=S.clean.filter((_,idx)=>!toRemove.has(idx));
  S.filtered=[...S.clean];
  S.dupGroups=[];
  buildDedup(); buildKPIs();
  document.getElementById('sbFileMeta').textContent=`${S.clean.length.toLocaleString()} records · ${keepCols().length} fields`;
}

function buildTableControls() {
  const keep=keepCols(), cf=document.getElementById('colFilter');
  cf.innerHTML='<option value="">Filter by column…</option>';
  keep.forEach(c=>{ cf.innerHTML+=`<option value="${c}">${c}</option>`; });
  S.filtered=[...S.clean]; renderTable();
}

function onColFilterChange() {
  const col=document.getElementById('colFilter').value, vf=document.getElementById('valFilter');
  if (col) {
    const vals=[...new Set(S.clean.map(r=>r[col]||'').filter(Boolean))].sort().slice(0,200);
    vf.innerHTML='<option value="">All values</option>'+vals.map(v=>`<option value="${v}">${v.slice(0,60)}</option>`).join('');
  } else vf.innerHTML='<option value="">All values</option>';
  filterTable();
}

function filterTable() {
  // BUG FIX: searchBox/colFilter/valFilter only exist inside the table view.
  // Without this guard, calling filterTable() from any other context
  // throws a TypeError and silently breaks all table search/filtering.
  const searchEl = document.getElementById('searchBox');
  const colEl    = document.getElementById('colFilter');
  const valEl    = document.getElementById('valFilter');
  if (!searchEl || !colEl || !valEl) return;

  const q=searchEl.value.toLowerCase();
  const colF=colEl.value, valF=valEl.value, keep=keepCols();
  S.filtered=S.clean.filter(row=>{ const mQ=!q||keep.some(c=>String(row[c]||'').toLowerCase().includes(q)); const mV=!valF||String(row[colF]||'')===valF; return mQ&&mV; });
  S.page=1; renderTable();
}

function renderTable() {
  const keep=keepCols(), head=document.getElementById('tHead'), body=document.getElementById('tBody');
  head.innerHTML='<tr>'+keep.map((c,i)=>{ const ft=FT[S.mapping[c].type],icon=ft?ft.icon:'',dir=S.sortCol===i?(S.sortDir===1?' ↑':' ↓'):''; return `<th onclick="sortTable(${i})" title="Sort by ${c}">${icon} ${c}${dir}</th>`; }).join('')+'<th style="width:110px;text-align:center">Actions</th></tr>';
  let data=[...S.filtered];
  if (S.sortCol!==null) { const col=keep[S.sortCol]; data.sort((a,b)=>String(a[col]||'').localeCompare(String(b[col]||''))*S.sortDir); }
  const start=(S.page-1)*S.pageSize, page=data.slice(start,start+S.pageSize);
  body.innerHTML=page.map((row,ri)=>{
    const idx = start + ri;
    return `<tr>${keep.map(c=>{ const type=S.mapping[c].type; let v=row[c]||'';
    if(type==='email'&&v) v=`<a href="mailto:${v}" style="color:var(--blue)">${v}</a>`;
    else if(type==='website'&&v) v=`<a href="${v}" target="_blank" style="color:var(--emerald)">${v.replace(/https?:\/\//,'').slice(0,36)}</a>`;
    else if(type==='phone'||type==='whatsapp') { const cls=row._phoneCountry&&row._phoneCountry!=='IN'?'foreign-flag':''; v=`<span class="mono ${cls}" style="color:var(--emerald)">${v}${row._phoneCountry&&row._phoneCountry!=='IN'?' <span class="badge b-amber" style="font-size:9px">'+row._phoneCountry+'</span>':''}</span>`; }
    else if(type==='id') v=v?`<span class="badge b-slate">#${v}</span>`:'';
    else if(type==='member'&&v) v=`<span class="badge b-emerald">✓ ${v}</span>`;
    else if(type==='company') v=`<span style="font-weight:700;color:var(--text)">${v}</span>`;
    else if(type==='industry'||type==='keyword') v=v?`<span class="badge b-violet">${v.slice(0,30)}</span>`:'';
    else if(type==='status') v=v?`<span class="badge b-amber">${v.slice(0,20)}</span>`:'';
    return `<td title="${String(row[c]||'').replace(/"/g,'')}">${v}</td>`; }).join('')}<td class="row-actions"><button class="act-btn act-view" onclick="showContactPanel(${idx})" title="View & Call Logs">👁</button><button class="act-btn act-edit" onclick="editRow(${idx})" title="Edit">✏️</button><button class="act-btn act-del" onclick="deleteRow(${idx})" title="Delete">🗑</button></td></tr>`;
  }).join('');
  document.getElementById('tblMeta').textContent=`${S.filtered.length.toLocaleString()} records`;
  document.getElementById('tblCount').textContent=`Showing ${start+1}–${Math.min(start+S.pageSize,data.length)} of ${S.filtered.length.toLocaleString()}`;
  renderPag(data.length);
}

function sortTable(i) { if(S.sortCol===i)S.sortDir*=-1;else{S.sortCol=i;S.sortDir=1;} renderTable(); }

function renderPag(total) {
  const pages=Math.ceil(total/S.pageSize), pg=document.getElementById('pagDiv');
  if (pages<=1) { pg.innerHTML=''; return; }
  let html=`<span class="pag-info">${pages} pages</span>`;
  html+=`<button class="pag-btn" onclick="goPage(${S.page-1})" ${S.page===1?'disabled':''}>‹</button>`;
  const range=[];
  for(let i=1;i<=pages;i++){ if(i===1||i===pages||(i>=S.page-2&&i<=S.page+2))range.push(i); else if(range[range.length-1]!=='…')range.push('…'); }
  range.forEach(p=>{ if(p==='…')html+=`<span class="pag-info">…</span>`;else html+=`<button class="pag-btn${p===S.page?' on':''}" onclick="goPage(${p})">${p}</button>`; });
  html+=`<button class="pag-btn" onclick="goPage(${S.page+1})" ${S.page===pages?'disabled':''}>›</button>`;
  pg.innerHTML=html;
}
function goPage(p) { const pages=Math.ceil(S.filtered.length/S.pageSize); S.page=Math.max(1,Math.min(p,pages)); renderTable(); }

function addBarChart(parent, title, labels, data, color, hClass='h260', horizontal=false) {
  const card=document.createElement('div'); card.className='chart-card';
  card.innerHTML=`<div class="chart-card-title">${title}</div><div class="chart-wrap ${hClass}"><canvas></canvas></div>`;
  parent.appendChild(card);
  const ctx=card.querySelector('canvas').getContext('2d');
  const dark=isDarkTheme();
  const textColor=dark?'#8B8DA0':'#7C7E92';
  const gridColor=dark?'rgba(255,255,255,.06)':'rgba(0,0,0,.06)';
  
  try {
    const ch=new Chart(ctx,{type:'bar',data:{labels,datasets:[{data,backgroundColor:color+'18',borderColor:color,borderWidth:1.5,borderRadius:6,borderSkipped:false,hoverBackgroundColor:color+'40'}]},options:{indexAxis:horizontal?'y':'x',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`Count: ${ctx.parsed[horizontal?'x':'y']}`}}},scales:{x:{grid:{color:gridColor,drawBorder:false},ticks:{color:textColor,font:{size:10,family:'Inter'},maxRotation:38,autoSkipPadding:8}},y:{grid:{color:gridColor,drawBorder:false},ticks:{color:textColor,font:{size:10,family:'Inter'}}}}}});
    S.charts.push(ch);
  } catch(err) { console.error('Chart.js error:', err); }
}

function addDonutChart(parent, title, labels, data, hClass='h260', colors) {
  const cols=colors||PALETTE, total=data.reduce((a,v)=>a+v,0);
  const card=document.createElement('div'); card.className='chart-card';
  card.innerHTML=`<div class="chart-card-title">${title}</div><div class="chart-wrap ${hClass}" style="position:relative"><canvas></canvas><div class="donut-center"><div class="dc-val">${total.toLocaleString()}</div><div class="dc-lbl">Total</div></div></div>`;
  parent.appendChild(card);
  const ctx=card.querySelector('canvas').getContext('2d');
  const dark=isDarkTheme();
  const textColor=dark?'#8B8DA0':'#7C7E92';
  const borderWidth=dark?1:0;
  const borderColor=dark?'var(--surf)':'#ffffff';

  try {
    const ch=new Chart(ctx,{type:'doughnut',data:{labels,datasets:[{data,backgroundColor:cols.slice(0,data.length),borderColor:borderColor,borderWidth:borderWidth,hoverOffset:8}]},options:{responsive:true,maintainAspectRatio:false,cutout:'64%',plugins:{legend:{position:'right',labels:{color:textColor,font:{size:11,family:'Inter'},boxWidth:12,padding:8,usePointStyle:true}},tooltip:{callbacks:{label:ctx=>`${ctx.label}: ${ctx.raw.toLocaleString()} (${Math.round(ctx.raw/total*100)}%)`}}}}});
    S.charts.push(ch);
  } catch(err) { console.error('Chart.js error:', err); }
}

function killCharts() { S.charts.forEach(c=>c.destroy&&c.destroy()); S.charts=[]; }

async function downloadPDF() {
  if (!S.clean.length) { alert('No data to export.'); return; }
  const btn = document.getElementById('btnPDF');
  if (btn) { btn.innerHTML = '<span class="spinner-inline"></span> Generating…'; btn.disabled = true; }

  const keep      = keepCols();
  const total     = S.clean.length;
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];
  const withEmail = emailCols.length ? countWithAny(emailCols) : null;
  const withPhone = phoneCols.length ? countWithAny(phoneCols) : null;
  const completeness = Math.round(S.clean.reduce((sum,row)=>{ const f=keep.filter(c=>row[c]&&row[c]!=='').length; return sum+f/keep.length; },0)/total*100);
  const fieldQuality = keep.map(col=>{ const filled=S.clean.filter(r=>r[col]&&r[col]!=='').length; const ft=FT[S.mapping[col].type]; return {label:`${ft?ft.icon:''} ${col}`,pct:Math.round(filled/total*100)}; });

  if (API_BASE) {
    try {
      const res = await fetch(`${API_BASE}/api/export/pdf`, {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
          fileName: S.fileName,
          sheetName: S.sheetName,
          total, fields: keep.length, completeness,
          withEmail, withPhone,
          fieldQuality,
          records: S.clean.slice(0, 300),
          columns: keep.slice(0, 8),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = S.fileName.replace(/\.[^.]+$/,'') + '_CRM_Report.pdf';
      a.click(); URL.revokeObjectURL(url);
    } catch (err) {
      console.warn('Backend PDF failed, falling back to print:', err);
      _printPDFFallback(keep, total, withEmail, withPhone, completeness);
    }
  } else {
    _printPDFFallback(keep, total, withEmail, withPhone, completeness);
  }
  if (btn) { btn.innerHTML = '📄 PDF'; btn.disabled = false; }
}

function _printPDFFallback(keep, total, withEmail, withPhone, completeness) {
  const dispCols=keep.slice(0,7);
  const tableRows=S.clean.slice(0,300).map(row=>`<tr>${dispCols.map(c=>`<td>${(row[c]||'').toString().slice(0,50)}</td>`).join('')}</tr>`).join('');
  const html=`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>CRM Report — ${S.fileName}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{font-family:Arial,sans-serif;color:#0F172A;font-size:11px}.cover{background:linear-gradient(135deg,#0F172A,#1E3A8A);color:white;padding:48px;page-break-after:always}.cover h1{font-size:28px;font-weight:900;margin-bottom:8px}.cover-sub{font-size:11px;opacity:.6;margin-bottom:32px}.kpis{display:flex;gap:12px}.kpi{background:rgba(255,255,255,.1);border-radius:8px;padding:14px 18px;flex:1;text-align:center}.kpi strong{font-size:22px;display:block}.kpi span{font-size:9px;opacity:.7;text-transform:uppercase}.section{padding:32px 48px}.h2{font-size:13px;font-weight:800;color:#1E3A8A;border-left:4px solid #3B82F6;padding-left:10px;margin-bottom:14px}.qual-row{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:10px}.qual-label{width:140px}.qual-bg{flex:1;background:#F1F5F9;border-radius:3px;height:6px;overflow:hidden}.qual-fill{height:100%;border-radius:3px}.qual-val{width:32px;text-align:right;font-weight:700}table{width:100%;border-collapse:collapse;font-size:9px}thead th{background:#0F172A;color:white;padding:7px 9px;text-align:left;font-size:8px;text-transform:uppercase}tbody tr:nth-child(even){background:#F8FAFC}tbody td{padding:6px 9px;border-bottom:1px solid #E2E8F0}@media print{@page{margin:0;size:A4}body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}</style></head><body>
  <div class="cover"><div style="font-size:9px;opacity:.5;margin-bottom:12px;letter-spacing:1.5px;text-transform:uppercase">CRM Intelligence · Export Report</div><h1>📊 ${S.fileName}</h1><div class="cover-sub">Sheet: ${S.sheetName} · Generated: ${new Date().toLocaleString()}</div><div class="kpis"><div class="kpi"><strong>${total.toLocaleString()}</strong><span>Records</span></div><div class="kpi"><strong>${keep.length}</strong><span>Fields</span></div>${withEmail!==null?`<div class="kpi"><strong>${withEmail}</strong><span>With Email</span></div>`:''} ${withPhone!==null?`<div class="kpi"><strong>${withPhone}</strong><span>With Phone</span></div>`:''}<div class="kpi"><strong>${completeness}%</strong><span>Quality</span></div></div></div>
  <div class="section"><div class="h2">Data Quality by Field</div>${keep.map(col=>{const filled=S.clean.filter(r=>r[col]&&r[col]!=='').length,pct=Math.round(filled/total*100),color=pct>75?'#10B981':pct>40?'#F59E0B':'#F43F5E';return `<div class="qual-row"><div class="qual-label">${col}</div><div class="qual-bg"><div class="qual-fill" style="width:${pct}%;background:${color}"></div></div><div class="qual-val" style="color:${color}">${pct}%</div></div>`;}).join('')}</div>
  <div class="section"><div class="h2">CRM Data (first 300 records)</div><table><thead><tr>${dispCols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${tableRows}</tbody></table></div>
  </body></html>`;
  const w=window.open('','_blank'); w.document.write(html); w.document.close(); w.focus(); setTimeout(()=>w.print(),900);
}

function downloadExcel() {
  if (!S.clean.length) { alert('No data to export.'); return; }

  const wb = XLSX.utils.book_new();

  // Build columns to export (all kept cols + secondary _2 variants if present)
  const keep = keepCols();
  const cols = [];
  keep.forEach(c => {
    cols.push(c);
    if (S.clean.some(r => r[c + '_2'])) cols.push(c + '_2');
  });

  // Use original column headers; secondary columns get a " 2" suffix
  const headers = cols.map(c => c.endsWith('_2') ? c.replace(/_2$/, '') + ' 2' : c);

  // Build data rows — empty string for missing values
  const rows = S.clean.map(row => cols.map(c => (row[c] !== undefined && row[c] !== null) ? row[c] : ''));

  // Single sheet with original-style headers + cleaned data
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);

  // Auto-width columns by field type
  ws['!cols'] = cols.map(c => {
    const base = c.replace(/_2$/, '');
    const t = S.mapping[base] ? S.mapping[base].type : 'other';
    return { wch: t === 'address' || t === 'product' ? 55 : t === 'company' ? 35 : t === 'phone' ? 20 : t === 'email' ? 35 : t === 'website' ? 40 : t === 'id' ? 8 : 22 };
  });

  XLSX.utils.book_append_sheet(wb, ws, 'Data');

  // File name: original name + _cleaned
  const outName = S.fileName.replace(/\.(xlsx?|xls|csv|txt)$/i, '') + '_cleaned.xlsx';
  XLSX.writeFile(wb, outName);
}
function toggleSidebarCollapse() {
  // BUG FIX: Sidebar collapse state was not persisted to localStorage,
  // so refreshing the page always reset the sidebar to expanded.
  document.body.classList.toggle('sb-collapsed');
  const collapsed = document.body.classList.contains('sb-collapsed');
  const btn = document.getElementById('sbToggleBtn');
  if (btn) btn.innerHTML = collapsed ? '›' : '‹';
  localStorage.setItem('crm-sb-collapsed', collapsed ? '1' : '');
}

function showView(id) {
  // Guard: redirect to upload if no data and trying to access data views
  const dataViews = ['dashboard','analytics','table','quality','dedup'];
  if (dataViews.includes(id) && !S.clean.length) return showView('upload');

  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-'+id).classList.add('active');
  document.querySelectorAll('.nav-item[data-view]').forEach(n=>n.classList.remove('active'));
  const nav=document.querySelector(`.nav-item[data-view="${id}"]`);
  if (nav) nav.classList.add('active');
  S.currentView=id;
  const titles={upload:'Import File',mapping:'Field Mapping',processing:'Processing',dashboard:'Dashboard',analytics:'Analytics',table:'Data Table',quality:'Data Quality',dedup:'Deduplication',history:'Upload History'};
  document.getElementById('topTitle').textContent=titles[id]||id;
  if (!['upload','mapping','processing'].includes(id))
    document.getElementById('topSub').textContent=`${S.fileName} · ${S.clean.length.toLocaleString()} records`;
  else
    document.getElementById('topSub').textContent='Supports .xlsx · .xls · .csv · .txt · .pdf — any column structure';
  if (id==='table') renderTable();
  if (id==='history') loadHistory();
}

function resetApp() {
  S.rawData=[];S.headers=[];S.mapping={};S.clean=[];S.fileName='';S.sheetName='';
  S.filtered=[];S.page=1;S.sortCol=null;S.sortDir=1;S.dupGroups=[];
  S.validation={dropped:0,invalidEmails:0,landlines:0,foreign:0,total:0};
  killCharts();
  document.getElementById('fileInput').value='';
  document.getElementById('topActions').style.display='none';
  document.getElementById('sbFileCard').classList.add('hidden');
  document.getElementById('procSteps').innerHTML='';
  document.getElementById('progFill').style.width='0%';
  showView('upload');
}

/* ══════════════════════════════════════════════════════════════════════
   CRM PHASE 2 — Save to DB, Edit, Delete, Contact Panel, Call Logs, VCF
   ══════════════════════════════════════════════════════════════════════ */

async function saveToCRM() {
  if (!API_BASE) { alert('Backend not configured. Set CRM_API_BASE in config.js'); return; }
  if (!S.clean.length) { alert('No data to save.'); return; }
  const btn = document.getElementById('btnSaveCRM');
  if (btn) { btn.innerHTML = '<span class="spinner-inline"></span> Saving…'; btn.disabled = true; }

  const companyCols = colsByType('company');
  const contactCols = colsByType('contact');
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];
  const cityCols = colsByType('city');
  const addressCols = colsByType('address');
  const pinCols = colsByType('pincode');
  const webCols = colsByType('website');
  const indCols = [...colsByType('industry'), ...colsByType('keyword')];
  const prodCols = colsByType('product');

  const contacts = S.clean.map(row => ({
    company_name: companyCols.length ? row[companyCols[0]] || null : null,
    contact_name: contactCols.length ? row[contactCols[0]] || null : null,
    email_primary: emailCols.length ? row[emailCols[0]] || null : null,
    email_secondary: emailCols.length && row[emailCols[0]+'_2'] ? row[emailCols[0]+'_2'] : null,
    phone_primary: phoneCols.length ? row[phoneCols[0]] || null : null,
    phone_secondary: phoneCols.length && row[phoneCols[0]+'_2'] ? row[phoneCols[0]+'_2'] : null,
    phone_country: row._phoneCountry || 'IN',
    whatsapp: colsByType('whatsapp').length ? row[colsByType('whatsapp')[0]] || null : null,
    address: addressCols.length ? row[addressCols[0]] || null : null,
    city: cityCols.length ? row[cityCols[0]] || null : null,
    pincode: pinCols.length ? row[pinCols[0]] || null : null,
    website: webCols.length ? row[webCols[0]] || null : null,
    industry: indCols.length ? row[indCols[0]] || null : null,
    product: prodCols.length ? row[prodCols[0]] || null : null,
    raw_data: row,
  }));

  try {
    const res = await fetch(`${API_BASE}/api/contacts/batch`, {
      method: 'POST',
      headers: apiHeaders(),
      body: JSON.stringify({
        file_name: S.fileName,
        sheet_name: S.sheetName,
        mapping: S.mapping,
        contacts,
        user_email: S.userEmail || null,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    S.sessionId = data.session_id;
    const msg = `✅ Saved ${data.imported} contacts to CRM.`
      + (data.skipped ? ` ${data.skipped} skipped (no email/phone).` : '')
      + (data.flagged_foreign ? ` ${data.flagged_foreign} foreign numbers flagged.` : '');
    showNotification(msg, 'success');
  } catch(err) {
    showNotification('Failed to save: ' + err.message, 'error');
  }
  if (btn) { btn.innerHTML = '💾 Save to CRM'; btn.disabled = false; }
}

async function loadHistory() {
  const content = document.getElementById('historyContent');
  if (!content) return;
  if (!API_BASE) {
    content.innerHTML = '<div class="empty-state">Backend not configured.</div>';
    return;
  }
  try {
    const email = S.userEmail || '';
    const res = await fetch(`${API_BASE}/api/history?email=${encodeURIComponent(email)}`, { headers: apiHeaders() });
    const data = await res.json();
    if (!data.sessions?.length) {
      content.innerHTML = '<div class="empty-state">No saved sessions yet. Import a file and click Save to CRM.</div>';
      return;
    }
    content.innerHTML = `<div class="chart-card"><table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="padding:10px;text-align:left">File</th>
        <th style="padding:10px;text-align:left">Sheet</th>
        <th style="padding:10px">Records</th>
        <th style="padding:10px">Imported</th>
        <th style="padding:10px">Date</th>
        <th style="padding:10px">Actions</th>
      </tr></thead>
      <tbody>${data.sessions.map((s) => {
        const safeName = String(s.file_name || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        return `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:10px;font-weight:600">${s.file_name}</td>
          <td style="padding:10px;color:var(--text-3)">${s.sheet_name}</td>
          <td style="padding:10px;text-align:center">${s.total_records || '—'}</td>
          <td style="padding:10px;text-align:center;color:var(--emerald)">${s.imported || '—'}</td>
          <td style="padding:10px;color:var(--text-3);font-size:11px">${new Date(s.upload_date).toLocaleString()}</td>
          <td style="padding:10px"><button class="btn btn-secondary btn-sm" onclick="reloadSession(${s.id},'${safeName}', this)">↺ Reload</button>
          <button class="btn btn-primary btn-sm" style="margin-left:4px" onclick="exportSessionWithCalls(${s.id},'${safeName}')">⬇ Export+Calls</button>
          <button class="btn btn-danger btn-sm" style="margin-left:4px" onclick="deleteSession(${s.id})">🗑</button></td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>`;
  } catch (err) {
    content.innerHTML = `<div class="empty-state">Could not load history: ${err.message}</div>`;
  }
}

async function reloadSession(sessionId, fileName, btnEl) {
  try {
    if (btnEl) btnEl.innerHTML = `<span class="spinner-inline"></span> Loading…`;
    const res = await fetch(`${API_BASE}/api/history/${sessionId}?page_size=1000`, { headers: apiHeaders() });
    const data = await res.json();
    if (!data.ok || !data.records.length) { showNotification('No records found.', 'error'); return; }
    S.rawData = data.records;
    S.headers = Object.keys(data.records[0]);
    S.fileName = fileName;
    S.sheetName = data.sheet_name;
    S.mapping = data.mapping || {};
    S.sessionId = sessionId;
    if (!Object.keys(S.mapping).length) buildMapping();
    else startProcessing();
  } catch (err) {
    showNotification(`Reload failed: ${err.message}`, 'error');
  } finally {
    if (btnEl) btnEl.innerHTML = `↺ Reload`;
  }
}

async function deleteSession(sessionId) {
  if (!confirm('Delete this history entry?')) return;
  try {
    await fetch(`${API_BASE}/api/history/${sessionId}`, { method: 'DELETE', headers: apiHeaders() });
    loadHistory();
  } catch (err) {
    showNotification(`Delete failed: ${err.message}`, 'error');
  }
}

async function exportSessionWithCalls(sessionId, fileName) {
  showNotification('Building export with call logs…', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/history/${sessionId}/export`, { headers: apiHeaders() });
    const data = await res.json();
    if (!data.ok || !data.records.length) { alert('No records found.'); return; }

    const wb = XLSX.utils.book_new();
    const rows = data.records;

    // All column keys — original cols first, call log cols (_*) at end
    const allKeys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
    const dataCols = allKeys.filter((k) => !k.startsWith('_'));
    const callCols = allKeys.filter((k) => k.startsWith('_'));
    const finalCols = [...dataCols, ...callCols];

    // Friendly header names for call log columns
    const colLabel = {
      _last_call_date: 'Last Call Date',
      _last_call_type: 'Last Call Type',
      _last_outcome: 'Last Outcome',
      _last_notes: 'Last Notes',
      _total_calls: 'Total Calls',
      _next_action: 'Next Action',
      _next_action_date: 'Next Action Date',
      _all_call_summary: 'All Calls Summary',
    };
    const headers = finalCols.map((k) => colLabel[k] || k);
    const sheetRows = rows.map((row) => finalCols.map((k) => row[k] ?? ''));

    const ws = XLSX.utils.aoa_to_sheet([headers, ...sheetRows]);
    ws['!cols'] = finalCols.map((k) => ({ wch: k.includes('summary') ? 80 : k.startsWith('_') ? 22 : 25 }));
    XLSX.utils.book_append_sheet(wb, ws, 'Data + Call Logs');

    const outName = (fileName || 'export').replace(/\.(xlsx?|csv|txt)$/i, '') + '_with_calls.xlsx';
    XLSX.writeFile(wb, outName);
    showNotification(`✅ Exported ${rows.length} records with call history`, 'success');
  } catch (err) {
    showNotification('Export failed: ' + err.message, 'error');
  }
}

function showNotification(msg, type='info') {
  let n = document.getElementById('crmNotification');
  if (!n) {
    n = document.createElement('div');
    n.id = 'crmNotification';
    document.body.appendChild(n);
  }
  n.className = `crm-notification ${type}`;
  n.textContent = msg;
  n.style.display = 'block';
  setTimeout(() => { n.style.display = 'none'; }, 5000);
}

/* ── Edit Row ─────────────────────────────────────────────────────── */
let _editIdx = null;
function editRow(idx) {
  _editIdx = idx;
  const row = S.filtered[idx];
  if (!row) return;
  const keep = keepCols();
  const modal = document.getElementById('editModal');
  const form = document.getElementById('editFields');
  form.innerHTML = '';
  keep.forEach(col => {
    const ft = FT[S.mapping[col].type];
    const icon = ft ? ft.icon : '';
    const val = row[col] || '';
    form.innerHTML += `<div class="edit-field">
      <label>${icon} ${col}</label>
      <input type="text" data-col="${col}" value="${val.replace(/"/g,'&quot;')}" />
    </div>`;
  });
  modal.classList.add('open');
}

function saveEdit() {
  if (_editIdx === null) return;
  const row = S.filtered[_editIdx];
  const inputs = document.querySelectorAll('#editFields input');
  inputs.forEach(inp => {
    const col = inp.dataset.col;
    const type = S.mapping[col] ? S.mapping[col].type : 'other';
    let val = inp.value.trim();
    // Validate email on edit
    if (type === 'email' && val && !isValidEmail(val)) {
      inp.style.border = '2px solid var(--rose)';
      showNotification('Invalid email: ' + val, 'error');
      return;
    }
    // Validate phone on edit
    if ((type === 'phone' || type === 'whatsapp') && val) {
      const cls = classifyPhone(val);
      if (!cls.valid) {
        inp.style.border = '2px solid var(--rose)';
        showNotification('Invalid/landline number: ' + val, 'error');
        return;
      }
    }
    row[col] = val;
  });
  S.filtered[_editIdx] = row;
  closeEditModal();
  renderTable();
  showNotification('✏️ Record updated', 'success');
}

function closeEditModal() {
  document.getElementById('editModal').classList.remove('open');
  _editIdx = null;
}

/* ── Delete Row ───────────────────────────────────────────────────── */
function deleteRow(idx) {
  const row = S.filtered[idx];
  if (!row) return;
  const companyCols = colsByType('company');
  const name = companyCols.length ? row[companyCols[0]] || 'this record' : 'this record';
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  // Remove from S.clean (find actual index)
  const cleanIdx = S.clean.indexOf(row);
  if (cleanIdx >= 0) S.clean.splice(cleanIdx, 1);
  S.filtered = [...S.clean];
  renderTable();
  buildKPIs();
  document.getElementById('sbFileMeta').textContent = `${S.clean.length.toLocaleString()} records · ${keepCols().length} fields`;
  showNotification('🗑 Record deleted', 'success');
}

/* ── Contact Detail Panel + Call Logs ─────────────────────────────── */
let _panelIdx = null;
function showContactPanel(idx) {
  _panelIdx = idx;
  const row = S.filtered[idx];
  if (!row) return;
  const keep = keepCols();
  const panel = document.getElementById('contactPanel');
  const companyCols = colsByType('company');
  const contactCols = colsByType('contact');
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];

  const name = contactCols.length ? row[contactCols[0]] || '' : '';
  const company = companyCols.length ? row[companyCols[0]] || '' : '';
  const email = emailCols.length ? row[emailCols[0]] || '' : '';
  const phone = phoneCols.length ? row[phoneCols[0]] || '' : '';

  document.getElementById('panelName').textContent = name || company || 'Contact';
  document.getElementById('panelCompany').textContent = company;

  // Contact details
  const detailsDiv = document.getElementById('panelDetails');
  detailsDiv.innerHTML = keep.map(col => {
    const ft = FT[S.mapping[col].type];
    const val = row[col] || '—';
    return `<div class="pd-row"><span class="pd-label">${ft ? ft.icon : ''} ${col}</span><span class="pd-val">${val}</span></div>`;
  }).join('');

  // Foreign number flag
  if (row._phoneCountry && row._phoneCountry !== 'IN') {
    detailsDiv.innerHTML += `<div class="pd-row"><span class="pd-label">🌍 Country</span><span class="pd-val"><span class="badge b-amber">${row._phoneCountry} — Foreign Number</span></span></div>`;
  }

  // Call logs section
  document.getElementById('callLogsList').innerHTML = '<div class="empty-state" style="padding:16px;font-size:12px">💡 Call logs will appear here after saving to CRM and recording calls.</div>';

  panel.classList.add('open');
}

function closeContactPanel() {
  document.getElementById('contactPanel').classList.remove('open');
  _panelIdx = null;
}

function addCallLogFromPanel() {
  const notes = document.getElementById('callNotes').value.trim();
  const outcome = document.getElementById('callOutcome').value;
  const callType = document.getElementById('callType').value;
  if (!notes) { showNotification('Please enter call notes.', 'error'); return; }

  const now = new Date();
  const entry = document.createElement('div');
  entry.className = 'call-log-entry';
  entry.innerHTML = `
    <div class="cle-header">
      <span class="cle-type badge ${callType==='Incoming'?'b-emerald':callType==='Follow-up'?'b-amber':'b-blue'}">${callType}</span>
      <span class="cle-outcome">${outcome}</span>
      <span class="cle-date">${now.toLocaleDateString()} ${now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>
    </div>
    <div class="cle-notes">${notes}</div>`;
  const list = document.getElementById('callLogsList');
  if (list.querySelector('.empty-state')) list.innerHTML = '';
  list.prepend(entry);
  document.getElementById('callNotes').value = '';
  showNotification('📞 Call log recorded', 'success');
}

/* ── VCF Export ───────────────────────────────────────────────────── */
function downloadVCF() {
  if (!S.clean.length) { alert('No data to export.'); return; }
  const companyCols = colsByType('company');
  const contactCols = colsByType('contact');
  const emailCols = colsByType('email');
  const phoneCols = [...colsByType('phone'), ...colsByType('whatsapp')];
  const addressCols = colsByType('address');
  const cityCols = colsByType('city');
  const webCols = colsByType('website');

  let vcf = '';
  S.clean.forEach(row => {
    const name = contactCols.length ? row[contactCols[0]] || '' : '';
    const company = companyCols.length ? row[companyCols[0]] || '' : '';
    const email = emailCols.length ? row[emailCols[0]] || '' : '';
    const phone = phoneCols.length ? row[phoneCols[0]] || '' : '';
    const phone2 = phoneCols.length && row[phoneCols[0]+'_2'] ? row[phoneCols[0]+'_2'] : '';
    const addr = addressCols.length ? row[addressCols[0]] || '' : '';
    const city = cityCols.length ? row[cityCols[0]] || '' : '';
    const web = webCols.length ? row[webCols[0]] || '' : '';

    const displayName = name || company || 'Unknown';
    const parts = displayName.split(' ');
    const firstName = parts[0] || '';
    const lastName = parts.slice(1).join(' ') || '';

    vcf += 'BEGIN:VCARD\n';
    vcf += 'VERSION:3.0\n';
    vcf += `N:${lastName};${firstName};;;\n`;
    vcf += `FN:${displayName}\n`;
    if (company) vcf += `ORG:${company}\n`;
    if (phone) vcf += `TEL;TYPE=CELL:${phone}\n`;
    if (phone2) vcf += `TEL;TYPE=CELL:${phone2}\n`;
    if (email) vcf += `EMAIL;TYPE=INTERNET:${email}\n`;
    if (addr || city) vcf += `ADR;TYPE=WORK:;;${addr};${city};;;;\n`;
    if (web) vcf += `URL:${web}\n`;
    vcf += 'END:VCARD\n\n';
  });

  const blob = new Blob([vcf], {type: 'text/vcard;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = (S.fileName || 'contacts').replace(/\.[^.]+$/, '') + '.vcf';
  a.click();
  URL.revokeObjectURL(url);
  showNotification(`📱 Downloaded ${S.clean.length} contacts as VCF`, 'success');
}
/* ══════════════════════════════════════════════════════════════════════
   EML EMAIL EXTRACTOR — v2.0 Enhanced
   ══════════════════════════════════════════════════════════════════════ */
const EML_SUPABASE_URL      = window.EML_SUPABASE_URL      || '';
const EML_SUPABASE_ANON_KEY = window.EML_SUPABASE_ANON_KEY || '';
const emlClient = (EML_SUPABASE_URL && EML_SUPABASE_ANON_KEY && window.supabase)
  ? window.supabase.createClient(EML_SUPABASE_URL, EML_SUPABASE_ANON_KEY)
  : null;

const EML = { raw:'', parsed:null, contacts:[], filtered:[], sigData:{}, sigLoading:false };

/* ── EML file handler ─────────────────────────────────────────────── */
function handleEmlFile(file) {
  const reader = new FileReader();
  reader.onload = e => { EML.raw = e.target.result; triggerEmlMorph(file.name); };
  reader.readAsText(file, 'utf-8');
}

/* ── Morph animation ──────────────────────────────────────────────── */
function triggerEmlMorph(fileName) {
  const overlay = document.createElement('div');
  overlay.className = 'eml-morph-overlay';
  overlay.innerHTML = `
    <div class="eml-morph-ring"></div>
    <div class="eml-morph-ring eml-morph-ring-2"></div>
    <div class="eml-morph-icon">✉️</div>
    <div class="eml-morph-status">Parsing email…</div>`;
  document.body.appendChild(overlay);
  const cx = window.innerWidth/2, cy = window.innerHeight/2;
  for (let i=0; i<32; i++) {
    const p = document.createElement('div');
    p.className = 'eml-morph-particle';
    const angle = (i/32)*Math.PI*2, dist = 140+Math.random()*260;
    const size = 3+Math.random()*7;
    const colors = ['#00D4FF','#6C5CE7','#2ECC71','#F59E0B','#EC4899','#3B82F6'];
    p.style.cssText = `left:${cx}px;top:${cy}px;--tx:${Math.cos(angle)*dist}px;--ty:${Math.sin(angle)*dist}px;background:${colors[i%colors.length]};width:${size}px;height:${size}px;animation:particleFly ${0.5+Math.random()*0.6}s ${i*0.02}s cubic-bezier(.2,.8,.2,1) forwards;`;
    overlay.appendChild(p);
  }
  requestAnimationFrame(() => { overlay.style.opacity='1'; overlay.classList.add('active'); setTimeout(()=>overlay.classList.add('expanding'),50); });
  const statusEl = overlay.querySelector('.eml-morph-status');
  setTimeout(()=>{ if(statusEl) statusEl.textContent='Extracting contacts…'; },300);
  setTimeout(()=>{ if(statusEl) statusEl.textContent='Building dashboard…'; },550);

  setTimeout(() => {
    parseEml(fileName); buildEmlDashboard(); showEmlView();
    if(statusEl) { statusEl.textContent=`${EML.contacts.length} contacts found!`; statusEl.classList.add('done'); }
    overlay.style.transition='opacity .5s'; overlay.style.opacity='0';
    setTimeout(()=>overlay.remove(), 550);
  }, 850);
}

/* ── .eml parser (v2 — full MIME multipart) ───────────────────────── */
function parseEml(fileName) {
  const raw = EML.raw;
  const splitIdx = raw.indexOf('\r\n\r\n') !== -1 ? raw.indexOf('\r\n\r\n') : raw.indexOf('\n\n');
  const headerBlock = raw.slice(0, splitIdx);
  let body = raw.slice(splitIdx + (raw.indexOf('\r\n\r\n')!==-1?4:2));
  const headers = {};
  const unfoldedHeaders = headerBlock.replace(/\r?\n([ \t]+)/g,' ');
  unfoldedHeaders.split(/\r?\n/).forEach(line => {
    const idx = line.indexOf(':');
    if (idx>0) {
      const key = line.slice(0,idx).trim().toLowerCase();
      const val = line.slice(idx+1).trim();
      headers[key] = headers[key] ? headers[key] + ', ' + val : val;
    }
  });

  const ct = headers['content-type'] || '';
  const boundaryMatch = ct.match(/boundary="?([^";\s]+)"?/i);
  let plainBody = '', htmlBody = '';

  if (boundaryMatch) {
    const boundary = boundaryMatch[1];
    const parts = body.split('--' + boundary).filter(p => p.trim() && !p.trim().startsWith('--'));
    for (const part of parts) {
      const partSplit = part.indexOf('\r\n\r\n') !== -1 ? part.indexOf('\r\n\r\n') : part.indexOf('\n\n');
      if (partSplit === -1) continue;
      const partHeaders = part.slice(0, partSplit).toLowerCase();
      let partBody = part.slice(partSplit + (part.indexOf('\r\n\r\n')!==-1?4:2));
      const nestedBoundary = partHeaders.match(/boundary="?([^";\s]+)"?/i);
      if (nestedBoundary) {
        const nestedParts = partBody.split('--' + nestedBoundary[1]).filter(np => np.trim() && !np.trim().startsWith('--'));
        for (const np of nestedParts) {
          const npSplit = np.indexOf('\r\n\r\n') !== -1 ? np.indexOf('\r\n\r\n') : np.indexOf('\n\n');
          if (npSplit === -1) continue;
          const npHeaders = np.slice(0, npSplit).toLowerCase();
          let npBody = np.slice(npSplit + (np.indexOf('\r\n\r\n')!==-1?4:2));
          npBody = decodePartBody(npBody, npHeaders);
          if (npHeaders.includes('text/plain') && !plainBody) plainBody = npBody;
          else if (npHeaders.includes('text/html') && !htmlBody) htmlBody = npBody;
        }
        continue;
      }
      partBody = decodePartBody(partBody, partHeaders);
      if (partHeaders.includes('text/plain') && !plainBody) plainBody = partBody;
      else if (partHeaders.includes('text/html') && !htmlBody) htmlBody = partBody;
    }
  } else {
    const cte = (headers['content-transfer-encoding'] || '').toLowerCase();
    if (cte.includes('base64')) {
      try { body = decodeURIComponent(escape(atob(body.replace(/\s/g,'')))); } catch(e) {}
    } else if (cte.includes('quoted-printable')) {
      body = body.replace(/=\r?\n/g,'').replace(/=([0-9A-Fa-f]{2})/g,(_,h)=>String.fromCharCode(parseInt(h,16)));
    }
    if (ct.includes('text/html')) htmlBody = body;
    else plainBody = body;
  }

  let bodyText;
  if (plainBody) {
    bodyText = plainBody.replace(/\r\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
  } else if (htmlBody) {
    bodyText = htmlBody
      .replace(/<style[\s\S]*?<\/style>/gi,'').replace(/<script[\s\S]*?<\/script>/gi,'')
      .replace(/<br\s*\/?>/gi,'\n').replace(/<\/p>/gi,'\n\n').replace(/<\/div>/gi,'\n')
      .replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&')
      .replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"')
      .replace(/ {2,}/g,' ').replace(/\n{3,}/g,'\n\n').trim();
  } else {
    bodyText = body.replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/ {2,}/g,' ').trim();
  }

  function emailToName(e) { return e.split('@')[0].replace(/[._\-+]/g,' ').split(' ').map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(' '); }
  function parseAddresses(str) {
    if (!str) return [];
    const results=[], re=/(?:"?([^"<,]+)"?\s*)?<([^>]+@[^>]+)>|([^\s,<]+@[^\s,>]+)/g; let m;
    while((m=re.exec(str))!==null) {
      const name=(m[1]||'').trim().replace(/^"|"$/g,''), email=(m[2]||m[3]||'').trim().toLowerCase();
      if(email) results.push({name:name||emailToName(email),email});
    }
    return results;
  }

  const attachments=[];
  const ar=/Content-Disposition:\s*attachment[^\n]*\n\s*filename[*]?="?([^"\n]+)"?/gi; let am;
  while((am=ar.exec(raw))!==null) attachments.push(am[1].trim());
  const ar2=/filename="([^"]+)"/gi;
  while((am=ar2.exec(raw))!==null) { if(!attachments.includes(am[1])) attachments.push(am[1].trim()); }
  const ar3=/filename\*=(?:utf-8|UTF-8)''([^\s;]+)/gi;
  while((am=ar3.exec(raw))!==null) {
    try { const decoded = decodeURIComponent(am[1]); if(!attachments.includes(decoded)) attachments.push(decoded); } catch(e){}
  }

  const phones = [];
  const phoneRe = /(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}/g;
  let pm; const bodyForPhones = bodyText || '';
  while((pm=phoneRe.exec(bodyForPhones))!==null) {
    const cleaned = pm[0].replace(/[\s\-().]/g,'');
    if (cleaned.length >= 10 && cleaned.length <= 15 && /\d{10,}/.test(cleaned) && !phones.includes(pm[0].trim())) phones.push(pm[0].trim());
  }

  const urls = [];
  const urlRe = /https?:\/\/[^\s<>"')\]]+/gi; let um;
  while((um=urlRe.exec(bodyForPhones))!==null) {
    const url = um[0].replace(/[.,;:!?)]+$/,'');
    if (!urls.includes(url) && urls.length < 20) urls.push(url);
  }

  const isReply = !!(headers['in-reply-to'] || headers['references'] || /^re:/i.test(headers['subject']||''));
  const isForwarded = /^(?:fwd?|fw):/i.test(headers['subject']||'') || /[-]+\s*Forwarded message/i.test(bodyText||'');

  EML.parsed = {
    fileName, subject: decodeEmlEncoding(headers['subject']||'(No Subject)'),
    date: headers['date']||'', messageId: headers['message-id']||'',
    from: parseAddresses(headers['from']||''), to: parseAddresses(headers['to']||''),
    cc: parseAddresses(headers['cc']||''), bcc: parseAddresses(headers['bcc']||''),
    replyTo: parseAddresses(headers['reply-to']||''),
    body: (bodyText||'').slice(0,5000), bodyHtml: (htmlBody||'').slice(0,10000),
    attachments, phones, urls,
    isReply, isForwarded,
    priority: headers['x-priority'] || headers['importance'] || 'normal',
    mailer: headers['x-mailer'] || headers['user-agent'] || '',
    contentType: ct,
  };

  const seen=new Set();
  function addContacts(list,source) { list.forEach(c=>{ if(!seen.has(c.email)){seen.add(c.email);EML.contacts.push({...c,source,domain:c.email.split('@')[1]||''});}});}
  EML.contacts=[];
  addContacts(EML.parsed.from,'FROM'); addContacts(EML.parsed.to,'TO');
  addContacts(EML.parsed.cc,'CC');     addContacts(EML.parsed.bcc,'BCC');
  if (EML.parsed.replyTo.length) addContacts(EML.parsed.replyTo,'REPLY-TO');
  const bre=/\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b/g; let be;
  while((be=bre.exec(bodyText||''))!==null) {
    const email=be[1].toLowerCase();
    if(!seen.has(email)){seen.add(email);EML.contacts.push({name:emailToName(email),email,source:'BODY',domain:email.split('@')[1]||''});}
  }
  EML.filtered=[...EML.contacts];
  EML.sigData = {};
  if (API_BASE && EML.parsed?.body) {
    EML.sigLoading = true;
    fetch(`${API_BASE}/api/parse-signature`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({ body_text: EML.parsed.body, subject: EML.parsed.subject }),
    })
    .then(r => r.json())
    .then(data => {
      EML.sigLoading = false;
      if (data.ok && data.fields && Object.values(data.fields).some(v => v)) {
        EML.sigData = data.fields;
        renderSigPanel();
        showNotification('🪪 Signature intelligence extracted by AI', 'success');
      }
    })
    .catch(() => { EML.sigLoading = false; });
  }
}

function decodePartBody(body, headers) {
  if (headers.includes('base64')) {
    try { return decodeURIComponent(escape(atob(body.replace(/[\r\n\s]/g,'')))); }
    catch(e) { return body; }
  }
  if (headers.includes('quoted-printable')) {
    return body.replace(/=\r?\n/g,'').replace(/=([0-9A-Fa-f]{2})/g,(_,h)=>String.fromCharCode(parseInt(h,16)));
  }
  return body;
}

function decodeEmlEncoding(str) {
  return str.replace(/=\?([^?]+)\?(Q|B)\?([^?]*)\?=/gi,(_,charset,enc,data)=>{
    try { return enc.toUpperCase()==='B'?decodeURIComponent(escape(atob(data))):data.replace(/_/g,' ').replace(/=([0-9A-Fa-f]{2})/g,(__,h)=>String.fromCharCode(parseInt(h,16))); }
    catch{return data;}
  });
}

function extractSignatureData(bodyText) {
  if (!bodyText) return {};
  // Signatures typically appear after "-- " or the last quoted block
  // Take the last 40 lines of body as signature zone
  const lines = bodyText.split('\n').map(l => l.trim()).filter(Boolean);
  const sigStart = Math.max(0, lines.length - 40);
  const sigLines = lines.slice(sigStart);

  const result = { company: null, designation: null, phone: null, website: null, address: null };

  // Phone — already extracted globally, pick first
  const phoneRe = /(?:\+?91[\s\-]?)?[6-9]\d{9}|\+\d{1,3}[\s\-]?\d{6,14}/;
  for (const l of sigLines) {
    if (!result.phone && phoneRe.test(l.replace(/[\s\(\)\-\.]/g,''))) {
      result.phone = l.replace(/^(ph|phone|mob|mobile|tel|cell)[:\s]*/i,'').trim();
    }
  }

  // Website
  const webRe = /(?:www\.|https?:\/\/)[^\s<>,"']+/i;
  for (const l of sigLines) {
    const m = l.match(webRe);
    if (m && !result.website) result.website = m[0].trim();
  }

  // Designation — lines with common title keywords
  const desgRe = /\b(ceo|cto|cfo|coo|founder|co-founder|director|manager|head|vp|vice president|president|engineer|developer|consultant|analyst|executive|officer|lead|partner|proprietor|md|gm|agm|dgm)\b/i;
  for (const l of sigLines) {
    if (!result.designation && desgRe.test(l) && l.length < 80) {
      result.designation = l.replace(/^[|\-•·]\s*/,'').trim();
    }
  }

  // Company — line after name/designation that looks like an org
  // Heuristic: all-caps or contains Ltd/Pvt/Inc/Corp/LLP/Industries/Solutions/Technologies
  const compRe = /\b(ltd|pvt|inc|corp|llp|llc|industries|solutions|technologies|systems|services|enterprises|group|associates|consulting|trading|mfg|manufacturing|exports|imports)\b/i;
  for (const l of sigLines) {
    if (!result.company && compRe.test(l) && l.length < 100) {
      result.company = l.replace(/^[|\-•·]\s*/,'').trim();
    }
  }
  // Fallback: line that's mostly uppercase and 3-60 chars
  if (!result.company) {
    for (const l of sigLines) {
      if (l.length >= 3 && l.length <= 60 && l === l.toUpperCase() && /[A-Z]{3,}/.test(l)) {
        result.company = l; break;
      }
    }
  }

  // Address — line with pincode or common address keywords
  const addrRe = /\d{6}|\b(road|rd|street|st|nagar|colony|sector|plot|phase|industrial|estate|ahmedabad|surat|mumbai|gujarat|maharashtra)\b/i;
  for (const l of sigLines) {
    if (!result.address && addrRe.test(l) && l.length > 10 && l.length < 150) {
      result.address = l.replace(/^[|\-•·]\s*/,'').trim();
    }
  }

  return result;
}

function buildEmlDashboard() {
  const p=EML.parsed; if(!p) return;
  const uniqueDomains = [...new Set(EML.contacts.map(c=>c.domain).filter(Boolean))];

  animateCount('emlKpiContacts',EML.contacts.length);
  animateCount('emlKpiEmails',EML.contacts.length);
  animateCount('emlKpiDomains',uniqueDomains.length);
  animateCount('emlKpiAttach',p.attachments.length);

  const phonesKpi = document.getElementById('emlKpiPhones');
  if (phonesKpi) animateCount('emlKpiPhones', p.phones.length);
  const urlsKpi = document.getElementById('emlKpiUrls');
  if (urlsKpi) animateCount('emlKpiUrls', p.urls.length);

  document.getElementById('emlFileName').textContent=p.subject || p.fileName;
  const dateStr = p.date ? new Date(p.date).toLocaleString('en-IN', {dateStyle:'medium', timeStyle:'short'}) : 'Unknown date';
  const badges = [];
  if (p.isReply) badges.push('<span class="eml-type-badge eml-badge-reply">↩ Reply</span>');
  if (p.isForwarded) badges.push('<span class="eml-type-badge eml-badge-forward">→ Forward</span>');
  if (p.attachments.length) badges.push(`<span class="eml-type-badge eml-badge-attach">📎 ${p.attachments.length}</span>`);
  if (p.phones.length) badges.push(`<span class="eml-type-badge eml-badge-phone">📞 ${p.phones.length}</span>`);
  document.getElementById('emlFileSub').innerHTML=`${EML.contacts.length} contact${EML.contacts.length!==1?'s':''} · ${dateStr} ${badges.join(' ')}`;

  function addrTags(list){return list.map(c=>`<span class="eml-meta-email-tag" title="Click to copy: ${escHtml(c.email)}" onclick="copyToClip('${escHtml(c.email)}')">${escHtml(c.name||c.email)}</span>`).join('');}

  document.getElementById('emlMeta').innerHTML=`
    ${p.from.length?`<div class="eml-meta-row"><span class="eml-meta-label">FROM</span><div class="eml-meta-val">${addrTags(p.from)}</div></div>`:''}
    ${p.to.length?`<div class="eml-meta-row"><span class="eml-meta-label">TO</span><div class="eml-meta-val">${addrTags(p.to)}</div></div>`:''}
    ${p.cc.length?`<div class="eml-meta-row"><span class="eml-meta-label">CC</span><div class="eml-meta-val">${addrTags(p.cc)}</div></div>`:''}
    ${p.replyTo&&p.replyTo.length?`<div class="eml-meta-row"><span class="eml-meta-label">REPLY-TO</span><div class="eml-meta-val">${addrTags(p.replyTo)}</div></div>`:''}
    ${p.date?`<div class="eml-meta-row"><span class="eml-meta-label">DATE</span><div class="eml-meta-val">${escHtml(dateStr)}</div></div>`:''}
    ${p.mailer?`<div class="eml-meta-row"><span class="eml-meta-label">MAILER</span><div class="eml-meta-val eml-mailer-tag">${escHtml(p.mailer)}</div></div>`:''}`;

  document.getElementById('emlSubject').innerHTML=`<span class="eml-subject-text">${escHtml(p.subject)}</span>`;

  const bodyEl = document.getElementById('emlBodyText');
  const wordCount = (p.body||'').split(/\s+/).filter(Boolean).length;
  bodyEl.textContent = p.body||'(No readable body content)';
  const bodyMeta = document.getElementById('emlBodyMeta');
  if (bodyMeta) bodyMeta.textContent = `${wordCount} words · ${(p.body||'').length} chars`;

  const attEl=document.getElementById('emlAttachments');
  if (p.attachments.length) {
    const icons={pdf:'📄',doc:'📝',docx:'📝',xls:'📗',xlsx:'📗',png:'🖼️',jpg:'🖼️',jpeg:'🖼️',gif:'🖼️',zip:'📦',rar:'📦',mp3:'🎵',mp4:'🎬',csv:'📊',pptx:'📊',ppt:'📊',txt:'📝'};
    attEl.innerHTML = `<div class="eml-attach-label">📎 ${p.attachments.length} Attachment${p.attachments.length>1?'s':''}</div>` +
      p.attachments.map((a,i) => {
        const ext = a.split('.').pop().toLowerCase();
        return `<div class="eml-attach-chip" style="animation-delay:${i*0.08}s"><span class="eml-attach-icon">${icons[ext]||'📄'}</span><span class="eml-attach-name">${escHtml(a)}</span><span class="eml-attach-ext">.${ext}</span></div>`;
      }).join('');
  } else attEl.innerHTML='';

  const phonesEl = document.getElementById('emlPhones');
  if (phonesEl) {
    if (p.phones.length) {
      phonesEl.innerHTML = `<div class="eml-section-label">📞 Phone Numbers Found</div><div class="eml-phone-grid">${
        p.phones.map(ph => `<span class="eml-phone-chip" onclick="copyToClip('${escHtml(ph)}')" title="Click to copy">📞 ${escHtml(ph)}</span>`).join('')
      }</div>`;
      phonesEl.style.display = '';
    } else phonesEl.style.display = 'none';
  }

  const urlsEl = document.getElementById('emlUrls');
  if (urlsEl) {
    if (p.urls.length) {
      urlsEl.innerHTML = `<div class="eml-section-label">🔗 Links Found (${p.urls.length})</div><div class="eml-url-grid">${
        p.urls.slice(0,10).map(u => `<a class="eml-url-chip" href="${escHtml(u)}" target="_blank" rel="noopener"><span class="eml-url-icon">🔗</span>${escHtml(u.length>55?u.slice(0,52)+'…':u)}</a>`).join('')
      }</div>`;
      urlsEl.style.display = '';
    } else urlsEl.style.display = 'none';
  }

  // Signature intelligence panel
  const sigEl = document.getElementById('emlSigData');
  if (sigEl) {
    const sd = EML.sigData;
    const hasAny = sd.company || sd.designation || sd.phone || sd.website || sd.address;
    if (hasAny) {
      sigEl.innerHTML = `
        <div class="eml-section-label">🪪 Signature Intelligence</div>
        <div class="eml-sig-grid">
          ${sd.company     ? `<div class="eml-sig-row"><span class="eml-sig-label">🏢 Company</span><span class="eml-sig-val">${escHtml(sd.company)}</span></div>` : ''}
          ${sd.designation ? `<div class="eml-sig-row"><span class="eml-sig-label">💼 Designation</span><span class="eml-sig-val">${escHtml(sd.designation)}</span></div>` : ''}
          ${sd.phone       ? `<div class="eml-sig-row"><span class="eml-sig-label">📞 Phone</span><span class="eml-sig-val">${escHtml(sd.phone)}</span></div>` : ''}
          ${sd.website     ? `<div class="eml-sig-row"><span class="eml-sig-label">🌐 Website</span><span class="eml-sig-val"><a href="${escHtml(sd.website)}" target="_blank">${escHtml(sd.website)}</a></span></div>` : ''}
          ${sd.address     ? `<div class="eml-sig-row"><span class="eml-sig-label">📍 Address</span><span class="eml-sig-val">${escHtml(sd.address)}</span></div>` : ''}
        </div>`;
      sigEl.style.display = '';
    } else {
      sigEl.style.display = 'none';
    }
  }

  renderEmlContacts();

  const domainCounts={};
  EML.contacts.forEach(c=>{if(c.domain) domainCounts[c.domain]=(domainCounts[c.domain]||0)+1;});
  const sorted=Object.entries(domainCounts).sort((a,b)=>b[1]-a[1]);

  const dGrid = document.getElementById('emlDomainGrid');
  if (sorted.length) {
    const totalContacts = EML.contacts.length;
    const colors = ['#00D4FF','#6C5CE7','#2ECC71','#F59E0B','#EC4899','#3B82F6','#F97316','#14B8A6'];
    dGrid.innerHTML = `<div class="eml-domain-chart-wrap">${sorted.map(([d,n],i)=>{
      const pct = Math.round(n/totalContacts*100);
      const color = colors[i % colors.length];
      return `<div class="eml-domain-row" style="animation-delay:${i*0.06}s">
        <div class="eml-domain-dot" style="background:${color}"></div>
        <span class="eml-domain-name">@${escHtml(d)}</span>
        <div class="eml-domain-bar-bg"><div class="eml-domain-bar-fg" style="width:${pct}%;background:${color}"></div></div>
        <span class="eml-domain-count">${n}</span>
        <span class="eml-domain-pct">${pct}%</span>
      </div>`;
    }).join('')}</div>`;
  } else {
    dGrid.innerHTML = '<div class="eml-empty"><div class="eml-empty-icon">🌐</div>No domains found</div>';
  }
}

function renderEmlContacts() {
  const list=document.getElementById('emlContactList');
  if(!EML.filtered.length){list.innerHTML='<div class="eml-empty"><div class="eml-empty-icon">👤</div>No contacts found</div>';return;}
  const sb={FROM:'eml-badge-from',TO:'eml-badge-to',CC:'eml-badge-cc',BCC:'eml-badge-cc','REPLY-TO':'eml-badge-cc',BODY:'eml-badge-body'};
  const avatarColors = ['#6C5CE7','#00D4FF','#2ECC71','#F59E0B','#EC4899','#3B82F6','#F97316','#14B8A6','#8B5CF6','#EF4444'];
  list.innerHTML=EML.filtered.map((c,i)=>{
    const initials = escHtml(c.name.split(' ').map(w=>w[0]).join('').toUpperCase().slice(0,2)||'?');
    const color = avatarColors[i % avatarColors.length];
    return `<div class="eml-contact-card" style="animation-delay:${i*0.04}s" onclick="copyToClip('${escHtml(c.email)}')" title="Click to copy email">
    <div class="eml-contact-avatar" style="background:linear-gradient(135deg, ${color}, ${color}88)">${initials}</div>
    <div class="eml-contact-info">
      <div class="eml-contact-name">${escHtml(c.name)}</div>
      <div class="eml-contact-email">${escHtml(c.email)}</div>
      <div class="eml-contact-domain">@${escHtml(c.domain)}</div>
    </div>
    <span class="eml-contact-badge ${sb[c.source]||'eml-badge-body'}">${c.source}</span>
    <button class="eml-copy-btn" onclick="event.stopPropagation();copyToClip('${escHtml(c.email)}')" title="Copy email">📋</button>
  </div>`;
  }).join('');
}

function renderSigPanel() {
  const el = document.getElementById('emlSigData');
  if (!el) return;
  const sd = EML.sigData || {};
  const hasAny = Object.values(sd).some(v => v);

  if (EML.sigLoading) {
    el.style.display = '';
    el.innerHTML = `<div class="eml-section-label">🪪 Signature Intelligence</div>
      <div class="eml-sig-loading"><span class="spinner-inline"></span> AI extracting signature data…</div>`;
    return;
  }
  if (!hasAny) { el.style.display = 'none'; return; }

  const row = (icon, label, val) => val
    ? `<div class="eml-sig-row">
        <span class="eml-sig-label">${icon} ${label}</span>
        <span class="eml-sig-val">${escHtml(val)}</span>
       </div>` : '';

  el.style.display = '';
  el.innerHTML = `
    <div class="eml-section-label">🪪 Signature Intelligence <span class="eml-sig-badge">AI</span></div>
    <div class="eml-sig-grid">
      ${row('👤','Name',        sd.name)}
      ${row('🏢','Company',     sd.company)}
      ${row('💼','Designation', sd.designation)}
      ${row('📞','Phone',       sd.phone_primary)}
      ${row('📞','Phone 2',     sd.phone_secondary)}
      ${row('📧','Email',       sd.email)}
      ${row('🌐','Website',     sd.website)}
      ${row('📍','Address',     sd.address)}
      ${row('🏙','City',        sd.city)}
      ${row('🔢','Pincode',     sd.pincode)}
    </div>`;
}

function emlFilterContacts() {
  const q=(document.getElementById('emlSearch')?.value||'').toLowerCase();
  EML.filtered=q?EML.contacts.filter(c=>c.name.toLowerCase().includes(q)||c.email.toLowerCase().includes(q)||c.domain.toLowerCase().includes(q)):[...EML.contacts];
  renderEmlContacts();
}

function animateCount(id,target) {
  const el=document.getElementById(id); if(!el) return;
  const dur=800,start=performance.now(); el.classList.remove('counted');
  function frame(now){const p=Math.min((now-start)/dur,1),ease=1-Math.pow(1-p,3);el.textContent=Math.round(ease*target);if(p<1)requestAnimationFrame(frame);else{el.textContent=target;el.classList.add('counted');}}
  requestAnimationFrame(frame);
}

/* ── Clipboard helper ─────────────────────────────────────────────── */
function copyToClip(text) {
  navigator.clipboard.writeText(text).then(()=>{
    showNotification(`📋 Copied: ${text}`, 'success');
  }).catch(()=>{
    const ta=document.createElement('textarea'); ta.value=text;
    document.body.appendChild(ta); ta.select(); document.execCommand('copy');
    document.body.removeChild(ta);
    showNotification(`📋 Copied: ${text}`, 'success');
  });
}

/* ── Show / exit EML view ─────────────────────────────────────────── */
function showEmlView() {
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-eml').classList.add('active');
  document.querySelectorAll('.nav-item[data-view]').forEach(n=>n.classList.remove('active'));
  document.getElementById('topTitle').textContent='📧 Email Intelligence';
  document.getElementById('topSub').textContent=`${EML.parsed?.fileName||'Email'} · ${EML.contacts.length} contacts extracted`;
  document.body.classList.add('eml-mode');
  const ta=document.getElementById('topActions'); if(ta) ta.style.display='flex';
}

function exitEmlDashboard() {
  document.body.classList.remove('eml-mode');
  const v=document.getElementById('view-eml');
  v.style.transition='opacity .35s, transform .35s'; v.style.opacity='0'; v.style.transform='translateY(12px)';
  setTimeout(()=>{v.style.opacity='';v.style.transform='';v.style.transition='';v.classList.remove('active');EML.raw='';EML.parsed=null;EML.contacts=[];EML.filtered=[];showView('upload');},380);
}

/* ── Export CSV ───────────────────────────────────────────────────── */
function emlExportCSV() {
  if (!EML.contacts.length) { showNotification('No contacts to export.','error'); return; }
  const sd = EML.sigData || {};
  const rows = [['Name','Email','Company','Designation','Phone','Phone 2','Website','Address','City','Pincode','Domain','Source']];
  EML.contacts.forEach(c => {
    const csd = sd[c.email] || {};
    rows.push([
      c.name, c.email,
      csd.company||'', csd.designation||'',
      csd.phone_primary||'', csd.phone_secondary||'',
      csd.website||'', csd.address||'', csd.city||'', csd.pincode||'',
      c.domain, c.source,
    ]);
  });
  const csv = rows.map(r => r.map(v => `"${String(v||'').replace(/"/g,'""')}"`).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8;'}));
  a.download = (EML.parsed?.fileName||'email').replace('.eml','') + '_contacts.csv';
  a.click();
  showNotification(`📧 Exported ${EML.contacts.length} contacts`, 'success');
}

/* ── Export Excel ───────────────────────────────────────────────────── */
function emlExportExcel() {
  if (!EML.contacts.length) { showNotification('No contacts to export.','error'); return; }
  const sd = EML.sigData || {};
  const headers = ['Name','Email','Company','Designation','Phone','Phone 2','Website','Address','City','Pincode','Domain','Source'];
  const rows = EML.contacts.map(c => {
    const csd = sd[c.email] || {};
    return [
      c.name, c.email,
      csd.company||'', csd.designation||'',
      csd.phone_primary||'', csd.phone_secondary||'',
      csd.website||'', csd.address||'', csd.city||'', csd.pincode||'',
      c.domain, c.source,
    ];
  });
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  ws['!cols'] = [28,36,36,28,20,20,36,50,20,12,28,12].map(w => ({wch:w}));
  XLSX.utils.book_append_sheet(wb, ws, 'EML Contacts');
  XLSX.writeFile(wb, (EML.parsed?.fileName||'email').replace('.eml','') + '_contacts.xlsx');
  showNotification(`⬇ Exported ${EML.contacts.length} contacts to Excel`, 'success');
}

/* ── Save to Supabase EML DB ──────────────────────────────────────── */
async function emlSaveToSupabase() {
  if(!emlClient){showNotification('EML Supabase not configured. Add EML_SUPABASE_URL and EML_SUPABASE_ANON_KEY to config.js','error');return;}
  if(!EML.parsed){showNotification('No email loaded','error');return;}
  const p=EML.parsed;
  try {
    showNotification('Saving to EML database…','info');
    const {data:emailRow,error:emailErr} = await emlClient.from('eml_emails').insert({
      file_name:     p.fileName,
      subject:       p.subject,
      sender_name:   p.from[0]?.name||null,
      sender_email:  p.from[0]?.email||null,
      to_emails:     p.to.map(c=>c.email).join(', ')||null,
      cc_emails:     p.cc.map(c=>c.email).join(', ')||null,
      sent_date:     p.date?new Date(p.date).toISOString():null,
      body_preview:  p.body.slice(0,500),
      attachments:   p.attachments.join(', ')||null,
      total_contacts:EML.contacts.length,
    }).select().single();
    if(emailErr) throw emailErr;
    // 2. Insert all extracted contacts
    const sd = EML.sigData || {};
    const contactRows = EML.contacts.map(c=>{
      const csd = sd[c.email] || {};
      return {
        email_id:      emailRow.id,
        name:          c.name,
        email:         c.email,
        domain:        c.domain,
        source:        c.source,
        company:       csd.company || null,
        designation:   csd.designation || null,
        phone_primary: csd.phone_primary || null,
        phone_secondary: csd.phone_secondary || null,
        website:       csd.website || null,
        address:       csd.address || null,
        city:          csd.city || null,
        pincode:       csd.pincode || null,
      };
    });
    const {error:contactErr} = await emlClient.from('eml_contacts').insert(contactRows);
    if(contactErr) throw contactErr;
    showNotification(`✅ Saved email + ${EML.contacts.length} contacts to EML database`,'success');
  } catch(err) {
    showNotification('Save failed: '+err.message,'error');
  }
}

/* ── Push contacts into main CRM table ───────────────────────────── */
function emlSendToCRM() {
  if (!EML.contacts.length) { alert('No contacts to push.'); return; }
  const sd = EML.sigData || {};
  const rows = EML.contacts.map(c => {
    const csd = sd[c.email] || {};
    return {
      'Name':        c.name                  || '',
      'Email':       c.email                 || '',
      'Company':     csd.company              || '',
      'Designation': csd.designation          || '',
      'Phone':       csd.phone_primary        || '',
      'Phone 2':     csd.phone_secondary      || '',
      'Website':     csd.website              || '',
      'Address':     csd.address              || '',
      'City':        csd.city                 || '',
      'Pincode':     csd.pincode              || '',
      'Domain':      c.domain               || '',
      'Source':      c.source               || '',
    };
  });
  S.rawData   = rows;
  S.headers   = ['Name','Email','Company','Designation','Phone','Phone 2','Website','Address','City','Pincode','Domain','Source'];
  S.fileName  = EML.parsed?.fileName || 'Email Import';
  S.sheetName = 'EML Contacts';
  S.mapping   = {
    'Name':        { type:'contact',  keep:true  },
    'Email':       { type:'email',    keep:true  },
    'Company':     { type:'company',  keep:true  },
    'Designation': { type:'keyword',  keep:true  },
    'Phone':       { type:'phone',    keep:true  },
    'Phone 2':     { type:'phone',    keep:true  },
    'Website':     { type:'website',  keep:true  },
    'Address':     { type:'address',  keep:true  },
    'City':        { type:'city',     keep:true  },
    'Pincode':     { type:'pincode',  keep:true  },
    'Domain':      { type:'website',  keep:false },
    'Source':      { type:'other',    keep:false },
  };
  S.clean    = rows.filter(r => r.Email);
  S.filtered = [...S.clean];
  S.page     = 1;
  document.body.classList.remove('eml-mode');
  showNotification(`✅ ${S.clean.length} contacts pushed to CRM with AI-extracted signature data`, 'success');
  document.getElementById('topActions').style.display = 'flex';
  showView('table');
}

function escHtml(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

/* ══════════════════════════════════════════════════════════════
   BULK EML PROCESSOR — handles 100–200 .eml files at once
   ══════════════════════════════════════════════════════════════ */

const BULK = {
  files: [],
  rows: [],       // master flat rows — one row per contact per email
  processed: 0,
  errors: 0,
};

async function handleBulkEml(fileList) {
  BULK.files = Array.from(fileList);
  BULK.rows = [];
  BULK.processed = 0;
  BULK.errors = 0;

  showBulkProgress(BULK.files.length);

  // Phase 1: Local Parse
  const parsedFiles = [];
  for (let i = 0; i < BULK.files.length; i++) {
    const file = BULK.files[i];
    try {
      const text = await readFileAsText(file);
      const parsed = parseSingleEml(text, file.name);
      parsedFiles.push({ file, parsed });
    } catch (e) {
      console.error(e);
      BULK.errors++;
    }
    updateBulkProgress(i + 1, BULK.files.length, `Reading & parsing file ${i + 1} of ${BULK.files.length} locally…`);
  }

  // Phase 2: AI Parsing (Parallel with Concurrency Limit)
  let aiSent = 0;
  let aiReceived = 0;
  const total = parsedFiles.length;
  const CONCURRENCY = 5;

  const updateAiProgress = () => {
    updateBulkProgress(aiReceived, total, `AI Extraction<br>Sent to AI: <span style="color:#6C5CE7;font-weight:600">${aiSent}</span> / ${total} &nbsp;|&nbsp; Received: <span style="color:#2ECC71;font-weight:600">${aiReceived}</span> / ${total}`);
  };

  updateAiProgress();

  let currentIndex = 0;

  async function processNext() {
    if (currentIndex >= total) return;
    const idx = currentIndex++;
    const item = parsedFiles[idx];
    
    aiSent++;
    updateAiProgress();

    try {
      const apiKey = localStorage.getItem('CRM_API_KEY') || window.CRM_API_KEY || '';
      const aiResp = await fetch('/api/parse-signature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
        body: JSON.stringify({ body_text: item.parsed.bodyText, subject: item.parsed.subject })
      });
      const resJson = await aiResp.json();
      if (resJson.ok && Array.isArray(resJson.fields)) {
        item.aiData = resJson.fields;
      } else if (resJson.ok && resJson.fields && typeof resJson.fields === 'object') {
        item.aiData = [resJson.fields];
      } else {
        item.aiData = [];
      }
    } catch (err) {
      console.error('AI parse failed for', item.file.name, err);
      item.aiData = [];
      BULK.errors++;
    }

    aiReceived++;
    updateAiProgress();
    
    await new Promise(r => setTimeout(r, 50)); // 50ms delay
    await processNext();
  }

  const workers = [];
  for (let i = 0; i < Math.min(CONCURRENCY, total); i++) {
    workers.push(processNext());
  }
  await Promise.all(workers);

  // Phase 3: Build Rows
  updateBulkProgress(total, total, 'Building tabular data…');
  parsedFiles.forEach(item => {
    const { file, parsed, aiData } = item;
    
    parsed.contacts.forEach(c => {
      const matchingAi = (aiData || []).find(a => a.email && a.email.toLowerCase() === c.email.toLowerCase()) || 
                         ((aiData || []).length === 1 ? aiData[0] : {});

      BULK.rows.push({
        'File Name':    file.name,
        'Subject':      parsed.subject,
        'Date':         parsed.date,
        'From Name':    parsed.from[0]?.name  || '',
        'From Email':   parsed.from[0]?.email || '',
        'Contact Name': matchingAi.name || c.name,
        'Email':        c.email,
        'Domain':       c.domain,
        'Source':       c.source,
        'Company':        matchingAi.company || c.company || '',
        'Designation':    matchingAi.designation || c.designation || '',
        'Phone Primary':  matchingAi.phone_primary || c.phone_primary || parsed.phones[0] || '',
        'Phone Secondary':matchingAi.phone_secondary || c.phone_secondary|| '',
        'Website':        matchingAi.website || c.website || '',
        'City':           matchingAi.city || c.city || '',
        'Attachments':  parsed.attachments.join(', '),
        'Is Reply':     parsed.isReply  ? 'Yes' : 'No',
        'Is Forward':   parsed.isForwarded ? 'Yes' : 'No',
        'Links':        parsed.urls.slice(0, 3).join(', '),
      });
    });
    BULK.processed++;
  });

  showBulkDashboard();
}

/* ── Reusable single-EML parser (no side effects on EML global) ── */
function parseSingleEml(raw, fileName) {
  const splitIdx = raw.indexOf('\r\n\r\n') !== -1 ? raw.indexOf('\r\n\r\n') : raw.indexOf('\n\n');
  const headerBlock = raw.slice(0, splitIdx);
  let body = raw.slice(splitIdx + (raw.indexOf('\r\n\r\n') !== -1 ? 4 : 2));
  const headers = {};
  const unfolded = headerBlock.replace(/\r?\n([ \t]+)/g, ' ');
  unfolded.split(/\r?\n/).forEach(line => {
    const idx = line.indexOf(':');
    if (idx > 0) {
      const key = line.slice(0, idx).trim().toLowerCase();
      const val = line.slice(idx + 1).trim();
      headers[key] = headers[key] ? headers[key] + ', ' + val : val;
    }
  });

  const ct = headers['content-type'] || '';
  const bMatch = ct.match(/boundary="?([^";\s]+)"?/i);
  let plainBody = '', htmlBody = '';

  if (bMatch) {
    const boundary = bMatch[1];
    const parts = body.split('--' + boundary).filter(p => p.trim() && !p.trim().startsWith('--'));
    for (const part of parts) {
      const ps = part.indexOf('\r\n\r\n') !== -1 ? part.indexOf('\r\n\r\n') : part.indexOf('\n\n');
      if (ps === -1) continue;
      const ph = part.slice(0, ps).toLowerCase();
      let pb = part.slice(ps + (part.indexOf('\r\n\r\n') !== -1 ? 4 : 2));
      pb = decodePartBody(pb, ph);
      if (ph.includes('text/plain') && !plainBody) plainBody = pb;
      else if (ph.includes('text/html') && !htmlBody) htmlBody = pb;
    }
  } else {
    const cte = (headers['content-transfer-encoding'] || '').toLowerCase();
    if (cte.includes('base64')) { try { body = decodeURIComponent(escape(atob(body.replace(/\s/g, '')))); } catch(e) {} }
    else if (cte.includes('quoted-printable')) { body = body.replace(/=\r?\n/g, '').replace(/=([0-9A-Fa-f]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16))); }
    if (ct.includes('text/html')) htmlBody = body; else plainBody = body;
  }

  let bodyText = '';
  if (plainBody) {
    bodyText = plainBody.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  } else if (htmlBody) {
    bodyText = htmlBody
      .replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<br\s*\/?>/gi, '\n').replace(/<\/p>/gi, '\n\n').replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/ {2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
  }

  function emailToName(e) { return e.split('@')[0].replace(/[._\-+]/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '); }
  function parseAddresses(str) {
    if (!str) return [];
    const results = [], re = /(?:"?([^"<,]+)"?\s*)?<([^>]+@[^>]+)>|([^\s,<]+@[^\s,>]+)/g; let m;
    while ((m = re.exec(str)) !== null) {
      const name = (m[1] || '').trim().replace(/^"|"$/g, '');
      const email = (m[2] || m[3] || '').trim().toLowerCase();
      if (email) results.push({ name: name || emailToName(email), email });
    }
    return results;
  }

  const attachments = [];
  const ar = /Content-Disposition:\s*attachment[^\n]*\n\s*filename[*]?="?([^"\n]+)"?/gi; let am;
  while ((am = ar.exec(raw)) !== null) attachments.push(am[1].trim());
  const ar2 = /filename="([^"]+)"/gi;
  while ((am = ar2.exec(raw)) !== null) { if (!attachments.includes(am[1])) attachments.push(am[1].trim()); }

  const phones = [];
  const phoneRe = /(?:\+?\d{1,3}[\-.\s]?)?\(?\d{2,4}\)?[\-.\s]?\d{3,4}[\-.\s]?\d{3,4}/g; let pm;
  while ((pm = phoneRe.exec(bodyText)) !== null) {
    const cleaned = pm[0].replace(/[\s\-().]/g, '');
    if (cleaned.length >= 10 && cleaned.length <= 15 && /\d{10,}/.test(cleaned) && !phones.includes(pm[0].trim())) phones.push(pm[0].trim());
  }

  const urls = [];
  const urlRe = /https?:\/\/[^\s<>"')]+/gi; let um;
  while ((um = urlRe.exec(bodyText)) !== null) {
    const url = um[0].replace(/[.,;:!?)]+$/, '');
    if (!urls.includes(url) && urls.length < 10) urls.push(url);
  }

  const from = parseAddresses(headers['from'] || '');
  const to   = parseAddresses(headers['to']   || '');
  const cc   = parseAddresses(headers['cc']   || '');
  const bcc  = parseAddresses(headers['bcc']  || '');
  const replyTo = parseAddresses(headers['reply-to'] || '');

  const seen = new Set();
  const contacts = [];
  function addC(list, source) { list.forEach(c => { if (!seen.has(c.email)) { seen.add(c.email); contacts.push({ ...c, source, domain: c.email.split('@')[1] || '' }); } }); }
  addC(from, 'FROM'); addC(to, 'TO'); addC(cc, 'CC'); addC(bcc, 'BCC'); addC(replyTo, 'REPLY-TO');
  const bre = /\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b/g; let be;
  while ((be = bre.exec(bodyText)) !== null) {
    const email = be[1].toLowerCase();
    if (!seen.has(email)) { seen.add(email); contacts.push({ name: emailToName(email), email, source: 'BODY', domain: email.split('@')[1] || '' }); }
  }

  return {
    fileName, subject: decodeEmlEncoding(headers['subject'] || '(No Subject)'),
    date: headers['date'] || '',
    from, to, cc, bcc, replyTo,
    attachments, phones, urls,
    contacts,
    bodyText,
    isReply: !!(headers['in-reply-to'] || headers['references'] || /^re:/i.test(headers['subject'] || '')),
    isForwarded: /^(?:fwd?|fw):/i.test(headers['subject'] || '') || /[-]+\s*Forwarded message/i.test(bodyText),
  };
}

function readFileAsText(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = e => res(e.target.result);
    r.onerror = () => rej(new Error('Read failed'));
    r.readAsText(file, 'utf-8');
  });
}

/* ── Progress overlay ── */
function showBulkProgress(total) {
  let overlay = document.getElementById('bulkProgressOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'bulkProgressOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `
      <div style="background:#fff;border-radius:16px;padding:36px 44px;min-width:340px;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,0.18)">
        <div style="font-size:36px;margin-bottom:12px">📧</div>
        <div style="font-size:17px;font-weight:600;color:#111;margin-bottom:6px">Processing EML files…</div>
        <div style="font-size:13px;color:#888;margin-bottom:18px" id="bulkProgressText">0 / ${total}</div>
        <div style="background:#f0f0f0;border-radius:99px;height:8px;overflow:hidden;margin-bottom:8px">
          <div id="bulkProgressBar" style="height:8px;background:linear-gradient(90deg,#378ADD,#6C5CE7);border-radius:99px;width:0%;transition:width 0.2s"></div>
        </div>
        <div style="font-size:12px;color:#aaa" id="bulkProgressSub">Reading files…</div>
      </div>`;
    document.body.appendChild(overlay);
  } else {
    overlay.style.display = 'flex';
    document.getElementById('bulkProgressBar').style.width = '0%';
    document.getElementById('bulkProgressText').textContent = `0 / ${total}`;
  }
}

function updateBulkProgress(done, total, customSub = null) {
  const pct = Math.round((done / total) * 100);
  const bar = document.getElementById('bulkProgressBar');
  const txt = document.getElementById('bulkProgressText');
  const sub = document.getElementById('bulkProgressSub');
  if (bar) bar.style.width = pct + '%';
  if (txt) txt.textContent = `${done} / ${total}`;
  if (sub) {
    if (customSub) {
      sub.innerHTML = customSub;
    } else {
      sub.textContent = done < total ? `Processing ${BULK.files[done]?.name || ''}…` : 'Building table…';
    }
  }
}

function hideBulkProgress() {
  const o = document.getElementById('bulkProgressOverlay');
  if (o) o.style.display = 'none';
}

/* ── Bulk dashboard ── */
function showBulkDashboard() {
  hideBulkProgress();

  // Unique contacts by email
  const uniqueEmails = [...new Map(BULK.rows.map(r => [r['Email'], r])).values()];
  const uniqueDomains = [...new Set(BULK.rows.map(r => r['Domain']).filter(Boolean))];
  const totalPhones = BULK.rows.filter(r => r['Phone']).length;

  // Update KPIs reusing existing elements
  animateCount('emlKpiContacts', uniqueEmails.length);
  animateCount('emlKpiEmails',   BULK.rows.length);
  animateCount('emlKpiDomains',  uniqueDomains.length);
  animateCount('emlKpiAttach',   BULK.processed);
  const phonesKpi = document.getElementById('emlKpiPhones');
  if (phonesKpi) animateCount('emlKpiPhones', totalPhones);
  const urlsKpi = document.getElementById('emlKpiUrls');
  if (urlsKpi) animateCount('emlKpiUrls', BULK.errors);

  // Update labels to match bulk context
  const labels = document.querySelectorAll('.eml-kpi-label');
  if (labels[0]) labels[0].textContent = 'Unique Contacts';
  if (labels[1]) labels[1].textContent = 'Total Rows';
  if (labels[2]) labels[2].textContent = 'Unique Domains';
  if (labels[3]) labels[3].textContent = 'Files Processed';
  if (labels[4]) labels[4].textContent = 'Rows with Phone';
  if (labels[5]) labels[5].textContent = 'Errors';

  document.getElementById('emlFileName').textContent = `Bulk EML — ${BULK.processed} files`;
  document.getElementById('emlFileSub').innerHTML = `${BULK.rows.length} total rows · ${uniqueEmails.length} unique contacts · ${BULK.errors > 0 ? `<span style="color:#F43F5E">${BULK.errors} errors</span>` : 'no errors'}`;

  // Replace message preview panel with bulk data table
  const emailPanel = document.querySelector('.eml-email-panel');
  if (emailPanel) {
    emailPanel.innerHTML = `
      <div class="eml-panel-title">📊 Bulk Data Table
        <span style="margin-left:auto;display:flex;gap:8px">
          <input id="bulkSearch" placeholder="🔍 Search…" class="eml-search" style="width:180px" oninput="filterBulkTable()">
        </span>
      </div>
      <div style="overflow-x:auto;max-height:520px;overflow-y:auto">
        <table id="bulkTable" style="width:100%;border-collapse:collapse;font-size:12px">
          <thead id="bulkTableHead"></thead>
          <tbody id="bulkTableBody"></tbody>
        </table>
      </div>
      <div style="padding:8px 0;font-size:12px;color:#888" id="bulkTableMeta"></div>`;
  }

  // Replace contacts panel with domain breakdown
  const contactsPanel = document.querySelector('.eml-contacts-panel');
  if (contactsPanel) {
    contactsPanel.innerHTML = `
      <div class="eml-panel-title">🌐 Domain breakdown</div>
      <div id="bulkDomainList" style="overflow-y:auto;max-height:540px"></div>`;
    renderBulkDomains();
  }

  // Update header buttons for bulk mode
  const actions = document.querySelector('.eml-header-actions');
  if (actions) {
    actions.innerHTML = `
      <button class="btn btn-secondary btn-sm" onclick="exportBulkExcel()">⬇ Export Excel</button>
      <button class="btn btn-primary btn-sm"   onclick="pushBulkToCRM()">💾 Push to CRM</button>
      <button class="btn btn-secondary btn-sm" onclick="exitEmlDashboard()">✕ Close</button>`;
  }

  renderBulkTable(BULK.rows);

  document.getElementById('emlFileName').textContent = `Bulk EML — ${BULK.processed} files`;
  document.getElementById('topTitle').textContent = '📧 Bulk Email Intelligence';
  document.getElementById('topSub').textContent = `${BULK.processed} files · ${BULK.rows.length} rows · ${uniqueEmails.length} unique contacts`;

  // Hide domains section (we moved it inline)
  const domSec = document.querySelector('.eml-domains-section');
  if (domSec) domSec.style.display = 'none';

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-eml').classList.add('active');
  document.body.classList.add('eml-mode');
}

const BULK_COLS = ['File Name','Subject','Date','From Name','From Email','Contact Name','Email','Company','Designation','Phone Primary','Phone Secondary','Website','City','Domain','Source','Attachments','Is Reply','Is Forward'];

let bulkFiltered = [];

function renderBulkTable(rows) {
  bulkFiltered = rows;
  const thead = document.getElementById('bulkTableHead');
  const tbody = document.getElementById('bulkTableBody');
  const meta  = document.getElementById('bulkTableMeta');
  if (!thead || !tbody) return;

  thead.innerHTML = `<tr style="position:sticky;top:0;background:#f8f8f8">${BULK_COLS.map(c => `<th style="padding:7px 10px;text-align:left;font-size:11px;font-weight:600;color:#555;border-bottom:1.5px solid #e5e5e5;white-space:nowrap">${c}</th>`).join('')}</tr>`;

  const display = rows.slice(0, 500); // cap at 500 for DOM perf
  tbody.innerHTML = display.map((row, i) => `<tr style="background:${i % 2 === 0 ? '#fff' : '#fafafa'}" onmouseover="this.style.background='#EEF5FF'" onmouseout="this.style.background='${i % 2 === 0 ? '#fff' : '#fafafa'}'">
    ${BULK_COLS.map(c => `<td style="padding:6px 10px;border-bottom:0.5px solid #f0f0f0;white-space:nowrap;max-width:220px;overflow:hidden;text-overflow:ellipsis;color:${c==='Email'?'#378ADD':'#333'}">${escHtml(row[c] || '')}</td>`).join('')}
  </tr>`).join('');

  if (meta) meta.textContent = `Showing ${Math.min(display.length, 500)} of ${rows.length} rows${rows.length > 500 ? ' (export Excel to see all)' : ''}`;
}

function filterBulkTable() {
  const q = (document.getElementById('bulkSearch')?.value || '').toLowerCase();
  const filtered = q ? BULK.rows.filter(r => BULK_COLS.some(c => (r[c] || '').toLowerCase().includes(q))) : BULK.rows;
  renderBulkTable(filtered);
}

function renderBulkDomains() {
  const domainCounts = {};
  BULK.rows.forEach(r => { if (r['Domain']) domainCounts[r['Domain']] = (domainCounts[r['Domain']] || 0) + 1; });
  const sorted = Object.entries(domainCounts).sort((a, b) => b[1] - a[1]);
  const total = BULK.rows.length;
  const colors = ['#378ADD','#6C5CE7','#1D9E75','#EF9F27','#D4537E','#3B82F6','#F97316','#14B8A6'];
  const el = document.getElementById('bulkDomainList');
  if (!el) return;
  el.innerHTML = sorted.map(([d, n], i) => {
    const pct = Math.round(n / total * 100);
    const color = colors[i % colors.length];
    return `<div style="display:flex;align-items:center;gap:8px;padding:7px 4px;border-bottom:0.5px solid #f0f0f0">
      <div style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0"></div>
      <span style="font-size:12px;color:#444;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">@${escHtml(d)}</span>
      <div style="background:#f0f0f0;border-radius:99px;height:5px;width:80px;flex-shrink:0"><div style="height:5px;border-radius:99px;width:${pct}%;background:${color}"></div></div>
      <span style="font-size:11px;color:#888;min-width:24px;text-align:right">${n}</span>
    </div>`;
  }).join('');
}

/* ── Export all rows to Excel ── */
function exportBulkExcel() {
  if (!BULK.rows.length) { showNotification('No data to export.', 'error'); return; }

  const wb = XLSX.utils.book_new();

  // Sheet 1 — all rows
  const headers = BULK_COLS;
  const dataRows = BULK.rows.map(r => headers.map(h => r[h] || ''));
  const ws1 = XLSX.utils.aoa_to_sheet([headers, ...dataRows]);
  ws1['!cols'] = headers.map(h => ({
    wch: h === 'Subject' || h === 'All Phones' || h === 'Links' ? 50 : h === 'File Name' ? 35 : h === 'Email' || h === 'From Email' ? 32 : h === 'Domain' ? 25 : 18
  }));
  XLSX.utils.book_append_sheet(wb, ws1, 'All Contacts');

  // Sheet 2 — deduplicated by email
  const seen = new Set();
  const deduped = BULK.rows.filter(r => { if (seen.has(r['Email'])) return false; seen.add(r['Email']); return true; });
  const ws2 = XLSX.utils.aoa_to_sheet([headers, ...deduped.map(r => headers.map(h => r[h] || ''))]);
  ws2['!cols'] = ws1['!cols'];
  XLSX.utils.book_append_sheet(wb, ws2, 'Unique Contacts');

  // Sheet 3 — summary by domain
  const domCounts = {};
  BULK.rows.forEach(r => { if (r['Domain']) domCounts[r['Domain']] = (domCounts[r['Domain']] || 0) + 1; });
  const domRows = Object.entries(domCounts).sort((a, b) => b[1] - a[1]).map(([d, n]) => [d, n]);
  const ws3 = XLSX.utils.aoa_to_sheet([['Domain', 'Count'], ...domRows]);
  ws3['!cols'] = [{ wch: 30 }, { wch: 10 }];
  XLSX.utils.book_append_sheet(wb, ws3, 'Domain Summary');

  const date = new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, `bulk_eml_export_${date}.xlsx`);
  showNotification(`✅ Exported ${BULK.rows.length} rows (${deduped.length} unique) across 3 sheets`, 'success');
}

/* ── Push all unique contacts into the CRM data table ── */
function pushBulkToCRM() {
  if (!BULK.rows.length) { showNotification('No data to push.', 'error'); return; }

  // Deduplicate by email
  const seen = new Set();
  const deduped = BULK.rows.filter(r => { if (seen.has(r['Email'])) return false; seen.add(r['Email']); return true; });

  const crmRows = deduped.map(r => ({
    'Name':       r['Contact Name'],
    'Email':      r['Email'],
    'Company':    r['Company'],
    'Designation':r['Designation'],
    'Domain':     r['Domain'],
    'Phone Primary': r['Phone Primary'],
    'Phone Secondary': r['Phone Secondary'],
    'Website':    r['Website'],
    'City':       r['City'],
    'From':       r['From Email'],
    'Subject':    r['Subject'],
    'Source':     r['Source'],
    'File':       r['File Name'],
    'Date':       r['Date'],
  }));

  S.rawData = crmRows;
  S.headers = ['Name','Email','Company','Designation','Domain','Phone Primary','Phone Secondary','Website','City','From','Subject','Source','File','Date'];
  S.fileName = `Bulk EML — ${BULK.processed} files`;
  S.sheetName = 'EML Bulk Import';
  S.mapping = {
    'Name':       { type: 'contact', keep: true },
    'Email':      { type: 'email',   keep: true },
    'Company':    { type: 'company', keep: true },
    'Designation':{ type: 'keyword', keep: true },
    'Domain':     { type: 'website', keep: true },
    'Phone Primary': { type: 'phone',   keep: true },
    'Phone Secondary': { type: 'phone',   keep: true },
    'Website':    { type: 'website', keep: true },
    'City':       { type: 'city',    keep: true },
    'From':       { type: 'email',   keep: true },
    'Subject':    { type: 'other',   keep: true },
    'Source':     { type: 'other',   keep: true },
    'File':       { type: 'other',   keep: true },
    'Date':       { type: 'other',   keep: true },
  };
  S.clean = crmRows;
  S.filtered = [...crmRows];
  S.page = 1;

  document.body.classList.remove('eml-mode');
  const domSec = document.querySelector('.eml-domains-section');
  if (domSec) domSec.style.display = '';
  showNotification(`✅ ${deduped.length} unique contacts pushed to CRM table`, 'success');
  const ta = document.getElementById('topActions');
  if (ta) ta.style.display = 'flex';
  showView('table');
}