const API = '/api/admin/manage/';

let _token = null;
async function getToken() {
  if (_token) return _token;
  try {
    const res = await fetch('/api/account/token/');
    if (res.ok) _token = (await res.json()).token;
  } catch (_) {}
  return _token;
}

async function api(url, options = {}) {
  const token = await getToken();
  const res = await fetch(url, {
    ...options,
    headers: token ? {Authorization: `Token ${token}`, ...options.headers} : options.headers,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || JSON.stringify(data) || `Request failed (${res.status})`);
  return data;
}

const escapeHtml = (s) => DOMPurify.sanitize(s ?? '', {ALLOWED_TAGS: []});

function confirmDelete(message) {
  return new Promise((resolve) => {
    const modalEl = document.getElementById('admin-confirm-modal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const confirmBtn = document.getElementById('admin-confirm-confirm');
    document.getElementById('admin-confirm-body').textContent = message;

    function cleanup() {
      confirmBtn.removeEventListener('click', onConfirm);
      modalEl.removeEventListener('hidden.bs.modal', onHidden);
    }
    function onConfirm() { cleanup(); resolve(true); modal.hide(); }
    function onHidden() { cleanup(); resolve(false); }

    confirmBtn.addEventListener('click', onConfirm);
    modalEl.addEventListener('hidden.bs.modal', onHidden);
    modal.show();
  });
}

// ---- Reference data (for FK selects / display lookups) ----

const refData = { groups: [], exams: [], users: [] };
const REF_LABEL_FIELD = { groups: 'name', exams: 'name', users: 'username' };

// Falls back to [] rather than throwing - a staff-only (non-admin) user can
// load exams but not groups/users, and vice versa isn't possible but the
// page should still render whatever sections it can rather than failing whole-hog.
async function safeApi(url) {
  try {
    return await api(url);
  } catch (err) {
    return [];
  }
}

async function loadRefData() {
  const [groups, exams, users] = await Promise.all([
    safeApi(API + 'groups/'), safeApi(API + 'exams/'), safeApi(API + 'users/'),
  ]);
  refData.groups = groups;
  refData.exams = exams;
  refData.users = users;
}

function refLabel(source, id) {
  if (id === null || id === undefined || id === '') return '';
  const item = refData[source].find((i) => i.id === id);
  return item ? item[REF_LABEL_FIELD[source]] : `#${id}`;
}

// ---- Resource configs ----

const RESOURCES = {
  invites: {
    label: 'Invites', url: 'invites/',
    columns: [
      { key: 'email', label: 'Email' },
      { key: 'group', label: 'Group', type: 'ref', source: 'groups' },
      { key: 'createdAt', label: 'Created', type: 'date' },
      { key: 'expiresAt', label: 'Expires', type: 'date' },
      { key: 'acceptedAt', label: 'Accepted', type: 'date' },
    ],
    fields: [
      { key: 'email', label: 'Email', type: 'text', required: true },
      { key: 'group', label: 'Group', type: 'select', source: 'groups', nullable: true },
      { key: 'expiresAt', label: 'Expires at (ISO 8601, blank = default 7 days)', type: 'text', omitIfBlank: true },
    ],
  },
  attempts: {
    label: 'Attempts', url: 'attempts/', readOnly: true,
    columns: [
      { key: 'exam', label: 'Exam', type: 'ref', source: 'exams' },
      { key: 'user', label: 'User', type: 'ref', source: 'users' },
      { key: 'finishedAt', label: 'Finished', type: 'date' },
      { key: 'numCorrect', label: 'Correct' },
      { key: 'numQuestions', label: 'Total' },
      { key: 'percentCorrect', label: '%', type: 'pct' },
      { key: 'grade', label: 'Grade' },
      { key: 'pointsEarned', label: 'Points' },
    ],
    fields: [],
    rowActions: [
      { label: 'Detail', icon: 'bi-search', action: 'detail' },
      { label: 'Re-evaluate', icon: 'bi-patch-check', action: 're-evaluate', btnClass: 'btn-outline-primary' },
    ],
    headerAction: { label: '<i class="bi bi-download me-1"></i>Export CSV', fn: 'exportAttempts' },
  },
  sessions: {
    label: 'Multiplayer Sessions', url: 'sessions/',
    columns: [
      { key: 'roomCode', label: 'Room code' },
      { key: 'exam', label: 'Exam', type: 'ref', source: 'exams' },
      { key: 'host', label: 'Host', type: 'ref', source: 'users' },
      { key: 'status', label: 'Status' },
      { key: 'createdAt', label: 'Created', type: 'date' },
    ],
    fields: [
      { key: 'exam', label: 'Exam', type: 'select', source: 'exams', required: true },
      { key: 'host', label: 'Host', type: 'select', source: 'users', nullable: true },
      { key: 'status', label: 'Status', type: 'select', options: ['lobby', 'active', 'paused', 'finished', 'abandoned'] },
      { key: 'currentIndex', label: 'Current question index', type: 'number', default: 0 },
      { key: 'timeLimitSeconds', label: 'Time limit (seconds, 0 = none)', type: 'number', default: 0 },
      { key: 'questionsJson', label: 'Questions snapshot (JSON)', type: 'json' },
    ],
    rowActions: [{ label: 'Participants', icon: 'bi-people', nested: 'participants', parentLabelKey: 'roomCode' }],
  },
  participants: {
    label: 'Participants', url: 'participants/', parentParam: 'session',
    columns: [
      { key: 'displayName', label: 'Name' },
      { key: 'score', label: 'Score' },
      { key: 'connected', label: 'Connected', type: 'bool' },
      { key: 'joinedAt', label: 'Joined', type: 'date' },
    ],
    fields: [
      { key: 'clientId', label: 'Client ID', type: 'text', required: true },
      { key: 'displayName', label: 'Display name', type: 'text', required: true },
      { key: 'score', label: 'Score', type: 'number', default: 0 },
      { key: 'connected', label: 'Connected', type: 'bool', default: true },
    ],
  },
  users: {
    label: 'Users', url: 'users/',
    columns: [
      { key: 'username', label: 'Username' },
      { key: 'email', label: 'Email' },
      { key: 'isStaff', label: 'Staff', type: 'bool' },
      { key: 'isSuperuser', label: 'Superuser', type: 'bool' },
      { key: 'isActive', label: 'Active', type: 'bool' },
    ],
    fields: [
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'email', label: 'Email', type: 'text' },
      { key: 'firstName', label: 'First name', type: 'text' },
      { key: 'lastName', label: 'Last name', type: 'text' },
      { key: 'password', label: 'Password', type: 'password', hint: 'Leave blank to keep the current password', requiredOnCreate: true },
      { key: 'isActive', label: 'Active', type: 'bool', default: true },
      { key: 'isStaff', label: 'Staff', type: 'bool' },
      { key: 'isSuperuser', label: 'Superuser', type: 'bool' },
      { key: 'mustChangePassword', label: 'Must change password on next login', type: 'bool' },
      { key: 'groups', label: 'Groups', type: 'multiselect', source: 'groups' },
    ],
  },
};

// ---- Generic field rendering ----

function selectOptionsHtml(field, value) {
  const opts = field.source
    ? refData[field.source].map((i) => [i.id, i[REF_LABEL_FIELD[field.source]]])
    : field.options.map((o) => [o, o]);
  const blank = field.nullable ? '<option value="">—</option>' : '';
  return blank + opts.map(([id, label]) =>
    `<option value="${escapeHtml(id)}" ${String(value) === String(id) ? 'selected' : ''}>${escapeHtml(label)}</option>`
  ).join('');
}

function fieldInputHtml(field, value, isCreate) {
  const v = value !== undefined && value !== null ? value : field.default;
  const req = (field.required || (isCreate && field.requiredOnCreate)) ? 'required' : '';
  switch (field.type) {
    case 'bool':
      return `<div class="form-check"><input type="checkbox" class="form-check-input" name="${field.key}" ${v ? 'checked' : ''}></div>`;
    case 'number':
      return `<input type="number" class="form-control" name="${field.key}" value="${v ?? 0}" ${req}>`;
    case 'password':
      return `<input type="password" class="form-control" name="${field.key}" placeholder="${escapeHtml(field.hint || '')}" autocomplete="new-password" ${req}>`;
    case 'select':
      return `<select class="form-select" name="${field.key}" ${req}>${selectOptionsHtml(field, v)}</select>`;
    case 'multiselect': {
      const selected = new Set((v || []).map(String));
      const opts = refData[field.source].map((i) =>
        `<option value="${i.id}" ${selected.has(String(i.id)) ? 'selected' : ''}>${escapeHtml(i[REF_LABEL_FIELD[field.source]])}</option>`
      ).join('');
      return `<select class="form-select" name="${field.key}" multiple>${opts}</select>`;
    }
    case 'textarea':
      return `<textarea class="form-control" name="${field.key}" rows="3" ${req}>${escapeHtml(v || '')}</textarea>`;
    case 'json':
      return `<textarea class="form-control font-monospace" name="${field.key}" rows="6">${escapeHtml(JSON.stringify(v ?? null, null, 2))}</textarea>`;
    default:
      return `<input type="text" class="form-control" name="${field.key}" value="${escapeHtml(v ?? '')}" ${req}>`;
  }
}

function collectFormData(fields, formEl) {
  const payload = {};
  for (const field of fields) {
    const el = formEl.elements[field.key];
    if (!el) continue;
    switch (field.type) {
      case 'bool':
        payload[field.key] = el.checked;
        break;
      case 'number':
        payload[field.key] = el.value === '' ? null : Number(el.value);
        break;
      case 'password':
        if (el.value) payload[field.key] = el.value;
        break;
      case 'multiselect':
        payload[field.key] = Array.from(el.selectedOptions).map((o) => Number(o.value));
        break;
      case 'select':
        payload[field.key] = el.value === '' ? null : (field.source ? Number(el.value) : el.value);
        break;
      case 'json':
        payload[field.key] = el.value.trim() ? JSON.parse(el.value) : null;
        break;
      default:
        // Blank optional text field (e.g. expiresAt) - omit rather than send ""
        // so the server's model default/existing value applies instead of a
        // DateTimeField validation error on an empty string.
        if (el.value === '' && field.omitIfBlank) break;
        payload[field.key] = el.value;
    }
  }
  return payload;
}

// ---- Section / nested-view state ----

let activeSection = null;
let nestedView = null; // {type, parentId, parentLabel, parentSection}

async function renderSection(key) {
  activeSection = key;
  nestedView = null;
  document.getElementById('admin-breadcrumb').classList.add('d-none');
  document.querySelectorAll('#admin-tabs button').forEach((b) => {
    b.classList.toggle('active', b.dataset.section === key);
  });

  if (key === 'appSettings') return renderAppSettingsSection();
  if (key === 'emailSettings') return renderEmailSettingsSection();
  if (key === 'apiToken') return renderApiTokenSection();
  if (key === 'groups') return renderGroupsSection();
  if (key === 'gradeScales') return renderGradeScalesSection();
  return renderListSection(key);
}

async function renderListSection(key, opts = {}) {
  const config = RESOURCES[key];
  document.getElementById('admin-section-title').textContent = config.label;
  const createBtn = document.getElementById('admin-create-btn');
  createBtn.classList.toggle('d-none', !!config.readOnly);
  if (!config.readOnly) createBtn.onclick = () => openFormModal(key, null, opts.extraPayload);

  const headerActionBtn = document.getElementById('admin-header-action-btn');
  if (config.headerAction) {
    headerActionBtn.innerHTML = config.headerAction.label;
    headerActionBtn.classList.remove('d-none');
    headerActionBtn.onclick = null;
  } else {
    headerActionBtn.classList.add('d-none');
  }

  const content = document.getElementById('admin-content');
  content.innerHTML = '<p class="text-muted small">Loading…</p>';

  let url = API + config.url;
  if (config.parentParam && opts.parentId) url += `?${config.parentParam}=${opts.parentId}`;
  const items = await api(url);
  content.innerHTML = renderTable(config, items, key, opts);
  wireRowButtons(config, items, key, opts);

  if (config.headerAction && config.headerAction.fn === 'exportAttempts') {
    headerActionBtn.onclick = () => exportAttemptsCSV(items);
  }
}

function renderTable(config, items, key, opts) {
  if (!items.length) return '<p class="text-muted small mb-0">No records yet.</p>';
  const headers = config.columns.map((c) => `<th>${escapeHtml(c.label)}</th>`).join('');
  const rows = items.map((item) => {
    const cells = config.columns.map((c) => `<td>${renderCell(c, item[c.key])}</td>`).join('');
    const rowActions = (config.rowActions || []).map((ra) =>
      ra.nested
        ? `<button class="btn btn-outline-secondary btn-sm me-1" data-nested="${ra.nested}" data-id="${item.id}" data-label="${escapeHtml(item[ra.parentLabelKey] || '')}">
            <i class="bi ${ra.icon} me-1"></i>${escapeHtml(ra.label)}
           </button>`
        : `<button class="btn ${ra.btnClass || 'btn-outline-secondary'} btn-sm me-1" data-row-action="${ra.action}" data-id="${item.id}">
            <i class="bi ${ra.icon} me-1"></i>${escapeHtml(ra.label)}
           </button>`
    ).join('');
    const mutateButtons = config.readOnly ? '' : `
        <button class="btn btn-primary btn-sm me-1" data-action="edit"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-danger btn-sm" data-action="delete"><i class="bi bi-trash"></i></button>`;
    return `<tr data-id="${item.id}">
      ${cells}
      <td class="text-end text-nowrap">
        ${rowActions}
        ${mutateButtons}
      </td>
    </tr>`;
  }).join('');
  return `<div class="table-responsive"><table class="table table-sm align-middle">
    <thead><tr>${headers}<th></th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

function renderCell(column, value) {
  if (column.type === 'bool') return value ? '<i class="bi bi-check-lg text-success"></i>' : '';
  if (column.type === 'date') return value ? new Date(value).toLocaleString() : '';
  if (column.type === 'ref') return escapeHtml(refLabel(column.source, value));
  if (column.type === 'pct') return `${value ?? 0}%`;
  return escapeHtml(value);
}

function wireRowButtons(config, items, key, opts) {
  const content = document.getElementById('admin-content');
  content.querySelectorAll('tr[data-id]').forEach((row) => {
    const id = Number(row.dataset.id);
    const item = items.find((i) => i.id === id);
    row.querySelector('[data-action="edit"]')?.addEventListener('click', () => openFormModal(key, item, opts.extraPayload));
    row.querySelector('[data-action="delete"]')?.addEventListener('click', async () => {
      if (await confirmDelete(`Delete this ${config.label.toLowerCase()} record?`)) {
        await api(`${API}${config.url}${id}/`, { method: 'DELETE' });
        await loadRefData();
        renderListSection(key, opts);
      }
    });
    row.querySelectorAll('[data-nested]').forEach((btn) => {
      btn.addEventListener('click', () => openNestedView(btn.dataset.nested, id, btn.dataset.label, key));
    });
    row.querySelectorAll('[data-row-action]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const rowAction = btn.dataset.rowAction;
        if (rowAction === 'detail') openAttemptDetail(Number(btn.dataset.id), item);
        if (rowAction === 're-evaluate') openReEvalModal(Number(btn.dataset.id), item);
      });
    });
  });
}

function openNestedView(nestedKey, parentId, parentLabel, parentSection) {
  nestedView = { type: nestedKey, parentId, parentLabel, parentSection };
  const bc = document.getElementById('admin-breadcrumb');
  bc.classList.remove('d-none');
  document.getElementById('admin-breadcrumb-text').textContent =
    `${RESOURCES[nestedKey].label} for ${parentLabel}`;
  document.getElementById('admin-back-btn').onclick = () => renderSection(parentSection);
  renderListSection(nestedKey, { parentId, extraPayload: { [RESOURCES[nestedKey].parentParam]: parentId } });
}

// ---- Create/edit modal ----

function openFormModal(key, item, extraPayload) {
  const config = RESOURCES[key];
  const modalEl = document.getElementById('admin-form-modal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const form = document.getElementById('admin-form');
  const errorEl = document.getElementById('admin-form-error');
  errorEl.classList.add('d-none');
  document.getElementById('admin-form-modal-title').textContent = item ? `Edit ${config.label}` : `Add ${config.label}`;

  form.innerHTML = config.fields.map((field) => `
    <div class="mb-3">
      <label class="form-label">${escapeHtml(field.label)}</label>
      ${fieldInputHtml(field, item ? item[field.key] : undefined, !item)}
    </div>
  `).join('');

  const saveBtn = document.getElementById('admin-form-save');
  saveBtn.onclick = async () => {
    errorEl.classList.add('d-none');
    try {
      const payload = { ...collectFormData(config.fields, form), ...(extraPayload || {}) };
      if (item) {
        await api(`${API}${config.url}${item.id}/`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      } else {
        await api(`${API}${config.url}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      }
      await loadRefData();
      modal.hide();
      if (nestedView && nestedView.type === key) {
        renderListSection(key, { parentId: nestedView.parentId, extraPayload });
      } else {
        renderSection(activeSection);
      }
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
    }
  };

  modal.show();
}

