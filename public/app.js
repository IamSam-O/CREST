const views = {
  library: document.getElementById('view-library'),
  setup: document.getElementById('view-setup'),
  take: document.getElementById('view-take'),
  results: document.getElementById('view-results'),
  history: document.getElementById('view-history'),
  editExam: document.getElementById('view-edit-exam'),
  questionEditor: document.getElementById('view-question-editor'),
};

function showView(name) {
  Object.values(views).forEach((v) => v.classList.add('d-none'));
  views[name].classList.remove('d-none');
}

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
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// Themed replacement for confirm() — used by every destructive/confirm action
// in the app so popups are consistent with the page's theme instead of native browser dialogs.
function confirmAction(message, { title = 'Confirm', confirmLabel = 'Confirm', confirmClass = 'btn-outline-danger' } = {}) {
  return new Promise((resolve) => {
    const modalEl = document.getElementById('confirm-modal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const confirmBtn = document.getElementById('confirm-modal-confirm');

    document.getElementById('confirm-modal-title').innerHTML =
      `<i class="bi bi-exclamation-triangle-fill me-2"></i>${escapeHtml(title)}`;
    document.getElementById('confirm-modal-body').textContent = message;
    confirmBtn.textContent = confirmLabel;
    confirmBtn.className = `btn ${confirmClass}`;

    function cleanup() {
      confirmBtn.removeEventListener('click', onConfirm);
      modalEl.removeEventListener('hidden.bs.modal', onHidden);
    }
    function onConfirm() {
      cleanup();
      resolve(true);
      modal.hide();
    }
    function onHidden() {
      cleanup();
      resolve(false);
    }

    confirmBtn.addEventListener('click', onConfirm);
    modalEl.addEventListener('hidden.bs.modal', onHidden);
    modal.show();
  });
}

document.getElementById('nav-back-library').addEventListener('click', async () => {
  const inExam = takeState && !views.take.classList.contains('d-none');
  if (inExam) {
    const leave = await confirmAction('You are in the middle of an exam. Your progress will be saved so you can resume later.', { title: 'Leave exam?', confirmLabel: 'Leave Exam' });
    if (!leave) return;
    pauseBonusTracking();
    await saveProgress();
  }
  showView('library');
  loadLibrary();
});

// Tab backgrounded/minimized counts as "not actively in progress" too — pause and resume
// the bonus window around visibility changes instead of letting it decay in the background.
document.addEventListener('visibilitychange', () => {
  if (!takeState || views.take.classList.contains('d-none')) return;
  if (document.hidden) {
    pauseBonusTracking();
    saveProgress();
  } else {
    resumeBonusTracking();
  }
});

// ---------- In-progress exam persistence (server-side resume support) ----------

async function saveProgress() {
  if (!takeState) return;
  const payload = {
    questions: takeState.questions,
    answers: Array.from(takeState.answers.entries()).map(([qId, set]) => [qId, Array.from(set)]),
    checked: Array.from(takeState.checked.entries()),
    elapsedSeconds: Array.from(takeState.elapsedSeconds.entries()),
    index: takeState.index,
    startedAt: takeState.startedAt,
    multiplier: takeState.multiplier,
  };
  try {
    await api(`/api/exams/${takeState.examId}/progress`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    // non-critical background save — ignore transient failures
  }
}

async function clearProgress(examId) {
  try {
    await api(`/api/exams/${examId}/progress`, { method: 'DELETE' });
  } catch (err) {
    // ignore
  }
}

async function resumeExam(exam) {
  const saved = await api(`/api/exams/${exam.id}/progress`);
  takeState = {
    examId: saved.examId,
    examName: exam.name,
    bonusWindowSeconds: saved.bonusWindowSeconds,
    questions: saved.questions,
    answers: new Map(saved.answers.map(([qId, arr]) => [qId, new Set(arr)])),
    checked: new Map(saved.checked),
    elapsedSeconds: new Map(saved.elapsedSeconds || []),
    activeSince: null,
    index: saved.index,
    startedAt: saved.startedAt,
    bonusMeterInterval: null,
    multiplier: saved.multiplier,
  };

  showView('take');
  renderQuestion();
}

// ---------- Library ----------

let allExams = [];

async function loadLibrary() {
  allExams = await api('/api/exams');
  document.getElementById('exam-search-input').value = '';
  renderInstanceList(allExams);
  renderExamList(allExams, 'No exams yet. Import a CSV above to get started.');
}

function renderInstanceList(exams) {
  const card = document.getElementById('instances-card');
  const list = document.getElementById('instance-list');
  const inProgress = exams.filter(
    (exam) => exam.progressIndex !== null && exam.progressIndex !== undefined
  );

  if (inProgress.length === 0) {
    card.classList.add('d-none');
    list.innerHTML = '';
    return;
  }
  card.classList.remove('d-none');
  list.innerHTML = '';

  inProgress.forEach((exam) => {
    const item = document.createElement('div');
    item.className = 'entry-card d-flex justify-content-between align-items-center flex-wrap gap-2';

    const meta = document.createElement('div');
    meta.className = 'entry-meta';
    const scoreLine =
      exam.progressNumChecked > 0
        ? `${exam.progressNumCorrect}/${exam.progressNumChecked} correct so far · ${exam.progressPointsEarned} pts`
        : 'Not answered yet';
    meta.innerHTML = `<strong>${escapeHtml(exam.name)}</strong><span class="text-muted small">Question ${exam.progressIndex + 1} of ${exam.progressTotal} · ${scoreLine}</span>`;

    const actions = document.createElement('div');
    actions.className = 'd-flex gap-2 flex-wrap';

    const resumeBtn = document.createElement('button');
    resumeBtn.className = 'btn btn-warning btn-sm';
    resumeBtn.innerHTML = '<i class="bi bi-play-circle me-1"></i>Resume';
    resumeBtn.onclick = () => resumeExam(exam);

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-danger btn-sm';
    deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
    deleteBtn.title = 'Discard this in-progress attempt';
    deleteBtn.onclick = () => deleteInstance(exam);

    actions.append(resumeBtn, deleteBtn);
    item.append(meta, actions);
    list.appendChild(item);
  });
}

async function deleteInstance(exam) {
  const ok = await confirmAction(`Discard your in-progress attempt on "${exam.name}"? This cannot be undone.`, {
    title: 'Discard in-progress attempt?',
    confirmLabel: 'Discard',
  });
  if (!ok) return;
  await clearProgress(exam.id);
  loadLibrary();
}

document.getElementById('exam-search-input').addEventListener('input', (e) => {
  const q = e.target.value.trim().toLowerCase();
  if (!q) {
    renderExamList(allExams, 'No exams yet. Import a CSV above to get started.');
    return;
  }
  const filtered = allExams.filter((exam) => {
    const name = exam.name.toLowerCase();
    const keywords = (exam.keywords || '').toLowerCase();
    return name.includes(q) || keywords.includes(q);
  });
  renderExamList(filtered, 'No exams match your search.');
});

function renderExamList(exams, emptyMessage) {
  const list = document.getElementById('exam-list');
  list.innerHTML = '';
  if (exams.length === 0) {
    list.innerHTML = `<p class="text-muted mb-0">${emptyMessage}</p>`;
    return;
  }
  for (const exam of exams) {
    const item = document.createElement('div');
    item.className = 'entry-card d-flex justify-content-between align-items-center flex-wrap gap-2';

    const meta = document.createElement('div');
    meta.className = 'entry-meta';
    const hasProgress = exam.progressIndex !== null && exam.progressIndex !== undefined;

    const scoreLine =
      exam.lastScore === null || exam.lastScore === undefined
        ? 'No attempts yet'
        : `Last score: ${exam.lastScore}/${exam.lastTotal} · ${exam.lastPointsEarned} pts earned · ${exam.attemptCount} attempt(s)`;
    meta.innerHTML = `<strong>${escapeHtml(exam.name)}</strong><span class="text-muted small">${exam.questionCount} questions · ${scoreLine}</span>`;

    const actions = document.createElement('div');
    actions.className = 'd-flex gap-2 flex-wrap';

    const practiceBtn = document.createElement('button');
    practiceBtn.className = 'btn btn-primary btn-sm';
    practiceBtn.innerHTML = `<i class="bi bi-play-fill me-1"></i>${hasProgress ? 'New Attempt' : 'Practice'}`;
    practiceBtn.onclick = () => openSetup(exam);

    const historyBtn = document.createElement('button');
    historyBtn.className = 'btn btn-outline-secondary btn-sm';
    historyBtn.innerHTML = '<i class="bi bi-clock-history"></i>';
    historyBtn.title = 'Attempt history';
    historyBtn.onclick = () => openHistory(exam);

    actions.append(practiceBtn);
    if (exam.canEdit) {
      const editBtn = document.createElement('button');
      editBtn.className = 'btn btn-primary btn-sm';
      editBtn.innerHTML = '<i class="bi bi-pencil"></i>';
      editBtn.title = 'Edit questions';
      editBtn.onclick = () => openEditExam(exam);
      actions.append(editBtn);
    }
    actions.append(historyBtn);
    item.append(meta, actions);
    list.appendChild(item);
  }
}

async function deleteExam(exam) {
  const ok = await confirmAction(`Delete "${exam.name}" and all its attempt history? This cannot be undone.`, {
    title: 'Delete exam?',
    confirmLabel: 'Delete',
  });
  if (!ok) return;
  await api(`/api/exams/${exam.id}`, { method: 'DELETE' });
  showView('library');
  loadLibrary();
}

document.getElementById('create-exam-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const status = document.getElementById('create-exam-status');
  const fileInput = document.getElementById('exam-file-input');
  const nameInput = document.getElementById('exam-name-input');
  const groupInput = document.getElementById('exam-group-input');
  if (!fileInput.files[0]) return;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  if (nameInput.value.trim()) formData.append('name', nameInput.value.trim());
  Array.from(groupInput.selectedOptions).forEach((o) => formData.append('group_ids', o.value));

  status.textContent = 'Importing...';
  status.className = 'status text-muted';
  try {
    const result = await api('/api/exams', { method: 'POST', body: formData });
    status.textContent = `Imported ${result.questionCount} questions.`;
    status.className = 'status text-success';
    e.target.reset();
    loadLibrary();
  } catch (err) {
    status.textContent = err.message;
    status.className = 'status text-danger';
  }
});

// ---------- Setup ----------

let currentExam = null;

function openSetup(exam) {
  currentExam = exam;
  document.getElementById('setup-exam-name').textContent = exam.name;
  document.getElementById('setup-question-count-label').textContent = `${exam.questionCount} questions available.`;
  const customInput = document.getElementById('custom-count-input');
  customInput.max = exam.questionCount;
  customInput.value = exam.questionCount;
  document.getElementById('count-mode-all').checked = true;
  customInput.disabled = true;
  showView('setup');
}

document.querySelectorAll('input[name="count-mode"]').forEach((radio) => {
  radio.addEventListener('change', () => {
    document.getElementById('custom-count-input').disabled =
      document.querySelector('input[name="count-mode"]:checked').value !== 'custom';
  });
});

document.getElementById('setup-cancel').addEventListener('click', () => {
  showView('library');
});

document.getElementById('setup-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const status = document.getElementById('setup-status');
  status.textContent = '';
  const mode = document.querySelector('input[name="count-mode"]:checked').value;
  const count = mode === 'all' ? 'all' : parseInt(document.getElementById('custom-count-input').value, 10);
  try {
    await startExam(currentExam, { count });
  } catch (err) {
    status.textContent = err.message;
    status.className = 'status text-danger';
  }
});

