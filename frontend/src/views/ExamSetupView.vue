<template>
  <div v-if="loading" class="text-muted">Loading…</div>
  <div v-else-if="error" class="alert alert-danger">{{ error }}</div>
  <div v-else-if="exam">
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="h4 mb-0">{{ exam.name }}</h1>
      <RouterLink to="/" class="btn btn-outline-secondary btn-sm">
        <i class="bi bi-house-door me-1"></i>Home
      </RouterLink>
    </div>

    <!-- Stats -->
    <div class="card mb-4">
      <div class="card-body">
        <div class="row g-3 text-center">
          <div class="col-6 col-md-3">
            <div class="h2 mb-0">{{ exam.questionCount }}</div>
            <div class="text-muted small">questions per attempt</div>
          </div>
          <div class="col-6 col-md-3">
            <div class="h2 mb-0">{{ exam.bonusWindowSeconds }}s</div>
            <div class="text-muted small">bonus window</div>
          </div>
          <div v-if="exam.lastScore != null" class="col-6 col-md-3">
            <div class="h2 mb-0">{{ exam.lastScore }}/{{ exam.lastTotal }}</div>
            <div class="text-muted small">last score</div>
          </div>
          <div class="col-6 col-md-3">
            <div class="h2 mb-0">{{ exam.instanceCount }}</div>
            <div class="text-muted small">attempts</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Settings (editor+) -->
    <div v-if="exam.canEdit" class="card mb-4">
      <div class="card-body">
        <h2 class="h6 mb-3"><i class="bi bi-gear me-2"></i>Settings</h2>
        <form @submit.prevent="saveSettings" class="row g-3">
          <div class="col-12 col-md-4">
            <label class="form-label">Bonus window (seconds)</label>
            <input v-model.number="settings.bonusWindowSeconds" type="number" min="1" class="form-control" />
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">Draw size</label>
            <input v-model.number="settings.questionCount" type="number" min="1" class="form-control" />
          </div>

          <!-- Category weights -->
          <div class="col-12" v-if="categories.length">
            <label class="form-label d-flex justify-content-between align-items-center">
              <span>Category weights <span class="text-muted fw-normal">(optional — blank = draw proportionally from all)</span></span>
              <span class="small" :class="weightTotal > 100 ? 'text-danger' : weightTotal > 0 ? 'text-success' : 'text-muted'">
                {{ weightTotal }}% allocated
              </span>
            </label>
            <div class="table-responsive">
              <table class="table table-sm align-middle mb-0">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Questions in bank</th>
                    <th style="width:140px">Weight %</th>
                    <th>Draw estimate</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="cat in categories" :key="cat.category">
                    <td>
                      <span v-if="cat.category">{{ cat.category }}</span>
                      <span v-else class="text-muted fst-italic">Uncategorised</span>
                    </td>
                    <td>{{ cat.count }}</td>
                    <td>
                      <div class="input-group input-group-sm">
                        <input
                          type="number" min="0" max="100" step="1"
                          class="form-control"
                          :value="settings.categoryWeights[cat.category] ?? ''"
                          @input="setWeight(cat.category, $event.target.value)"
                          placeholder="—"
                        />
                        <span class="input-group-text">%</span>
                      </div>
                    </td>
                    <td class="text-muted small">
                      {{ estimateDraw(cat.category, cat.count) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="weightTotal > 100" class="text-danger small mt-1">
              Weights exceed 100% — reduce them before saving.
            </div>
            <div v-else-if="weightTotal > 0 && weightTotal < 100" class="text-muted small mt-1">
              Remaining {{ 100 - weightTotal }}% will be drawn proportionally from the full pool.
            </div>
          </div>
          <div v-else-if="exam.questionBankId && !loadingCategories" class="col-12">
            <p class="text-muted small mb-0">No categories found in this bank. Add a Category column to your CSV to enable weighted sampling.</p>
          </div>

          <div class="col-12 col-md-4">
            <label class="form-label">Grade Scale</label>
            <select v-model="settings.gradeScaleId" class="form-select">
              <option value="">— none —</option>
              <option v-for="s in gradeScales" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>

          <div class="col-12 d-flex gap-2 align-items-center">
            <button type="submit" class="btn btn-outline-secondary btn-sm" :disabled="saving || weightTotal > 100">
              {{ saving ? 'Saving…' : 'Save Settings' }}
            </button>
            <span v-if="settingsError" class="text-danger small">{{ settingsError }}</span>
            <span v-if="settingsSaved" class="text-success small"><i class="bi bi-check2 me-1"></i>Saved</span>
          </div>
        </form>
      </div>
    </div>

    <!-- Start -->
    <div class="text-center">
      <button class="btn btn-primary btn-lg px-5" @click="startExam" :disabled="starting">
        <i class="bi bi-play-fill me-2"></i>{{ starting ? 'Starting…' : 'Start Exam' }}
      </button>
      <p v-if="startError" class="text-danger mt-2">{{ startError }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { api } from '../api.js'
import { useTakeStore } from '../stores/take.js'

const route = useRoute()
const router = useRouter()
const take = useTakeStore()
const examId = route.params.id

const loading = ref(true)
const error = ref('')
const exam = ref(null)
const categories = ref([])
const gradeScales = ref([])
const loadingCategories = ref(false)
const saving = ref(false)
const settingsError = ref('')
const settingsSaved = ref(false)
const starting = ref(false)
const startError = ref('')
const settings = ref({ bonusWindowSeconds: 30, questionCount: 10, categoryWeights: {}, gradeScaleId: '' })

const weightTotal = computed(() =>
  Object.values(settings.value.categoryWeights).reduce((s, v) => s + (Number(v) || 0), 0)
)

function setWeight(category, raw) {
  const v = raw === '' ? undefined : Math.max(0, Math.min(100, Number(raw)))
  const weights = { ...settings.value.categoryWeights }
  if (v == null || isNaN(v)) {
    delete weights[category]
  } else {
    weights[category] = v
  }
  settings.value.categoryWeights = weights
}

function estimateDraw(category, bankCount) {
  const w = settings.value.categoryWeights[category]
  if (!w) return '—'
  const n = Math.round(settings.value.questionCount * w / 100)
  return `~${Math.min(n, bankCount)} of ${settings.value.questionCount}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const exams = await api('/api/exams')
    exam.value = exams.find((e) => String(e.id) === String(examId)) || null
    if (exam.value) {
      settings.value.bonusWindowSeconds = exam.value.bonusWindowSeconds || 30
      settings.value.questionCount = exam.value.questionCount || 10
      settings.value.categoryWeights = { ...(exam.value.categoryWeights || {}) }
      settings.value.gradeScaleId = exam.value.gradeScaleId || ''
      if (exam.value.questionBankId) loadCategories(exam.value.questionBankId)
    }
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function loadCategories(bankId) {
  loadingCategories.value = true
  try {
    categories.value = await api(`/api/banks/${bankId}/categories`)
    // Drop any saved weights for categories that no longer exist
    const valid = new Set(categories.value.map((c) => c.category))
    const cleaned = Object.fromEntries(
      Object.entries(settings.value.categoryWeights).filter(([k]) => valid.has(k))
    )
    settings.value.categoryWeights = cleaned
  } catch (_) {
    categories.value = []
  } finally {
    loadingCategories.value = false
  }
}

async function saveSettings() {
  saving.value = true
  settingsError.value = ''
  settingsSaved.value = false
  try {
    await api(`/api/exams/${examId}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bonus_window_seconds: settings.value.bonusWindowSeconds,
        question_count: settings.value.questionCount,
        category_weights: settings.value.categoryWeights,
        grade_scale_id: settings.value.gradeScaleId || null,
      }),
    })
    settingsSaved.value = true
    setTimeout(() => { settingsSaved.value = false }, 2000)
  } catch (err) {
    settingsError.value = err.message
  } finally {
    saving.value = false
  }
}

async function startExam() {
  starting.value = true
  startError.value = ''
  try {
    const data = await api(`/api/exams/${examId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })
    take.reset()
    take.examId = data.examId
    take.examName = data.examName
    take.bonusWindowSeconds = data.bonusWindowSeconds
    take.questions = data.questions
    take.answers = new Array(data.questions.length).fill(null)
    take.checked = new Array(data.questions.length).fill(null)
    take.startedAt = new Date().toISOString()
    take.resumeBonusTracking()
    router.push(`/exams/${examId}/take`)
  } catch (err) {
    startError.value = err.message
  } finally {
    starting.value = false
  }
}

onMounted(async () => {
  await load()
  api('/api/grade-scales').then((s) => { gradeScales.value = s }).catch(() => {})
})
</script>
