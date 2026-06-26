<template>
  <div v-if="loading" class="text-muted">Loading…</div>
  <div v-else-if="!bank">
    <p class="text-danger">Bank not found.</p>
    <RouterLink to="/banks" class="btn btn-outline-secondary btn-sm">Back</RouterLink>
  </div>
  <div v-else>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="h4 mb-0"><i class="bi bi-database me-2"></i>{{ bank.bankName }}</h1>
      <div class="d-flex gap-2">
        <a :href="`/api/banks/${bankId}/export`" class="btn btn-outline-secondary btn-sm">
          <i class="bi bi-download me-1"></i>Export CSV
        </a>
        <RouterLink to="/banks" class="btn btn-outline-secondary btn-sm">
          <i class="bi bi-arrow-left me-1"></i>Banks
        </RouterLink>
      </div>
    </div>

    <!-- Re-upload CSV -->
    <div v-if="bank.canEdit" class="card mb-4">
      <div class="card-body">
        <h2 class="card-title h6 mb-2"><i class="bi bi-arrow-repeat me-2"></i>Replace Questions via CSV</h2>
        <form @submit.prevent="reimport" class="d-flex gap-2 align-items-center flex-wrap">
          <input ref="reimportInput" type="file" class="form-control form-control-sm" accept=".csv" style="max-width:280px" required />
          <button type="submit" class="btn btn-warning btn-sm" :disabled="reimporting">
            {{ reimporting ? 'Replacing…' : 'Replace' }}
          </button>
          <a href="/template.csv" download class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-download me-1"></i>CSV Template
          </a>
          <span v-if="reimportError" class="text-danger small">{{ reimportError }}</span>
        </form>
      </div>
    </div>

    <!-- Question list -->
    <div class="card">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h2 class="h5 mb-0"><i class="bi bi-list-ul me-2"></i>Questions ({{ bank.questions.length }})</h2>
          <button v-if="bank.canEdit" class="btn btn-primary btn-sm" @click="openEditor(null)">
            <i class="bi bi-plus-lg me-1"></i>Add
          </button>
        </div>
        <div v-if="!bank.questions.length" class="text-muted small">No questions yet.</div>
        <div v-else class="d-flex flex-column gap-2">
          <div
            v-for="q in bank.questions" :key="q.id"
            class="p-3 rounded border"
          >
            <div class="d-flex justify-content-between align-items-start gap-2">
              <div class="flex-grow-1">
                <span v-if="q.category" class="badge bg-secondary me-1">{{ q.category }}</span>
                <span class="fw-semibold" v-html="sanitize(q.questionText)"></span>
                <span class="text-muted small ms-2">({{ q.questionType }}, {{ q.points }}pt)</span>
              </div>
              <div v-if="bank.canEdit" class="d-flex gap-1 flex-shrink-0">
                <button class="btn btn-primary btn-sm" @click="openEditor(q)" title="Edit"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-danger btn-sm" @click="deleteQuestion(q)" title="Delete"><i class="bi bi-trash"></i></button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Question editor modal -->
    <div v-if="editorOpen" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editTarget ? 'Edit Question' : 'Add Question' }}</h5>
            <button class="btn-close" @click="editorOpen = false"></button>
          </div>
          <div class="modal-body">
            <div v-if="editorError" class="alert alert-danger">{{ editorError }}</div>
            <div class="mb-3">
              <label class="form-label">Category</label>
              <input v-model="editorForm.category" type="text" class="form-control" placeholder="e.g. Networking" />
            </div>
            <div class="mb-3">
              <label class="form-label">Question text <span class="text-danger">*</span></label>
              <RichEditor v-model="editorForm.questionText" />
            </div>
            <div class="mb-3">
              <label class="form-label">Type</label>
              <select v-model="editorForm.questionType" class="form-select">
                <option value="single">Single choice</option>
                <option value="multi">Multi choice</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">Points</label>
              <input v-model.number="editorForm.points" type="number" min="1" class="form-control" style="max-width:100px" />
            </div>
            <div class="mb-3">
              <label class="form-label">Options <span class="text-danger">*</span></label>
              <div v-for="(opt, idx) in editorForm.options" :key="opt._key" class="d-flex gap-2 mb-2 align-items-start">
                <input type="checkbox" :checked="opt.isCorrect" @change="opt.isCorrect = $event.target.checked" class="form-check-input flex-shrink-0" style="margin-top: 0.85rem" title="Mark as correct" />
                <div class="flex-grow-1">
                  <RichEditor v-model="opt.text" :toolbar="inlineToolbar" />
                </div>
                <button class="btn btn-outline-danger btn-sm flex-shrink-0" @click="editorForm.options.splice(idx,1)" type="button" style="margin-top: 0.4rem">
                  <i class="bi bi-x"></i>
                </button>
              </div>
              <button class="btn btn-outline-secondary btn-sm" @click="editorForm.options.push({ _key: crypto.randomUUID(), text: '', isCorrect: false })" type="button">
                <i class="bi bi-plus me-1"></i>Add option
              </button>
            </div>
            <div class="mb-3">
              <label class="form-label">Explanation</label>
              <RichEditor v-model="editorForm.explanation" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-outline-secondary" @click="editorOpen = false">Cancel</button>
            <button class="btn btn-primary" @click="saveQuestion" :disabled="saving">
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import DOMPurify from 'dompurify'
import { api } from '../api.js'
import RichEditor from '../components/RichEditor.vue'

