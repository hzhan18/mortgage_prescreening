const BROKER_SLUG = window.BROKER_SLUG;
const BROKER_NAME = window.BROKER_NAME;
const API = (path) => `/b/${BROKER_SLUG}${path}`;

let translations = { en: {}, zh: {} };
let lang = localStorage.getItem('prescreen_lang') || 'en';

let state = {
  client: { name: '', email: '', phone: '' },
  propertyKnown: null,
  property: { price: null, taxMonthly: null, hasCondo: false, condoFees: 0, source: '', note: '' },
  income: null, incomeSource: 'manual', extraction: null,
  downPayment: null, otherDebts: null,
  assumptions: { rate: 5.09, amortYears: 25, heating: 100 }
};
let history = [];
let lastResult = null; // server response from /api/submit, kept so we can re-render on language switch

const progressMap = {
  'landing': 0, 'q-name': 8, 'q-email': 16, 'q-phone': 24, 'q-property-known': 32,
  'q-property-address': 40, 'q-property-confirm': 50, 'q-property-price-range': 40,
  'q-income-upload': 60, 'q-income-confirm': 68, 'q-down-payment': 78, 'q-other-debts': 88, 'results': 100
};

// ---------------- i18n ----------------
function t(key, vars) {
  let str = (translations[lang] && translations[lang][key]) || key;
  if (vars) {
    Object.keys(vars).forEach(k => { str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), vars[k]); });
  }
  return str;
}

function applyStaticTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
  });
  document.getElementById('lang-en').classList.toggle('active', lang === 'en');
  document.getElementById('lang-zh').classList.toggle('active', lang === 'zh');
  updateInviteHeadline();
  updateEmailTitle();
  if (lastResult) renderResults(lastResult);
}

function updateInviteHeadline() {
  const el = document.getElementById('invite-headline');
  el.textContent = BROKER_NAME ? t('invite_headline', { name: BROKER_NAME }) : t('invite_headline_no_name');
}
function updateEmailTitle() {
  const el = document.getElementById('email-title');
  const first = (state.client.name || '').split(' ')[0];
  el.textContent = first ? t('email_title_named', { first_name: first }) : t('email_title');
}

function setLanguage(l) {
  lang = l;
  localStorage.setItem('prescreen_lang', l);
  applyStaticTranslations();
}

async function loadTranslations() {
  const [en, zh] = await Promise.all([
    fetch('/static/i18n/en.json').then(r => r.json()),
    fetch('/static/i18n/zh.json').then(r => r.json())
  ]);
  translations = { en, zh };
  applyStaticTranslations();
}

// ---------------- Screen navigation ----------------
function showScreen(id, pushHistory = true) {
  const current = document.querySelector('.screen.active');
  if (pushHistory && current) history.push(current.dataset.screen);
  document.querySelectorAll('.screen').forEach(el => el.classList.toggle('active', el.dataset.screen === id));
  document.getElementById('progress-bar').style.width = (progressMap[id] || 0) + '%';
  document.getElementById('back-btn').style.visibility = id === 'landing' ? 'hidden' : 'visible';
  window.scrollTo(0, 0);
}
function goBack() {
  if (history.length === 0) return;
  const prev = history.pop();
  document.querySelectorAll('.screen').forEach(el => el.classList.toggle('active', el.dataset.screen === prev));
  document.getElementById('progress-bar').style.width = (progressMap[prev] || 0) + '%';
  document.getElementById('back-btn').style.visibility = prev === 'landing' ? 'hidden' : 'visible';
}
function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2200);
}

// ---------------- Field enabling ----------------
function bindEnabler(inputId, btnId, validFn) {
  document.getElementById(inputId).addEventListener('input', e => {
    document.getElementById(btnId).disabled = !validFn(e.target.value);
  });
}
bindEnabler('in-name', 'btn-name', v => v.trim().length > 0);
bindEnabler('in-email', 'btn-email', v => v.includes('@'));
bindEnabler('in-phone', 'btn-phone', v => v.trim().length > 0);
bindEnabler('in-address', 'btn-address', v => v.trim().length > 0);
bindEnabler('in-price-range', 'btn-price-range', v => parseFloat(v) > 0);
bindEnabler('in-income', 'btn-income', v => parseFloat(v) > 0);
bindEnabler('in-down', 'btn-down', v => v !== '');