// ---------- Groups (exam visibility) ----------

let allGroups = [];

function renderGroupOptions(selectEl, selectedIds) {
  const selected = new Set((selectedIds || []).map(String));
  selectEl.innerHTML = allGroups
    .map((g) => `<option value="${g.id}" ${selected.has(String(g.id)) ? 'selected' : ''}>${escapeHtml(g.name)}</option>`)
    .join('');
}

async function loadGroups() {
  try {
    allGroups = await api('/api/groups');
  } catch (err) {
    allGroups = [];
  }
  renderGroupOptions(document.getElementById('exam-group-input'));
}

// ---------- Grade Scales ----------

let allGradeScales = [];

function renderGradeScaleOptions(selectEl, selectedId) {
  const blank = '<option value="">— None —</option>';
  selectEl.innerHTML = blank + allGradeScales
    .map((s) => `<option value="${s.id}" ${String(s.id) === String(selectedId) ? 'selected' : ''}>${escapeHtml(s.name)}</option>`)
    .join('');
}

async function loadGradeScales() {
  try {
    allGradeScales = await api('/api/grade-scales');
  } catch (_) {
    allGradeScales = [];
  }
}

// ---------- Settings ----------

let appSettings = { soundEffectsEnabled: false, theme: 'dark', maxInProgressInstances: 5 };