const inlineToolbar = [['bold', 'italic', 'underline']]

const route = useRoute()
const bankId = route.params.id

const loading = ref(true)
const bank = ref(null)
const reimportInput = ref(null)
const reimporting = ref(false)
const reimportError = ref('')
const editorOpen = ref(false)
const editorError = ref('')
const editTarget = ref(null)
const saving = ref(false)
const editorForm = ref(emptyForm())

function sanitize(html) {
  return DOMPurify.sanitize(html ?? '', { ALLOWED_TAGS: [] })
}

function emptyForm() {
  return {
    category: '', questionText: '', questionType: 'single', points: 1, explanation: '',
    options: [
      { _key: crypto.randomUUID(), text: '', isCorrect: false },
      { _key: crypto.randomUUID(), text: '', isCorrect: false },
    ],
  }
}

async function load() {
  loading.value = true
  try {
    bank.value = await api(`/api/banks/${bankId}/questions`)
  } finally {
    loading.value = false
  }
}

async function reimport() {
  reimporting.value = true
  reimportError.value = ''
  const file = reimportInput.value?.files[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    await api(`/api/banks/${bankId}/import`, { method: 'PUT', body: fd })
    reimportInput.value.value = ''
    await load()
  } catch (err) {
    reimportError.value = err.message
  } finally {
    reimporting.value = false
  }
}

function openEditor(question) {
  editTarget.value = question
  editorError.value = ''
  if (question) {
    editorForm.value = {
      category: question.category || '',
      questionText: question.questionText,
      questionType: question.questionType,
      points: question.points,
      explanation: question.explanation || '',
      options: question.options.map((o) => ({ _key: String(o.id), text: o.text, isCorrect: o.isCorrect })),
    }
  } else {
    editorForm.value = emptyForm()
  }
  editorOpen.value = true
}

async function saveQuestion() {
  saving.value = true
  editorError.value = ''
  const payload = {
    category: editorForm.value.category,
    question_text: editorForm.value.questionText,
    question_type: editorForm.value.questionType,
    points: editorForm.value.points,
    explanation: editorForm.value.explanation,
    options: editorForm.value.options.map((o) => ({ text: o.text, is_correct: o.isCorrect })),
  }
  try {
    if (editTarget.value) {
      await api(`/api/questions/${editTarget.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } else {
      await api(`/api/banks/${bankId}/questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    }
    editorOpen.value = false
    await load()
  } catch (err) {
    editorError.value = err.message
  } finally {
    saving.value = false
  }
}

async function deleteQuestion(q) {
  if (!confirm('Delete this question?')) return
  try {
    await api(`/api/questions/${q.id}`, { method: 'DELETE' })
    await load()
  } catch (err) {
    alert(err.message)
  }
}

onMounted(load)
</script>