// ---------------- Step handlers ----------------
function submitName() {
  state.client.name = document.getElementById('in-name').value.trim();
  updateEmailTitle();
  showScreen('q-email');
}
function submitEmail() { state.client.email = document.getElementById('in-email').value.trim(); showScreen('q-phone'); }
function submitPhone() { state.client.phone = document.getElementById('in-phone').value.trim(); showScreen('q-property-known'); }

function choosePropertyKnown(known) {
  state.propertyKnown = known;
  showScreen(known ? 'q-property-address' : 'q-property-price-range');
}

function toggleRangeCondo() {
  document.getElementById('range-condo-field').style.display = document.getElementById('range-has-condo').checked ? 'block' : 'none';
}
function submitPriceRange() {
  const price = parseFloat(document.getElementById('in-price-range').value) || 0;
  const hasCondo = document.getElementById('range-has-condo').checked;
  const condoFees = hasCondo ? (parseFloat(document.getElementById('range-condo-fees').value) || 0) : 0;
  state.property = {
    price, taxMonthly: Math.round(price * 0.01 / 12), hasCondo, condoFees,
    source: 'estimated', note: 'Property tax estimated at ~1% of price/yr — no specific address provided.'
  };
  showScreen('q-income-upload');
}

// ---- Address lookup (calls our backend, which calls Anthropic) ----
async function submitAddress() {
  const address = document.getElementById('in-address').value.trim();
  const status = document.getElementById('lookup-status');
  status.innerHTML = `<div class="loading-line"><span class="spinner"></span>${t('searching_listings')}</div>`;
  document.getElementById('btn-address').disabled = true;

  try {
    const res = await fetch(API('/api/lookup-property'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    const parsed = await res.json();
    state.property = {
      price: parsed.list_price || null,
      taxMonthly: parsed.estimated_property_tax_monthly || null,
      hasCondo: !!parsed.is_condo,
      condoFees: parsed.condo_fees_monthly || 0,
      source: parsed.found ? 'lookup' : 'not found',
      note: parsed.source_note || ''
    };
  } catch (err) {
    state.property = { price: null, taxMonthly: null, hasCondo: false, condoFees: 0, source: 'error', note: 'Automatic lookup failed — please fill in manually.' };
  }
  document.getElementById('btn-address').disabled = false;
  populateConfirmScreen();
  showScreen('q-property-confirm');
}

function populateConfirmScreen() {
  const p = state.property;
  document.getElementById('edit-price').value = p.price || '';
  document.getElementById('edit-tax').value = p.taxMonthly || '';
  document.getElementById('edit-has-condo').checked = p.hasCondo;
  document.getElementById('edit-condo-fees').value = p.condoFees || '';
  toggleEditCondo();

  const badge = document.getElementById('lookup-badge');
  const note = document.getElementById('lookup-note');
  if (p.source === 'lookup') badge.innerHTML = `<span class="badge high">${t('badge_found')}</span>`;
  else if (p.source === 'estimated') badge.innerHTML = `<span class="badge medium">${t('badge_estimated')}</span>`;
  else badge.innerHTML = `<span class="badge low">${t('badge_not_found')}</span>`;
  note.textContent = p.note || '';
}
function toggleEditCondo() {
  document.getElementById('edit-condo-field').style.display = document.getElementById('edit-has-condo').checked ? 'block' : 'none';
}
function confirmProperty() {
  state.property.price = parseFloat(document.getElementById('edit-price').value) || null;
  state.property.taxMonthly = parseFloat(document.getElementById('edit-tax').value) || 0;
  state.property.hasCondo = document.getElementById('edit-has-condo').checked;
  state.property.condoFees = state.property.hasCondo ? (parseFloat(document.getElementById('edit-condo-fees').value) || 0) : 0;
  showScreen('q-income-upload');
}

// ---- Income upload + extraction (calls our backend) ----
document.getElementById('file-input').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  document.getElementById('file-status').innerHTML = `<div class="loading-line"><span class="spinner"></span>${t('reading_document', { filename: file.name })}</div>`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(API('/api/extract-income'), { method: 'POST', body: formData });
    const parsed = await res.json();
    state.extraction = parsed;
    if (parsed.annual_gross_income > 0) state.incomeSource = 'AI-extracted from ' + (parsed.document_type || 'document');
    document.getElementById('file-status').innerHTML = `<div class="loading-line" style="color:var(--teal);">${t('document_read_ok')}</div>`;
    goToIncomeConfirm(parsed);
  } catch (err) {
    document.getElementById('file-status').innerHTML = `<div class="loading-line" style="color:var(--brick);">${t('document_read_fail')}</div>`;
    setTimeout(() => goToIncomeConfirm(null), 900);
  }
});