function applyTheme(theme) {
  document.body.classList.toggle('theme-light', theme === 'light');
  const icon = document.querySelector('#nav-theme-toggle i');
  icon.className = theme === 'light' ? 'bi bi-moon-stars-fill' : 'bi bi-sun-fill';
}

async function loadSettings() {
  try {
    appSettings = await api('/api/settings');
  } catch (err) {
    // keep defaults
  }
  applyTheme(appSettings.theme);
}

let audioCtx = null;
function playTone(freq, duration) {
  if (!appSettings.soundEffectsEnabled) return;
  audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.frequency.value = freq;
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
  osc.start();
  osc.stop(audioCtx.currentTime + duration);
}
function playResultSound(isCorrect) {
  playTone(isCorrect ? 880 : 220, isCorrect ? 0.18 : 0.3);
}

document.getElementById('nav-theme-toggle').addEventListener('click', async () => {
  const previousTheme = appSettings.theme;
  const newTheme = previousTheme === 'light' ? 'dark' : 'light';
  appSettings.theme = newTheme;
  applyTheme(newTheme);
  try {
    appSettings = await api('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        soundEffectsEnabled: appSettings.soundEffectsEnabled,
        theme: newTheme,
        maxInProgressInstances: appSettings.maxInProgressInstances,
      }),
    });
    applyTheme(appSettings.theme);
  } catch (err) {
    appSettings.theme = previousTheme;
    applyTheme(previousTheme);
  }
});

// ---------- Take exam ----------

const MULTIPLIER_MAX = 30;
const TILE_COLOR_COUNT = 6;

let takeState = null;