// ---- Attempt detail drill-down ----

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

async function openReEvalModal(id, item) {
  const modalEl = document.getElementById('admin-form-modal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const form = document.getElementById('admin-form');
  const errorEl = document.getElementById('admin-form-error');
  const saveBtn = document.getElementById('admin-form-save');

  document.getElementById('admin-form-modal-title').textContent = 'Re-evaluate Grade';
  errorEl.classList.add('d-none');
  saveBtn.disabled = false;

  const scales = await api('/api/grade-scales').catch(() => []);
  const scaleOptions = scales.map((s) =>
    `<option value="${s.id}" ${s.id === item.gradeScale ? 'selected' : ''}>${escapeHtml(s.name)}</option>`
  ).join('');

  form.innerHTML = `
    <div class="mb-3">
      <label class="form-label">Grade scale</label>
      <select class="form-select" id="re-eval-scale-select">
        <option value="">— None (clear grade) —</option>
        ${scaleOptions}
      </select>
    </div>
    <div class="mb-3">
      <label class="form-label">Note <span class="text-danger">*</span></label>
      <input type="text" class="form-control" id="re-eval-note-input" placeholder="Reason for this change">
    </div>`;

  modal.show();

  saveBtn.onclick = async () => {
    const note = document.getElementById('re-eval-note-input').value.trim();
    if (!note) {
      errorEl.textContent = 'A note is required.';
      errorEl.classList.remove('d-none');
      return;
    }
    errorEl.classList.add('d-none');
    saveBtn.disabled = true;
    try {
      const scaleId = document.getElementById('re-eval-scale-select').value;
      await api(`${API}attempts/${id}/re-evaluate/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gradeScaleId: scaleId ? Number(scaleId) : null, note }),
      });
      modal.hide();
      renderListSection('attempts');
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
      saveBtn.disabled = false;
    }
  };
}

async function openAttemptDetail(id, item) {
  const modalEl = document.getElementById('attempt-detail-modal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const body = document.getElementById('attempt-detail-body');
  const title = document.getElementById('attempt-detail-title');
  const exportBtn = document.getElementById('attempt-export-missed-btn');
  const generateBtn = document.getElementById('attempt-generate-exam-btn');

  title.textContent = 'Loading…';
  body.innerHTML = '<p class="text-muted">Loading…</p>';
  exportBtn.classList.add('d-none');
  generateBtn.classList.add('d-none');
  exportBtn.onclick = null;
  generateBtn.onclick = null;
  modal.show();

  try {
    const data = await api(`${API}attempts/${id}/drill/`);
    const missed = data.results.filter((r) => !r.isCorrect);
    const pctClass = data.percentCorrect >= 70 ? 'bg-success' : 'bg-danger';

    title.textContent = `${data.examName} — ${data.user}`;

    const gradeHtml = data.grade
      ? `<span class="badge bg-info text-dark">${escapeHtml(data.grade)}</span>` : '';
    const bonusHtml = data.bonusPointsEarned > 0
      ? `<span class="badge bg-warning text-dark">+${data.bonusPointsEarned} bonus</span>` : '';
    let html = `<div class="d-flex flex-wrap gap-2 mb-4">
      <span class="badge bg-secondary">${new Date(data.finishedAt).toLocaleString()}</span>
      <span class="badge bg-primary">${data.numCorrect}/${data.numQuestions} correct</span>
      <span class="badge ${pctClass}">${data.percentCorrect}%</span>
      ${gradeHtml}
      <span class="badge bg-secondary">${data.basePointsEarned}/${data.totalPoints} pts</span>
      ${bonusHtml}
    </div>`;

    if (!missed.length) {
      html += '<p class="text-success"><i class="bi bi-check-circle me-1"></i>All questions answered correctly.</p>';
    } else {
      html += `<h6 class="mb-3">${missed.length} Missed Question${missed.length !== 1 ? 's' : ''}</h6>`;
      html += missed.map((r, i) => {
        const correct = r.options.filter((o) => o.isCorrect);
        const selected = r.options.filter((o) => r.selectedOptionIds.includes(o.id));
        const correctHtml = correct.map((o) => DOMPurify.sanitize(o.text)).join(', ');
        const selectedHtml = selected.length ? selected.map((o) => DOMPurify.sanitize(o.text)).join(', ') : '<em>No answer</em>';
        return `<div class="card mb-3 border-danger-subtle">
          <div class="card-body py-2">
            <p class="mb-2 fw-semibold">${i + 1}. ${DOMPurify.sanitize(r.questionText)}</p>
            <p class="mb-1 text-success small"><i class="bi bi-check-circle me-1"></i><strong>Correct:</strong> ${correctHtml}</p>
            <p class="${r.explanation ? 'mb-1' : 'mb-0'} text-danger small"><i class="bi bi-x-circle me-1"></i><strong>Your answer:</strong> ${selectedHtml}</p>
            ${r.explanation ? `<p class="mb-0 text-muted small"><i class="bi bi-lightbulb me-1"></i>${DOMPurify.sanitize(r.explanation)}</p>` : ''}
          </div>
        </div>`;
      }).join('');
    }

    // Grade log
    if (data.gradeLog?.length) {
      html += `<hr>
      <h6 class="mb-2">Grade History</h6>
      <div class="table-responsive">
        <table class="table table-sm table-borderless mb-0">
          <thead class="text-muted small"><tr><th>Date</th><th>By</th><th>Scale</th><th>Grade</th><th>Note</th></tr></thead>
          <tbody>
            ${data.gradeLog.map((e) => `<tr>
              <td class="text-nowrap small">${new Date(e.changedAt).toLocaleString()}</td>
              <td class="small">${escapeHtml(e.changedBy)}</td>
              <td class="small">${e.scaleName ? escapeHtml(e.scaleName) : '<span class="text-muted">—</span>'}</td>
              <td>${e.newGrade ? `<span class="badge bg-info text-dark">${escapeHtml(e.newGrade)}</span>` : '<span class="text-muted">—</span>'}</td>
              <td class="small">${escapeHtml(e.note)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    }

    body.innerHTML = html;

    if (missed.length) {
      exportBtn.classList.remove('d-none');
      generateBtn.classList.remove('d-none');

      exportBtn.onclick = async () => {
        const token = await getToken();
        const res = await fetch(`${API}attempts/${id}/missed-csv/`, {
          headers: token ? { Authorization: `Token ${token}` } : {},
        });
        if (!res.ok) { alert('Export failed.'); return; }
        const filename = res.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || `missed_${id}.csv`;
        downloadBlob(await res.blob(), filename);
      };

      generateBtn.onclick = async () => {
        generateBtn.disabled = true;
        try {
          const result = await api(`${API}attempts/${id}/generate-exam/`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
          });
          modal.hide();
          alert(`Created "${result.examName}" with ${result.questionCount} question${result.questionCount !== 1 ? 's' : ''}. Find it in your Library.`);
        } catch (err) {
          alert(`Failed: ${err.message}`);
        } finally {
          generateBtn.disabled = false;
        }
      };
    }
  } catch (err) {
    body.innerHTML = `<p class="text-danger">${escapeHtml(err.message)}</p>`;
  }
}

function exportAttemptsCSV(items) {
  const headers = ['ID', 'Exam', 'User', 'Finished', 'Correct', 'Total', '%', 'Points Earned', 'Total Points'];
  const rows = items.map((item) => [
    item.id,
    refLabel('exams', item.exam),
    refLabel('users', item.user),
    item.finishedAt ? new Date(item.finishedAt).toLocaleString() : '',
    item.numCorrect,
    item.numQuestions,
    `${item.percentCorrect ?? 0}%`,
    item.pointsEarned,
    item.totalPoints,
  ]);
  const csv = [headers, ...rows]
    .map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n');
  downloadBlob(new Blob([csv], { type: 'text/csv' }), 'attempts.csv');
}

// ---- Grade Scales ----

async function renderGradeScalesSection() {
  document.getElementById('admin-section-title').textContent = 'Grade Scales';
  document.getElementById('admin-header-action-btn').classList.add('d-none');
  const createBtn = document.getElementById('admin-create-btn');
  createBtn.classList.remove('d-none');
  createBtn.onclick = () => openGradeScaleModal(null);

  const content = document.getElementById('admin-content');
  content.innerHTML = '<p class="text-muted small">Loading…</p>';
  const scales = await api(API + 'grade-scales/');
  if (!scales.length) {
    content.innerHTML = '<p class="text-muted small mb-0">No grade scales yet. Add one to get started.</p>';
    return;
  }
  content.innerHTML = `<div class="table-responsive"><table class="table table-sm align-middle">
    <thead><tr><th>Name</th><th>Entries</th><th></th></tr></thead>
    <tbody>${scales.map((s) => `
      <tr data-id="${s.id}">
        <td>${escapeHtml(s.name)}</td>
        <td>${(s.entriesJson || []).length}</td>
        <td class="text-end text-nowrap">
          <button class="btn btn-primary btn-sm me-1" data-action="edit"><i class="bi bi-pencil"></i></button>
          <button class="btn btn-danger btn-sm" data-action="delete"><i class="bi bi-trash"></i></button>
        </td>
      </tr>`).join('')}
    </tbody>
  </table></div>`;

  content.querySelectorAll('tr[data-id]').forEach((row) => {
    const id = Number(row.dataset.id);
    const scale = scales.find((s) => s.id === id);
    row.querySelector('[data-action="edit"]').addEventListener('click', () => openGradeScaleModal(scale));
    row.querySelector('[data-action="delete"]').addEventListener('click', async () => {
      if (await confirmDelete(`Delete the "${scale.name}" grade scale? Exams using it will no longer have a grade scale assigned.`)) {
        await api(`${API}grade-scales/${id}/`, { method: 'DELETE' });
        renderGradeScalesSection();
      }
    });
  });
}

const GRADE_OPERATORS = ['>=', '<=', '>', '<', '=='];
const GRADE_OPERATOR_LABELS = {
  '>=': 'Greater than or equal to',
  '<=': 'Less than or equal to',
  '>':  'Greater than',
  '<':  'Less than',
  '==': 'Equal to',
};

function addGradeScaleEntryRow(container, value = '', operator = '>=', grade = '') {
  const row = document.createElement('div');
  row.className = 'd-flex gap-2 align-items-center gs-entry-row';
  const opOptions = GRADE_OPERATORS.map((op) =>
    `<option value="${op}" ${op === operator ? 'selected' : ''}>${GRADE_OPERATOR_LABELS[op]}</option>`
  ).join('');
  row.innerHTML = `
    <input type="number" class="form-control form-control-sm" placeholder="%" min="0" max="100" value="${escapeHtml(String(value))}" style="width:5rem;flex-shrink:0;">
    <select class="form-select form-select-sm" style="width:auto;flex-shrink:0;">${opOptions}</select>
    <input type="text" class="form-control form-control-sm" placeholder="Grade (e.g. A)" value="${escapeHtml(grade)}">
    <button type="button" class="btn btn-outline-danger btn-sm gs-remove-row" title="Remove"><i class="bi bi-x-lg"></i></button>
  `;
  row.querySelector('.gs-remove-row').addEventListener('click', () => row.remove());
  container.appendChild(row);
}

async function openGradeScaleModal(scale) {
  const modalEl = document.getElementById('admin-form-modal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const form = document.getElementById('admin-form');
  const errorEl = document.getElementById('admin-form-error');
  errorEl.classList.add('d-none');
  document.getElementById('admin-form-modal-title').textContent = scale ? 'Edit Grade Scale' : 'Add Grade Scale';

  form.innerHTML = `
    <div class="mb-3">
      <label class="form-label">Name</label>
      <input type="text" class="form-control" id="gs-name" value="${escapeHtml(scale?.name || '')}" required>
    </div>
    <label class="form-label">Grade Entries <span class="text-muted small">(minimum % to earn this grade)</span></label>
    <div id="gs-entries" class="d-flex flex-column gap-2 mb-2"></div>
    <button type="button" class="btn btn-outline-secondary btn-sm" id="gs-add-row">
      <i class="bi bi-plus-lg me-1"></i>Add Entry
    </button>
  `;

  const entriesEl = document.getElementById('gs-entries');
  const existing = scale?.entriesJson || [];
  if (existing.length) {
    existing.forEach((e) => addGradeScaleEntryRow(entriesEl, e.value, e.operator, e.grade));
  } else {
    addGradeScaleEntryRow(entriesEl);
  }
  document.getElementById('gs-add-row').addEventListener('click', () => addGradeScaleEntryRow(entriesEl));

  const saveBtn = document.getElementById('admin-form-save');
  saveBtn.onclick = async () => {
    errorEl.classList.add('d-none');
    const name = document.getElementById('gs-name').value.trim();
    if (!name) { errorEl.textContent = 'Name is required.'; errorEl.classList.remove('d-none'); return; }

    const entriesJson = [];
    for (const row of entriesEl.querySelectorAll('.gs-entry-row')) {
      const inputs = row.querySelectorAll('input');
      const selects = row.querySelectorAll('select');
      const value = inputs[0].value.trim();
      const operator = selects[0].value;
      const grade = inputs[1].value.trim();
      if (!value && !grade) continue;
      if (!value || !grade) {
        errorEl.textContent = 'Each entry needs a numeric value and a grade label.';
        errorEl.classList.remove('d-none');
        return;
      }
      entriesJson.push({ value: Number(value), operator, grade });
    }

    try {
      const payload = { name, entriesJson };
      if (scale) {
        await api(`${API}grade-scales/${scale.id}/`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      } else {
        await api(`${API}grade-scales/`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      }
      modal.hide();
      renderGradeScalesSection();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
    }
  };

  modal.show();
}

// ---- App settings (singleton form, no table) ----

async function renderAppSettingsSection() {
  document.getElementById('admin-section-title').textContent = 'App Settings';
  document.getElementById('admin-create-btn').classList.add('d-none');
  const content = document.getElementById('admin-content');
  const settings = await api(API + 'app-settings/');
  content.innerHTML = `
    <form id="app-settings-form" style="max-width: 28rem;">
      <div class="mb-3">
        <label class="form-label">Theme</label>
        <select class="form-select" name="theme">
          <option value="dark" ${settings.theme === 'dark' ? 'selected' : ''}>Dark</option>
          <option value="light" ${settings.theme === 'light' ? 'selected' : ''}>Light</option>
        </select>
      </div>
      <div class="form-check mb-3">
        <input type="checkbox" class="form-check-input" name="soundEffectsEnabled" ${settings.soundEffectsEnabled ? 'checked' : ''}>
        <label class="form-check-label">Sound effects enabled</label>
      </div>
      <div class="mb-3">
        <label class="form-label">Max in-progress instances per user</label>
        <input type="number" class="form-control" name="maxInProgressInstances" value="${settings.maxInProgressInstances}">
      </div>
      <div id="app-settings-error" class="alert alert-danger d-none"></div>
      <button type="submit" class="btn btn-primary">Save</button>
    </form>
  `;
  document.getElementById('app-settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById('app-settings-error');
    errorEl.classList.add('d-none');
    const form = e.target;
    try {
      await api(API + 'app-settings/', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme: form.theme.value,
          soundEffectsEnabled: form.soundEffectsEnabled.checked,
          maxInProgressInstances: Number(form.maxInProgressInstances.value),
        }),
      });
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
    }
  });
}

// ---- Email settings (singleton form + live SMTP connection check + test send) ----

function setEmailConnectionStatus(state, detail) {
  const checkbox = document.getElementById('email-connected-indicator');
  const label = document.getElementById('email-connected-label');
  if (!checkbox) return;
  checkbox.checked = state === 'ok';
  label.textContent = state === 'ok' ? 'SMTP connected'
    : state === 'checking' ? 'Checking connection…'
    : `Not connected${detail ? `: ${detail}` : ''}`;
  label.className = state === 'ok' ? 'form-check-label text-success' : state === 'checking' ? 'form-check-label text-muted' : 'form-check-label text-danger';
}

async function checkEmailConnection() {
  setEmailConnectionStatus('checking');
  try {
    await api('/api/admin/email/test/', { method: 'POST' });
    setEmailConnectionStatus('ok');
  } catch (err) {
    setEmailConnectionStatus('fail', err.message);
  }
}

async function renderEmailSettingsSection() {
  document.getElementById('admin-section-title').textContent = 'Email Settings';
  document.getElementById('admin-create-btn').classList.add('d-none');
  const content = document.getElementById('admin-content');
  const settings = await api(API + 'email-settings/');
  content.innerHTML = `
    <form id="email-settings-form" style="max-width: 32rem;">
      <div class="d-flex align-items-center gap-2 mb-3">
        <input type="checkbox" class="form-check-input mt-0" id="email-connected-indicator" disabled>
        <label class="form-check-label" id="email-connected-label">Checking connection…</label>
        <button type="button" class="btn btn-outline-secondary btn-sm ms-auto" id="email-test-connection-btn">Test Connection</button>
      </div>
      <div class="mb-2">
        <label class="form-label">Host</label>
        <input type="text" class="form-control" name="host" value="${escapeHtml(settings.host)}">
      </div>
      <div class="mb-2">
        <label class="form-label">Port</label>
        <input type="number" class="form-control" name="port" value="${settings.port}">
      </div>
      <div class="form-check mb-2">
        <input type="checkbox" class="form-check-input" name="useTls" ${settings.useTls ? 'checked' : ''}>
        <label class="form-check-label">Use TLS (STARTTLS)</label>
      </div>
      <div class="form-check mb-2">
        <input type="checkbox" class="form-check-input" name="useSsl" ${settings.useSsl ? 'checked' : ''}>
        <label class="form-check-label">Use SSL</label>
      </div>
      <div class="mb-2">
        <label class="form-label">Username</label>
        <input type="text" class="form-control" name="username" value="${escapeHtml(settings.username)}">
      </div>
      <div class="mb-2">
        <label class="form-label">Password</label>
        <input type="password" class="form-control" name="password" placeholder="Leave blank to keep the current password" autocomplete="new-password">
      </div>
      <div class="mb-3">
        <label class="form-label">Default from address</label>
        <input type="text" class="form-control" name="defaultFromEmail" value="${escapeHtml(settings.defaultFromEmail)}">
      </div>
      <div id="email-settings-error" class="alert alert-danger d-none"></div>
      <button type="submit" class="btn btn-primary">Save</button>
    </form>
    <hr>
    <div style="max-width: 32rem;">
      <label class="form-label">Send a test email</label>
      <div class="input-group mb-2">
        <input type="email" class="form-control" id="email-test-recipient" placeholder="you@example.com">
        <button type="button" class="btn btn-outline-secondary" id="email-send-test-btn">Send Test Email</button>
      </div>
      <div id="email-send-test-result" class="small"></div>
    </div>
  `;

  document.getElementById('email-settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById('email-settings-error');
    errorEl.classList.add('d-none');
    const form = e.target;
    const payload = {
      host: form.host.value,
      port: Number(form.port.value),
      useTls: form.useTls.checked,
      useSsl: form.useSsl.checked,
      username: form.username.value,
      defaultFromEmail: form.defaultFromEmail.value,
    };
    if (form.password.value) payload.password = form.password.value;
    try {
      await api(API + 'email-settings/', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      checkEmailConnection();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
    }
  });

  document.getElementById('email-test-connection-btn').addEventListener('click', checkEmailConnection);

  document.getElementById('email-send-test-btn').addEventListener('click', async () => {
    const resultEl = document.getElementById('email-send-test-result');
    const to = document.getElementById('email-test-recipient').value.trim();
    resultEl.className = 'small text-muted';
    resultEl.textContent = 'Sending…';
    try {
      await api('/api/admin/email/send-test/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to }),
      });
      resultEl.className = 'small text-success';
      resultEl.textContent = `Sent to ${to}.`;
    } catch (err) {
      resultEl.className = 'small text-danger';
      resultEl.textContent = err.message;
    }
  });

  checkEmailConnection();
}

// ---- Groups/Roles (custom: nested RoleSettings + permissions checklist) ----

let permissionsCatalog = null;

async function renderGroupsSection() {
  document.getElementById('admin-section-title').textContent = 'Groups';
  const createBtn = document.getElementById('admin-create-btn');
  createBtn.classList.remove('d-none');
  createBtn.onclick = () => openGroupModal(null);

  const content = document.getElementById('admin-content');
  content.innerHTML = '<p class="text-muted small">Loading…</p>';
  const groups = await api(API + 'groups/');
  if (!groups.length) {
    content.innerHTML = '<p class="text-muted small mb-0">No groups yet.</p>';
    return;
  }
  content.innerHTML = `<div class="table-responsive"><table class="table table-sm align-middle">
    <thead><tr><th>Name</th><th>Permissions</th><th></th></tr></thead>
    <tbody>${groups.map((g) => `
      <tr data-id="${g.id}">
        <td>${escapeHtml(g.name)}</td>
        <td>${g.permissions.length}</td>
        <td class="text-end">
          <button class="btn btn-primary btn-sm me-1" data-action="edit"><i class="bi bi-pencil"></i></button>
          <button class="btn btn-danger btn-sm" data-action="delete"><i class="bi bi-trash"></i></button>
        </td>
      </tr>`).join('')}
    </tbody>
  </table></div>`;

  content.querySelectorAll('tr[data-id]').forEach((row) => {
    const id = Number(row.dataset.id);
    const group = groups.find((g) => g.id === id);
    row.querySelector('[data-action="edit"]').addEventListener('click', () => openGroupModal(group));
    row.querySelector('[data-action="delete"]').addEventListener('click', async () => {
      if (await confirmDelete(`Delete the "${group.name}" group?`)) {
        await api(`${API}groups/${id}/`, { method: 'DELETE' });
        await loadRefData();
        renderGroupsSection();
      }
    });
  });
}

async function openGroupModal(group) {
  if (!permissionsCatalog) {
    permissionsCatalog = await api(API + 'groups/permissions_catalog/');
  }
  const byApp = {};
  permissionsCatalog.forEach((p) => {
    (byApp[p.appLabel] = byApp[p.appLabel] || []).push(p);
  });
  const selected = new Set((group?.permissions || []));

  const modalEl = document.getElementById('admin-form-modal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const form = document.getElementById('admin-form');
  const errorEl = document.getElementById('admin-form-error');
  errorEl.classList.add('d-none');
  document.getElementById('admin-form-modal-title').textContent = group ? 'Edit Group' : 'Add Group';

  form.innerHTML = `
    <div class="mb-3">
      <label class="form-label">Name</label>
      <input type="text" class="form-control" name="name" value="${escapeHtml(group?.name || '')}" required>
    </div>
    <label class="form-label">Permissions</label>
    <div style="max-height: 16rem; overflow-y: auto;" class="border rounded p-2 mb-3">
      ${Object.entries(byApp).map(([appLabel, perms]) => `
        <div class="mb-2">
          <div class="text-muted small fw-bold">${escapeHtml(appLabel)}</div>
          ${perms.map((p) => `
            <div class="form-check">
              <input type="checkbox" class="form-check-input perm-checkbox" value="${p.id}" ${selected.has(p.id) ? 'checked' : ''}>
              <label class="form-check-label small">${escapeHtml(p.name)}</label>
            </div>
          `).join('')}
        </div>
      `).join('')}
    </div>
  `;

  const saveBtn = document.getElementById('admin-form-save');
  saveBtn.onclick = async () => {
    errorEl.classList.add('d-none');
    const permissionIds = Array.from(form.querySelectorAll('.perm-checkbox:checked')).map((el) => Number(el.value));
    const payload = {
      name: form.name.value,
      permissions: permissionIds,
    };
    try {
      if (group) {
        await api(`${API}groups/${group.id}/`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      } else {
        await api(API + 'groups/', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
      }
      await loadRefData();
      modal.hide();
      renderGroupsSection();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('d-none');
    }
  };

  modal.show();
}

// ---- API Token (everyone - the only section visible to non-staff users) ----

async function renderApiTokenSection() {
  document.getElementById('admin-section-title').textContent = 'API Token';
  document.getElementById('admin-create-btn').classList.add('d-none');
  const content = document.getElementById('admin-content');
  content.innerHTML = '<p class="text-muted small">Loading…</p>';
  const { token } = await api('/api/account/token/');
  content.innerHTML = `
    <p class="text-muted small">Send as <code>Authorization: Token &lt;token&gt;</code>. See <a href="/api/docs/" target="_blank" rel="noopener">API docs</a>.</p>
    <div class="input-group mb-3" style="max-width: 36rem;">
      <input type="password" class="form-control font-monospace" id="api-token-value" value="${escapeHtml(token)}" readonly>
      <button class="btn btn-outline-secondary" type="button" id="api-token-reveal" title="Show/hide token"><i class="bi bi-eye"></i></button>
      <button class="btn btn-outline-secondary" type="button" id="api-token-copy" title="Copy"><i class="bi bi-clipboard"></i></button>
    </div>
    <button class="btn btn-outline-danger btn-sm" id="api-token-regenerate">Regenerate token</button>
  `;
  const tokenInput = document.getElementById('api-token-value');
  document.getElementById('api-token-reveal').addEventListener('click', (e) => {
    const show = tokenInput.type === 'password';
    tokenInput.type = show ? 'text' : 'password';
    e.currentTarget.querySelector('i').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
  });
  document.getElementById('api-token-copy').addEventListener('click', () => {
    navigator.clipboard.writeText(token);
  });
  document.getElementById('api-token-regenerate').addEventListener('click', async () => {
    await api('/api/account/token/', { method: 'POST' });
    renderApiTokenSection();
  });
}

// ---- Init ----

document.querySelectorAll('#admin-tabs button').forEach((btn) => {
  btn.addEventListener('click', () => renderSection(btn.dataset.section));
});

let _who = { isStaff: false, canCreateExam: false };

async function initManage() {
  try {
    _who = await api(API + 'whoami/');
  } catch (err) {
    // Treat as a plain user — only the My Account/API Token section applies.
  }
  document.getElementById('manage-group-staff').classList.toggle('d-none', !_who.isStaff);
  document.getElementById('manage-group-editor').classList.toggle('d-none', _who.isStaff || !_who.canCreateExam);
  await loadRefData();
  renderSection(_who.isStaff || _who.canCreateExam ? 'attempts' : 'apiToken');
}

initManage();