function skipToManualIncome() { goToIncomeConfirm(null); }

function goToIncomeConfirm(extracted) {
  const badge = document.getElementById('extract-badge');
  const sub = document.getElementById('income-confirm-sub');
  if (extracted && extracted.annual_gross_income > 0) {
    const conf = (extracted.confidence || 'low').toLowerCase();
    badge.innerHTML = `<div class="lookup-box" style="margin-bottom:16px;">
      <span class="badge ${conf}">${extracted.confidence || 'low'}</span>
      <span class="badge" style="background:#EEF1F4;color:var(--ink);margin-left:6px;">${extracted.document_type}</span>
      ${extracted.notes ? `<div class="note">${extracted.notes}</div>` : ''}
    </div>`;
    document.getElementById('in-income').value = Math.round(extracted.annual_gross_income);
    sub.textContent = t('income_confirm_sub_auto');
  } else {
    badge.innerHTML = '';
    document.getElementById('in-income').value = '';
    sub.textContent = t('income_confirm_sub_manual');
  }
  document.getElementById('btn-income').disabled = !(parseFloat(document.getElementById('in-income').value) > 0);
  showScreen('q-income-confirm');
}
function submitIncome() { state.income = parseFloat(document.getElementById('in-income').value) || 0; showScreen('q-down-payment'); }
function submitDown() { state.downPayment = parseFloat(document.getElementById('in-down').value) || 0; showScreen('q-other-debts'); }

async function submitDebts() {
  state.otherDebts = parseFloat(document.getElementById('in-debts').value) || 0;
  await submitAssessment();
}

// ---- Final submit: server computes GDS/TDS and saves the lead ----
async function submitAssessment(overrideAssumptions) {
  if (overrideAssumptions) state.assumptions = { ...state.assumptions, ...overrideAssumptions };
  const payload = {
    name: state.client.name, email: state.client.email, phone: state.client.phone, language: lang,
    annual_income: state.income, income_source: state.incomeSource,
    property_address: document.getElementById('in-address') ? document.getElementById('in-address').value : '',
    property_price: state.property.price, property_tax_monthly: state.property.taxMonthly,
    has_condo: state.property.hasCondo, condo_fees_monthly: state.property.condoFees,
    property_source: state.property.source,
    down_payment: state.downPayment, other_monthly_debts: state.otherDebts,
    heating_monthly: state.assumptions.heating, contract_rate_pct: state.assumptions.rate,
    amortization_years: state.assumptions.amortYears
  };
  const res = await fetch(API('/api/submit'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
  });
  const result = await res.json();
  lastResult = result;
  renderResults(result);
  showScreen('results');
}

function gaugeHTML(label, value, limit) {
  const scaleMax = limit * 1.25;
  const fillPct = Math.min(value / scaleMax * 100, 100);
  const limitPct = limit / scaleMax * 100;
  const over = value > limit;
  return `<div class="gauge-row">
    <div class="gauge-title">${label}</div>
    <div class="gauge-track"><div class="gauge-fill ${over ? 'over' : 'ok'}" style="width:${fillPct}%"></div><div class="gauge-limit-mark" style="left:${limitPct}%"></div></div>
    <div class="gauge-val mono">${value.toFixed(1)}%</div>
  </div>`;
}