async function startExam(exam, options) {
  const data = await api(`/api/exams/${exam.id}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  });

  takeState = {
    examId: data.examId,
    examName: data.examName,
    bonusWindowSeconds: data.bonusWindowSeconds,
    questions: data.questions,
    answers: new Map(),
    checked: new Map(),
    elapsedSeconds: new Map(),
    activeSince: null,
    index: 0,
    startedAt: new Date().toISOString(),
    bonusMeterInterval: null,
    multiplier: 1,
  };

  showView('take');
  renderQuestion();
}

// Correct answers within the 30s bonus window earn extra points (more the faster you answer).
// Once the window closes only the question's standard points apply. A correct-answer streak
// builds a multiplier (up to 30x) that is reset back to 1x by any incorrect answer.
function computeAwardedPoints(question, isCorrect, elapsedSeconds) {
  if (!isCorrect) return 0;
  const base = question.points;
  const bonusWindow = takeState.bonusWindowSeconds;
  const withinBonusWindow = elapsedSeconds < bonusWindow;
  const bonusFraction = withinBonusWindow ? Math.max(0, (bonusWindow - elapsedSeconds) / bonusWindow) : 0;
  const bonus = Math.round(base * bonusFraction);
  return (base + bonus) * takeState.multiplier;
}

// Active time spent actually viewing/answering a question, excluding any time spent
// away from the Take Exam screen (navigated elsewhere, tab backgrounded, or closed).
function currentElapsedSeconds(questionId) {
  const committed = takeState.elapsedSeconds.get(questionId) || 0;
  const live = takeState.activeSince ? (Date.now() - takeState.activeSince) / 1000 : 0;
  return committed + live;
}

function recordCheckedResult(question, result) {
  const elapsedSeconds = currentElapsedSeconds(question.id);
  const pointsAwarded = computeAwardedPoints(question, result.isCorrect, elapsedSeconds);
  takeState.checked.set(question.id, { ...result, pointsAwarded });
  takeState.multiplier = result.isCorrect ? Math.min(MULTIPLIER_MAX, takeState.multiplier + 1) : 1;
  takeState.activeSince = null;
}

function renderQuestion() {
  const q = takeState.questions[takeState.index];
  const total = takeState.questions.length;
  document.getElementById('take-progress').textContent = `Question ${takeState.index + 1} of ${total}`;
  document.getElementById('take-progress-bar').style.width = `${Math.round(((takeState.index + 1) / total) * 100)}%`;
  document.getElementById('take-question-text').innerHTML = DOMPurify.sanitize(q.questionText);

  const img = document.getElementById('take-image');
  if (q.imageLink) {
    img.src = q.imageLink;
    img.classList.remove('d-none');
  } else {
    img.classList.add('d-none');
  }

  const selectHint = document.getElementById('take-select-hint');
  selectHint.textContent = `Select ${q.selectCount} answer${q.selectCount === 1 ? '' : 's'}`;
  selectHint.classList.remove('d-none');

  const checkedResult = takeState.checked.get(q.id);

  renderOptionsUI();

  document.getElementById('take-next').disabled = takeState.index === total - 1 || !checkedResult;

  updatePointsDisplay();

  if (checkedResult) {
    clearBonusMeter();
    updateBonusMeterDisplay(0);
  } else {
    resumeBonusTracking();
  }
}

function renderOptionsUI() {
  const q = takeState.questions[takeState.index];
  const selected = takeState.answers.get(q.id) || new Set();
  const checkedResult = takeState.checked.get(q.id);

  const optionsList = document.getElementById('take-options');
  optionsList.innerHTML = '';
  optionsList.style.gridTemplateColumns = `repeat(${q.options.length}, 1fr)`;
  q.options.forEach((opt, idx) => {
    const tile = document.createElement('button');
    tile.type = 'button';
    tile.className = `answer-tile tile-color-${idx % TILE_COLOR_COUNT}`;
    tile.disabled = !!checkedResult;

    const label = document.createElement('div');
    label.className = 'answer-tile-label';
    label.innerHTML = DOMPurify.sanitize(opt.text);
    tile.appendChild(label);

    if (checkedResult) {
      if (checkedResult.correctOptionIds.includes(opt.id)) tile.classList.add('correct');
      else if (selected.has(opt.id)) tile.classList.add('incorrect-selected');
    } else if (selected.has(opt.id)) {
      tile.classList.add('selected');
    }

    tile.addEventListener('click', () => {
      if (takeState.checked.get(q.id)) return;
      handleOptionChange(q, opt, !selected.has(opt.id));
      renderOptionsUI();
    });

    optionsList.appendChild(tile);
  });

  const tmp = document.createElement('div');
  const maxLen = q.options.reduce((max, opt) => {
    tmp.innerHTML = DOMPurify.sanitize(opt.text);
    return Math.max(max, tmp.textContent.length);
  }, 0);
  const scale = Math.max(0, Math.min(1, (maxLen - 50) / 130));
  optionsList.style.setProperty('--tile-font-scale', scale.toFixed(3));

  const feedback = document.getElementById('take-feedback');
  const checkBtn = document.getElementById('take-check');
  if (checkedResult) {
    feedback.classList.remove('d-none', 'correct', 'incorrect');
    feedback.classList.add(checkedResult.isCorrect ? 'correct' : 'incorrect');
    const pointsText = checkedResult.isCorrect ? ` (+${checkedResult.pointsAwarded} pts)` : '';
    feedback.textContent = checkedResult.isCorrect ? `Correct!${pointsText}` : 'Incorrect.';
    if (checkedResult.explanation) {
      feedback.insertAdjacentHTML('beforeend', ' ' + DOMPurify.sanitize(checkedResult.explanation));
    }
    checkBtn.classList.add('d-none');
  } else {
    feedback.classList.add('d-none');
    checkBtn.classList.remove('d-none');
    checkBtn.disabled = selected.size === 0;
  }

  saveProgress();
}

function updatePointsDisplay() {
  let totalAwarded = 0;
  takeState.checked.forEach((result) => {
    totalAwarded += result.pointsAwarded || 0;
  });
  document.getElementById('take-points').innerHTML = `<i class="bi bi-star-fill me-1"></i>${totalAwarded} pts`;
  document.getElementById('take-multiplier').innerHTML = `<i class="bi bi-fire me-1"></i>${takeState.multiplier}x`;
}

function clearBonusMeter() {
  if (takeState && takeState.bonusMeterInterval) {
    clearInterval(takeState.bonusMeterInterval);
    takeState.bonusMeterInterval = null;
  }
}

function updateBonusMeterDisplay(remainingSeconds) {
  const pct = Math.max(0, Math.min(100, (remainingSeconds / takeState.bonusWindowSeconds) * 100));
  const bar = document.getElementById('take-bonus-bar');
  bar.style.width = `${pct}%`;
  bar.classList.toggle('bg-danger', remainingSeconds <= 5);
}

// Purely visual — shows how much of the bonus window is left. Does not lock the question
// or advance it; you can still answer any time, just without the bonus. Only counts down
// while actively tracking (see pauseBonusTracking/resumeBonusTracking) so time spent away
// from the Take Exam screen doesn't burn down the bonus window.
function startBonusMeter() {
  clearBonusMeter();
  const q = takeState.questions[takeState.index];
  updateBonusMeterDisplay(Math.max(0, takeState.bonusWindowSeconds - currentElapsedSeconds(q.id)));
  takeState.bonusMeterInterval = setInterval(() => {
    const remaining = Math.max(0, takeState.bonusWindowSeconds - currentElapsedSeconds(q.id));
    updateBonusMeterDisplay(remaining);
    if (remaining <= 0) clearBonusMeter();
  }, 200);
}

// Commits the live elapsed time for the current question into the persisted total and
// stops the countdown — called whenever the user leaves the Take Exam screen.
function pauseBonusTracking() {
  if (!takeState) return;
  if (takeState.activeSince) {
    const q = takeState.questions[takeState.index];
    if (q && !takeState.checked.has(q.id)) {
      const committed = takeState.elapsedSeconds.get(q.id) || 0;
      takeState.elapsedSeconds.set(q.id, committed + (Date.now() - takeState.activeSince) / 1000);
    }
    takeState.activeSince = null;
  }
  clearBonusMeter();
}

// Starts a fresh active-viewing burst for the current question and resumes the countdown
// from its previously committed elapsed time (not from a full bonus window).
function resumeBonusTracking() {
  if (!takeState) return;
  const q = takeState.questions[takeState.index];
  if (!q || takeState.checked.has(q.id)) return;
  takeState.activeSince = Date.now();
  startBonusMeter();
}

function handleOptionChange(question, option, checked) {
  if (!takeState.answers.has(question.id)) takeState.answers.set(question.id, new Set());
  const set = takeState.answers.get(question.id);
  if (question.questionType === 'multi') {
    if (checked) set.add(option.id);
    else set.delete(option.id);
  } else {
    set.clear();
    if (checked) set.add(option.id);
  }
}

document.getElementById('take-check').addEventListener('click', async () => {
  const q = takeState.questions[takeState.index];
  const selectedIds = Array.from(takeState.answers.get(q.id) || []);
  const result = await api(`/api/questions/${q.id}/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selectedOptionIds: selectedIds }),
  });
  recordCheckedResult(q, result);
  playResultSound(result.isCorrect);
  renderQuestion();
});

