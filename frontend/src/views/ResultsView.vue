<template>
  <div v-if="loading" class="text-muted">Loading…</div>
  <div v-else-if="error" class="alert alert-danger">{{ error }}</div>
  <div v-else-if="instance">
    <!-- Header -->
    <div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
      <div>
        <h1 class="h4 mb-0"><i class="bi bi-trophy me-2"></i>{{ instance.examName || 'Results' }}</h1>
        <div class="text-muted small">{{ new Date(instance.finishedAt).toLocaleString() }}</div>
      </div>
      <div class="d-flex gap-2 flex-wrap">
        <RouterLink v-if="instance.examId" :to="`/exams/${instance.examId}/setup`" class="btn btn-primary btn-sm">
          <i class="bi bi-arrow-repeat me-1"></i>Retake
        </RouterLink>
        <RouterLink to="/history" class="btn btn-outline-secondary btn-sm">
          <i class="bi bi-clock-history me-1"></i>History
        </RouterLink>
        <RouterLink to="/" class="btn btn-outline-secondary btn-sm">
          <i class="bi bi-house-door me-1"></i>Home
        </RouterLink>
      </div>
    </div>

    <!-- Score summary -->
    <div class="card mb-4">
      <div class="card-body">
        <div class="row g-3 text-center">
          <div class="col-6 col-md-3">
            <div class="h2 mb-0" :class="pctClass">{{ instance.numCorrect }}/{{ instance.numQuestions }}</div>
            <div class="text-muted small">correct</div>
          </div>
          <div class="col-6 col-md-3">
            <div class="h2 mb-0" :class="pctClass">{{ pct }}%</div>
            <div class="text-muted small">score</div>
          </div>
          <div class="col-6 col-md-3">
            <div class="h2 mb-0">
              {{ instance.pointsEarned }}<span class="text-muted fs-6">/{{ instance.totalPoints }}</span>
            </div>
            <div class="text-muted small">points</div>
          </div>
          <div class="col-6 col-md-3">
            <div class="h2 mb-0">
              <span v-if="instance.grade">{{ instance.grade }}</span>
              <span v-else class="text-muted">—</span>
            </div>
            <div class="text-muted small">grade</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Export / Generate missed (editor + staff only, when there are missed questions) -->
    <div v-if="(auth.isStaff || auth.canCreateExam) && missedCount > 0" class="d-flex gap-2 flex-wrap mb-4">
      <button class="btn btn-outline-secondary btn-sm" @click="exportMissedCsv">
        <i class="bi bi-download me-1"></i>Export Missed CSV
      </button>
      <button class="btn btn-outline-secondary btn-sm" :disabled="generating" @click="generateExam">
        <i class="bi bi-file-earmark-plus me-1"></i>{{ generating ? 'Generating…' : 'Generate Missed Exam' }}
      </button>
    </div>

    <!-- Per-question review -->
    <div class="card">
      <div class="card-body">
        <h2 class="h5 mb-3">Question Review</h2>
        <div v-if="!instance.results?.length" class="text-muted small">
          No question data available. The questions may have been removed from their bank.
        </div>
        <div class="d-flex flex-column gap-3">
          <div
            v-for="(r, idx) in instance.results" :key="r.questionId"
            class="p-3 rounded border"
            :class="r.isCorrect ? 'border-success' : 'border-danger'"
          >
            <div class="d-flex justify-content-between">
              <div class="fw-semibold mb-2" v-html="`${idx + 1}. ${sanitize(r.questionText)}`"></div>
              <span :class="r.isCorrect ? 'text-success' : 'text-danger'">
                <i :class="r.isCorrect ? 'bi bi-check-circle-fill' : 'bi bi-x-circle-fill'"></i>
              </span>
            </div>
            <div class="d-flex flex-column gap-1">
              <div v-for="opt in r.options" :key="opt.id" class="small"
                :class="{
                  'text-success fw-semibold': opt.isCorrect,
                  'text-danger': !opt.isCorrect && r.selectedOptionIds.includes(opt.id),
                  'text-muted': !opt.isCorrect && !r.selectedOptionIds.includes(opt.id),
                }"
              >
                <i v-if="opt.isCorrect" class="bi bi-check me-1"></i>
                <i v-else-if="r.selectedOptionIds.includes(opt.id)" class="bi bi-x me-1"></i>
                <div class="d-inline" v-html="sanitize(opt.text)"></div>
              </div>
            </div>
            <div v-if="r.explanation" class="mt-2 text-muted small" v-html="sanitize(r.explanation)"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Grade history (shown when instance has been re-evaluated) -->
    <div v-if="instance.gradeLog && instance.gradeLog.length" class="card mt-4">
      <div class="card-body">
        <h2 class="h5 mb-3">Grade History</h2>
        <div class="table-responsive">
          <table class="table table-sm align-middle mb-0">
            <thead class="text-muted small">
              <tr><th>Date</th><th>By</th><th>Scale</th><th>Grade</th><th>Note</th></tr>
            </thead>
            <tbody>
              <tr v-for="entry in instance.gradeLog" :key="entry.changedAt">
                <td class="text-nowrap small">{{ new Date(entry.changedAt).toLocaleString() }}</td>
                <td class="small">{{ entry.changedBy }}</td>
                <td class="small">{{ entry.scaleName || '—' }}</td>
                <td>
                  <span v-if="entry.newGrade" class="badge bg-info text-dark">{{ entry.newGrade }}</span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="small">{{ entry.note }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import DOMPurify from 'dompurify'
import { api, getToken } from '../api.js'
import { useAuthStore } from '../stores/auth.js'

const route = useRoute()
const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const instance = ref(null)
const generating = ref(false)

const pct = computed(() => instance.value
  ? Math.round(instance.value.numCorrect / instance.value.numQuestions * 100) : 0)
const pctClass = computed(() => pct.value >= 70 ? 'text-success' : 'text-danger')
const missedCount = computed(() => instance.value?.results?.filter((r) => !r.isCorrect).length ?? 0)

function sanitize(html) {
  return DOMPurify.sanitize(html ?? '', {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'a'],
    ALLOWED_ATTR: ['href'],
  })
}

async function exportMissedCsv() {
  const token = await getToken()
  const res = await fetch(`/api/admin/manage/instances/${route.params.id}/missed-csv/`, {
    headers: token ? { Authorization: `Token ${token}` } : {},
  })
  if (!res.ok) { alert('Export failed.'); return }
  const filename = res.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || `missed_${route.params.id}.csv`
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

async function generateExam() {
  generating.value = true
  try {
    const result = await api(`/api/admin/manage/instances/${route.params.id}/generate-exam/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    })
    alert(`Created "${result.examName}" with ${result.questionCount} question${result.questionCount !== 1 ? 's' : ''}. Find it in your Library.`)
  } catch (err) {
    alert(`Failed: ${err.message}`)
  } finally {
    generating.value = false
  }
}

onMounted(async () => {
  await auth.load()
  try {
    instance.value = await api(`/api/instances/${route.params.id}`)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
})
</script>
