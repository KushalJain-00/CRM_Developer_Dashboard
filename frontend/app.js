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
  const files = Array.from(fileList).filter(f => /\.(xlsx|xls|csv|txt|pdf)$/i.test(f.name));
  if (!files.length) { showError('No supported files found. Drop .xlsx, .xls, .csv, .txt, or .pdf files.'); return; }

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
  const companyCols = colsByType('company');
  if (!companyCols.length) { S.dupGroups = []; return; }
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
          <td style="padding:10px"><button class="btn btn-secondary btn-sm" onclick="reloadSession(${s.id},'${safeName}')">↺ Reload</button>
          <button class="btn btn-primary btn-sm" style="margin-left:4px" onclick="exportSessionWithCalls(${s.id},'${safeName}')">⬇ Export+Calls</button>
          <button class="btn btn-danger btn-sm" style="margin-left:4px" onclick="deleteSession(${s.id})">🗑</button></td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>`;
  } catch (err) {
    content.innerHTML = `<div class="empty-state">Could not load history: ${err.message}</div>`;
  }
}

async function reloadSession(sessionId, fileName) {
  const res = await fetch(`${API_BASE}/api/history/${sessionId}?page_size=5000`, { headers: apiHeaders() });
  const data = await res.json();
  if (!data.ok || !data.records.length) { alert('No records found.'); return; }
  S.rawData = data.records;
  S.headers = Object.keys(data.records[0]);
  S.fileName = fileName;
  S.sheetName = data.sheet_name;
  S.mapping = data.mapping || {};
  S.sessionId = sessionId;
  if (!Object.keys(S.mapping).length) buildMapping();
  else startProcessing();
}

async function deleteSession(sessionId) {
  if (!confirm('Delete this history entry?')) return;
  await fetch(`${API_BASE}/api/history/${sessionId}`, { method: 'DELETE', headers: apiHeaders() });
  loadHistory();
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