document.addEventListener('keydown', (e) => {
  if (!takeState || views.take.classList.contains('d-none')) return;

  if (e.key === 'Enter') {
    const checkBtn = document.getElementById('take-check');
    if (!checkBtn.classList.contains('d-none') && !checkBtn.disabled) {
      e.preventDefault();
      checkBtn.click();
    }
    return;
  }

  if (e.key === 'ArrowRight') {
    const nextBtn = document.getElementById('take-next');
    if (!nextBtn.disabled) {
      e.preventDefault();
      nextBtn.click();
    }
    return;
  }

  if (!/^[1-6]$/.test(e.key)) return;
  const q = takeState.questions[takeState.index];
  if (takeState.checked.get(q.id)) return;
  const tiles = document.querySelectorAll('#take-options .answer-tile');
  const idx = parseInt(e.key, 10) - 1;
  if (tiles[idx]) {
    e.preventDefault();
    tiles[idx].click();
  }
});

document.getElementById('take-next').addEventListener('click', () => {
  if (takeState.index < takeState.questions.length - 1) {
    takeState.index += 1;
    renderQuestion();
  }
});

document.getElementById('take-finish').addEventListener('click', async () => {
  const unanswered = takeState.questions.filter((q) => !(takeState.answers.get(q.id) || new Set()).size).length;
  if (unanswered > 0) {
    const ok = await confirmAction(`${unanswered} question(s) unanswered. Finish anyway?`, {
      title: 'Finish exam?',
      confirmLabel: 'Finish',
      confirmClass: 'btn-primary',
    });
    if (!ok) return;
  }

  clearBonusMeter();

  const answers = takeState.questions.map((q) => {
    const checkedResult = takeState.checked.get(q.id);
    return {
      questionId: q.id,
      selectedOptionIds: Array.from(takeState.answers.get(q.id) || []),
      pointsAwarded: checkedResult ? checkedResult.pointsAwarded : undefined,
    };
  });

  const result = await api(`/api/exams/${takeState.examId}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers, startedAt: takeState.startedAt }),
  });

  await clearProgress(takeState.examId);
  renderResults(takeState.examId, result.examName, result.numCorrect, result.numQuestions, result.pointsEarned, result.totalPoints, result.results, 'library', result.grade);
});

// ---------- Results ----------

let resultsReturnTo = 'library';

function renderResults(examId, examName, numCorrect, numQuestions, pointsEarned, totalPoints, results, returnTo = 'library', grade = null) {
  resultsReturnTo = returnTo;
  document.getElementById('results-back').textContent = returnTo === 'history' ? 'Back to History' : 'Back to Library';

  document.getElementById('results-summary').textContent =
    `${examName} — ${numCorrect}/${numQuestions} correct (${Math.round((numCorrect / numQuestions) * 100)}%) · ${pointsEarned} pts earned (standard max ${totalPoints})`;

  const gradeEl = document.getElementById('results-grade');
  if (grade) {
    gradeEl.textContent = grade;
    gradeEl.classList.remove('d-none');
  } else {
    gradeEl.classList.add('d-none');
  }

  const retakeWrap = document.getElementById('results-retake-wrap');
  const retakeStatus = document.getElementById('results-retake-status');
  retakeStatus.textContent = '';
  const missedIds = results.filter((r) => !r.isCorrect).map((r) => r.questionId);
  if (missedIds.length > 0) {
    retakeWrap.classList.remove('d-none');
    document.getElementById('results-retake-btn').onclick = () => retakeMissedQuestions(examId, missedIds);
  } else {
    retakeWrap.classList.add('d-none');
  }

  const list = document.getElementById('results-list');
  list.innerHTML = '';
  results.forEach((r, idx) => {
    const item = document.createElement('div');
    item.className = `card mb-3 border-${r.isCorrect ? 'success' : 'danger'}`;

    const body = document.createElement('div');
    body.className = 'card-body';

    const title = document.createElement('h3');
    title.className = 'h6 d-flex justify-content-between gap-2';
    const pointsLabel = document.createElement('span');
    pointsLabel.className = `points-badge ${r.isCorrect ? 'bg-success' : 'bg-secondary'} flex-shrink-0`;
    pointsLabel.textContent = `+${r.pointsAwarded || 0} pts`;
    title.innerHTML = `<span>${idx + 1}. ${DOMPurify.sanitize(r.questionText)}</span>`;
    title.appendChild(pointsLabel);
    body.appendChild(title);

    if (r.imageLink) {
      const img = document.createElement('img');
      img.src = r.imageLink;
      img.className = 'img-fluid rounded mb-2 question-image';
      body.appendChild(img);
    }

    const optionsWrap = document.createElement('div');
    optionsWrap.className = 'list-group mb-2';
    r.options.forEach((opt) => {
      const wasSelected = r.selectedOptionIds.includes(opt.id);
      let cls = 'list-group-item';
      if (opt.isCorrect) cls += ' list-group-item-success';
      else if (wasSelected) cls += ' list-group-item-danger';
      const optDiv = document.createElement('div');
      optDiv.className = cls;
      optDiv.innerHTML = `${wasSelected ? '☑' : '☐'} ` + DOMPurify.sanitize(opt.text);
      optionsWrap.appendChild(optDiv);
    });
    body.appendChild(optionsWrap);

    if (r.explanation) {
      const exp = document.createElement('p');
      exp.className = 'text-muted small mb-0';
      exp.innerHTML = DOMPurify.sanitize(r.explanation);
      body.appendChild(exp);
    }

    item.appendChild(body);
    list.appendChild(item);
  });

  showView('results');
}

document.getElementById('results-back').addEventListener('click', () => {
  if (resultsReturnTo === 'history' && currentExam) {
    openHistory(currentExam);
  } else {
    showView('library');
    loadLibrary();
  }
});

async function retakeMissedQuestions(examId, questionIds) {
  const status = document.getElementById('results-retake-status');
  status.textContent = '';
  try {
    await startExam({ id: examId }, { questionIds });
  } catch (err) {
    status.textContent = err.message;
    status.className = 'status text-danger';
  }
}

// ---------- History ----------

async function openHistory(exam) {
  currentExam = exam;
  document.getElementById('history-exam-name').textContent = `${exam.name} — Attempt History`;
  const attempts = await api(`/api/exams/${exam.id}/attempts`);
  const list = document.getElementById('history-list');
  list.innerHTML = '';
  if (attempts.length === 0) {
    list.innerHTML = '<p class="text-muted mb-0">No attempts yet.</p>';
  } else {
    attempts.forEach((a) => {
      const item = document.createElement('div');
      item.className = 'entry-card clickable d-flex justify-content-between align-items-center';
      const pct = Math.round((a.numCorrect / a.numQuestions) * 100);
      item.innerHTML = `<span>${new Date(a.finishedAt).toLocaleString()}</span><span class="d-flex gap-2"><span class="badge bg-${pct >= 70 ? 'success' : 'danger'}">${a.numCorrect}/${a.numQuestions} (${pct}%)</span><span class="badge bg-warning text-dark">${a.pointsEarned} pts</span></span>`;
      item.addEventListener('click', () => openAttemptDetail(a.id));
      list.appendChild(item);
    });
  }
  showView('history');
}

async function openAttemptDetail(attemptId) {
  const attempt = await api(`/api/attempts/${attemptId}`);
  renderResults(
    currentExam.id,
    currentExam.name,
    attempt.numCorrect,
    attempt.numQuestions,
    attempt.pointsEarned,
    attempt.totalPoints,
    attempt.results,
    'history',
    attempt.grade,
  );
}

document.getElementById('history-back').addEventListener('click', () => {
  showView('library');
  loadLibrary();
});

// ---------- Edit exam (question list) ----------

let editingQuestions = [];
let editingQuestionId = null;
let editingCanEdit = true;

async function openEditExam(exam) {
  currentExam = exam;
  document.getElementById('edit-exam-name').textContent = `${exam.name} — Edit Questions`;
  document.getElementById('edit-export-link').href = `/api/exams/${exam.id}/export`;
  document.getElementById('edit-bulk-status').textContent = '';
  await loadGradeScales();
  await loadEditQuestions();
  showView('editExam');
}

document.getElementById('edit-bulk-upload-input').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const ok = await confirmAction(
    'This will replace all current questions in this exam with the contents of the CSV. Past attempt scores are kept, but detailed answer review for past attempts may be lost. Continue?',
    { title: 'Replace all questions?', confirmLabel: 'Replace' }
  );
  if (!ok) {
    e.target.value = '';
    return;
  }

  const status = document.getElementById('edit-bulk-status');
  const formData = new FormData();
  formData.append('file', file);
  status.textContent = 'Updating...';
  status.className = 'status text-muted';
  try {
    const result = await api(`/api/exams/${currentExam.id}/import`, { method: 'PUT', body: formData });
    status.textContent = `Updated — now ${result.questionCount} questions.`;
    status.className = 'status text-success';
    await loadEditQuestions();
  } catch (err) {
    status.textContent = err.message;
    status.className = 'status text-danger';
  }
  e.target.value = '';
});

function setEditExamControlsEnabled(canEdit) {
  ['edit-save-exam-settings', 'edit-add-question', 'edit-delete-exam'].forEach((id) => {
    document.getElementById(id).classList.toggle('d-none', !canEdit);
  });
  document.getElementById('edit-bonus-window').disabled = !canEdit;
  document.getElementById('edit-keywords').disabled = !canEdit;
  document.getElementById('edit-group-input').disabled = !canEdit;
  document.getElementById('edit-grade-scale-input').disabled = !canEdit;
  document.getElementById('edit-bulk-upload-input').disabled = !canEdit;
}

async function loadEditQuestions() {
  const data = await api(`/api/exams/${currentExam.id}/questions`);
  editingQuestions = data.questions;
  editingCanEdit = data.canEdit;
  document.getElementById('edit-bonus-window').value = data.bonusWindowSeconds;
  document.getElementById('edit-keywords').value = data.keywords || '';
  renderGroupOptions(document.getElementById('edit-group-input'), data.allowedGroupIds);
  renderGradeScaleOptions(document.getElementById('edit-grade-scale-input'), data.gradeScaleId);
  setEditExamControlsEnabled(editingCanEdit);
  renderEditQuestionList();
}

document.getElementById('edit-save-exam-settings').addEventListener('click', async () => {
  const status = document.getElementById('edit-exam-settings-status');
  const bonusWindowSeconds = parseInt(document.getElementById('edit-bonus-window').value, 10);
  const keywords = document.getElementById('edit-keywords').value.trim();
  const allowedGroupIds = Array.from(document.getElementById('edit-group-input').selectedOptions).map((o) => Number(o.value));
  const gradeScaleRaw = document.getElementById('edit-grade-scale-input').value;
  const gradeScaleId = gradeScaleRaw ? Number(gradeScaleRaw) : null;
  try {
    const result = await api(`/api/exams/${currentExam.id}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bonusWindowSeconds, keywords, allowedGroupIds, gradeScaleId }),
    });
    currentExam.keywords = result.keywords;
    status.textContent = 'Saved.';
    status.className = 'status text-success';
  } catch (err) {
    status.textContent = err.message;
    status.className = 'status text-danger';
  }
});