function renderResults(r) {
  const fmt = n => '$' + Math.round(n).toLocaleString();
  const box = document.getElementById('results-content');
  const firstName = (state.client.name || '').split(' ')[0];

  const gauges = `<div style="margin:20px 0 6px;">${gaugeHTML(t('gds_label'), r.actual_gds_pct, 39)}${gaugeHTML(t('tds_label'), r.actual_tds_pct, 44)}</div>`;

  let compareHTML = '';
  if (state.property.price) {
    const withinReach = r.max_purchase_price >= state.property.price;
    compareHTML = `<div class="compare-box ${withinReach ? '' : 'warn'}">
      ${withinReach
        ? t('compare_within_reach', { price: fmt(state.property.price) })
        : t('compare_above_reach', { price: fmt(state.property.price), diff: fmt(state.property.price - r.max_purchase_price) })}
    </div>`;
  }

  let clientSection;
  if (r.qualifies) {
    clientSection = `
      <div class="hero-label">${t('max_purchase_label')}</div>
      <div class="hero-number">${fmt(r.max_purchase_price)}</div>
      <div style="color:var(--muted); font-size:14px;">${t('max_mortgage_note', { mortgage: fmt(r.max_mortgage), down: fmt(state.downPayment) })}</div>
      ${compareHTML}${gauges}
      <div class="disclaimer">${t('client_message_qualifies', { first_name: firstName, mortgage: fmt(r.max_mortgage), price: fmt(r.max_purchase_price) })}</div>`;
  } else {
    clientSection = `
      <div class="hero-label">${t('result_title_no')}</div>
      <div class="hero-number neg">${t('not_qualifying')}</div>
      <div style="color:var(--muted); font-size:14px;">${t('ratio_exceeds', { ratio: r.binding_ratio })}</div>
      ${compareHTML}${gauges}
      <div class="disclaimer">${t('client_message_no', { first_name: firstName, ratio: r.binding_ratio })}</div>`;
  }

  const assumptionsHTML = `
    <details class="assump">
      <summary>${t('assumptions_summary')}</summary>
      <div class="assump-fields">
        <div><label>${t('assump_rate_label')}</label><input type="number" step="0.01" id="assump-rate" value="${state.assumptions.rate}"></div>
        <div><label>${t('assump_amort_label')}</label>
          <select id="assump-amort"><option value="25" ${state.assumptions.amortYears == 25 ? 'selected' : ''}>25</option><option value="30" ${state.assumptions.amortYears == 30 ? 'selected' : ''}>30</option></select>
        </div>
        <div><label>${t('assump_heating_label')}</label><input type="number" id="assump-heating" value="${state.assumptions.heating}"></div>
      </div>
      <button class="btn secondary" style="margin-top:14px;" onclick="recalcFromAssumptions()">${t('recalculate')}</button>
    </details>`;

  box.innerHTML = `
    <div class="eyebrow">${t('result_eyebrow')}</div>
    <h2 class="qtitle">${r.qualifies ? t('result_title_qualifies') : t('result_title_no')}</h2>
    ${clientSection}
    ${assumptionsHTML}
    <div style="margin-top:24px;">
      <h2 style="font-size:19px;">${t('broker_summary_title')}</h2>
      <p style="color:var(--muted); font-size:13.5px; margin-top:-6px;">${t('broker_summary_sub')}</p>
      <div class="summary-block" id="summary-block"></div>
      <div class="btn-row">
        <button class="btn" onclick="copySummary()">${t('copy_summary')}</button>
        <button class="btn secondary" onclick="emailSummary()">${t('open_mail')}</button>
      </div>
    </div>`;
  document.getElementById('summary-block').textContent = r.summary_text;
}

function recalcFromAssumptions() {
  const rate = parseFloat(document.getElementById('assump-rate').value) || 5.09;
  const amortYears = parseFloat(document.getElementById('assump-amort').value) || 25;
  const heating = parseFloat(document.getElementById('assump-heating').value) || 100;
  submitAssessment({ rate, amortYears, heating }).then(() => showToast(t('recalculated_toast')));
}

function copySummary() {
  navigator.clipboard.writeText((lastResult && lastResult.summary_text) || '').then(() => showToast(t('copied_toast')));
}
function emailSummary() {
  const subject = encodeURIComponent(`Pre-screening summary — ${state.client.name}`);
  const body = encodeURIComponent((lastResult && lastResult.summary_text) || '');
  window.location.href = `mailto:?subject=${subject}&body=${body}`;
}

function resetAll() {
  state = {
    client: { name: '', email: '', phone: '' }, propertyKnown: null,
    property: { price: null, taxMonthly: null, hasCondo: false, condoFees: 0, source: '', note: '' },
    income: null, incomeSource: 'manual', extraction: null,
    downPayment: null, otherDebts: null,
    assumptions: { rate: 5.09, amortYears: 25, heating: 100 }
  };
  history = []; lastResult = null;
  document.querySelectorAll('input[type=text],input[type=email],input[type=tel],input[type=number]').forEach(el => el.value = '');
  document.getElementById('file-status').innerHTML = '';
  document.getElementById('lookup-status').innerHTML = '';
  showScreen('landing', false);
}

// ---------------- Init ----------------
loadTranslations();
showScreen('landing', false);