function renderEditQuestionList() {
  const list = document.getElementById('edit-question-list');
  list.innerHTML = '';
  if (editingQuestions.length === 0) {
    list.innerHTML = '<p class="text-muted mb-0">No questions yet. Add one to get started.</p>';
    return;
  }
  editingQuestions.forEach((q, idx) => {
    const item = document.createElement('div');
    item.className = 'entry-card d-flex justify-content-between align-items-start flex-wrap gap-2';

    const meta = document.createElement('div');
    meta.className = 'entry-meta flex-grow-1';
    const typeLabel = q.questionType === 'multi' ? 'Multiple select' : 'Single choice';
    meta.innerHTML = `<strong>${idx + 1}. ${DOMPurify.sanitize(q.questionText)}</strong><span class="badge bg-secondary me-1">${typeLabel}</span><span class="badge bg-warning text-dark me-1">${q.points} pt${q.points === 1 ? '' : 's'}</span><span class="text-muted small">${q.options.length} options</span>`;

    const actions = document.createElement('div');
    actions.className = 'd-flex gap-2 flex-wrap';

    if (editingCanEdit) {
      const editBtn = document.createElement('button');
      editBtn.className = 'btn btn-primary btn-sm';
      editBtn.innerHTML = '<i class="bi bi-pencil"></i>';
      editBtn.onclick = () => openQuestionEditor(q);

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'btn btn-danger btn-sm';
      deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
      deleteBtn.onclick = () => handleDeleteQuestion(q.id);

      actions.append(editBtn, deleteBtn);
    }
    item.append(meta, actions);
    list.appendChild(item);
  });
}

async function handleDeleteQuestion(questionId) {
  const ok = await confirmAction('Delete this question? This cannot be undone.', {
    title: 'Delete question?',
    confirmLabel: 'Delete',
  });
  if (!ok) return;
  await api(`/api/questions/${questionId}`, { method: 'DELETE' });
  await loadEditQuestions();
}

document.getElementById('edit-add-question').addEventListener('click', () => openQuestionEditor(null));
document.getElementById('edit-delete-exam').addEventListener('click', () => deleteExam(currentExam));

document.getElementById('edit-exam-back').addEventListener('click', () => { showView('library'); loadLibrary(); });
document.getElementById('edit-exam-back-top').addEventListener('click', () => { showView('library'); loadLibrary(); });

// ---------- Question editor ----------

// Question text and explanation are rich text (Quill); answer options each get their own
// compact rich-text editor too (rebuilt per-question in renderOptionRows since the rows
// themselves are recreated each time the editor opens).
const qeTextQuill = new Quill('#qe-text', {
  theme: 'snow',
  modules: { toolbar: [['bold', 'italic', 'underline'], [{ list: 'ordered' }, { list: 'bullet' }], ['link'], ['clean']] },
});
const qeExplanationQuill = new Quill('#qe-explanation', {
  theme: 'snow',
  modules: { toolbar: [['bold', 'italic', 'underline'], [{ list: 'ordered' }, { list: 'bullet' }], ['link'], ['clean']] },
});
let optionQuills = [];

// An empty Quill editor's HTML is "<p><br></p>", not "" — normalize to '' so server-side
// "is this field/option blank" checks (which test for falsy/empty string) still work.
function quillValue(quill) {
  return quill.getText().trim().length === 0 ? '' : quill.root.innerHTML;
}

function openQuestionEditor(question) {
  editingQuestionId = question ? question.id : null;
  document.getElementById('question-editor-title').textContent = question ? 'Edit Question' : 'Add Question';
  document.getElementById('question-editor-error').classList.add('d-none');

  qeTextQuill.root.innerHTML = question ? question.questionText : '';
  document.getElementById('qe-type').value = question ? question.questionType : 'single';
  document.getElementById('qe-points').value = question && question.points ? question.points : 1;
  document.getElementById('qe-image').value = question && question.imageLink ? question.imageLink : '';
  qeExplanationQuill.root.innerHTML = question && question.explanation ? question.explanation : '';

  renderOptionRows(question ? question.options : []);
  showView('questionEditor');
}

function renderOptionRows(existingOptions) {
  const container = document.getElementById('qe-options');
  container.innerHTML = '';
  optionQuills = [];
  const rows = [];
  for (let i = 0; i < 6; i++) rows.push(existingOptions[i] || { text: '', isCorrect: false });

  rows.forEach((opt, idx) => {
    const row = document.createElement('div');
    row.className = 'qe-option-row d-flex align-items-start gap-2';

    const correctInput = document.createElement('input');
    correctInput.type = 'checkbox';
    correctInput.className = 'form-check-input flex-shrink-0 mt-2';
    correctInput.checked = !!opt.isCorrect;
    correctInput.title = 'Correct answer';

    const editorDiv = document.createElement('div');
    editorDiv.className = 'quill-editor quill-editor-option flex-grow-1';

    row.append(correctInput, editorDiv);
    container.appendChild(row);

    const quill = new Quill(editorDiv, {
      theme: 'snow',
      placeholder: `Option ${idx + 1}`,
      modules: { toolbar: [['bold', 'italic', 'underline']] },
    });
    if (opt.text) quill.root.innerHTML = opt.text;
    optionQuills.push(quill);
  });
}

function cancelQuestionEditor() {
  showView('editExam');
}
document.getElementById('qe-cancel').addEventListener('click', cancelQuestionEditor);
document.getElementById('qe-cancel-top').addEventListener('click', cancelQuestionEditor);

document.getElementById('question-editor-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errorBox = document.getElementById('question-editor-error');
  errorBox.classList.add('d-none');

  const rows = Array.from(document.querySelectorAll('#qe-options .qe-option-row'));
  const options = rows.map((row, idx) => ({
    text: quillValue(optionQuills[idx]),
    isCorrect: row.querySelector('input[type="checkbox"]').checked,
  }));

  const payload = {
    questionText: quillValue(qeTextQuill),
    questionType: document.getElementById('qe-type').value,
    points: parseInt(document.getElementById('qe-points').value, 10) || 1,
    imageLink: document.getElementById('qe-image').value.trim(),
    explanation: quillValue(qeExplanationQuill),
    options,
  };

  try {
    if (editingQuestionId) {
      await api(`/api/questions/${editingQuestionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } else {
      await api(`/api/exams/${currentExam.id}/questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }
    await loadEditQuestions();
    showView('editExam');
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove('d-none');
  }
});

// ---------- Utils ----------

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Tooltips need explicit activation in Bootstrap 5 (unlike data-bs-toggle="modal" triggers).
document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => new bootstrap.Tooltip(el));

async function initUserCapabilities() {
  try {
    const { canCreateExam } = await api('/api/admin/manage/whoami/');
    document.getElementById('create-exam-card').classList.toggle('d-none', !canCreateExam);
  } catch (_) {}
}

loadLibrary();
loadSettings();
loadGroups();
initUserCapabilities();
