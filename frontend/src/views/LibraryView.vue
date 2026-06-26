<template>
  <div>
    <!-- Question Banks (editor+) -->
    <div v-if="auth.canCreateExam || auth.isStaff" class="card mb-4">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-3">
          <h2 class="card-title h5 mb-0"><i class="bi bi-database me-2"></i>Question Banks</h2>
          <RouterLink to="/banks" class="btn btn-outline-secondary btn-sm">
            <i class="bi bi-upload me-1"></i>Import / Manage
          </RouterLink>
        </div>
        <div v-if="banksLoading" class="text-muted small">Loading…</div>
        <div v-else-if="!banks.length" class="text-muted small">
          No question banks yet. Import a CSV to create one.
        </div>
        <div v-else class="d-flex flex-column gap-2">
          <div
            v-for="bank in banks" :key="bank.id"
            class="d-flex justify-content-between align-items-center p-3 rounded border"
          >
            <div>
              <span class="fw-semibold">{{ bank.name }}</span>
              <span class="text-muted small ms-2">{{ bank.questionCount }} questions</span>
            </div>
            <RouterLink :to="`/banks/${bank.id}`" class="btn btn-outline-secondary btn-sm" title="Edit bank">
              <i class="bi bi-pencil"></i>
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <!-- Exam Library -->
    <div class="card">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
          <h2 class="card-title h5 mb-0"><i class="bi bi-collection me-2"></i>Exam Library</h2>
          <div class="d-flex gap-2 flex-wrap">
            <button v-if="auth.canCreateExam || auth.isStaff" class="btn btn-primary btn-sm" @click="showCreateModal = true">
              <i class="bi bi-plus-lg me-1"></i>New Exam
            </button>
            <RouterLink to="/history" class="btn btn-outline-secondary btn-sm">
              <i class="bi bi-clock-history me-1"></i>History
            </RouterLink>
            <a href="/multiplayer/" class="btn btn-outline-secondary btn-sm">
              <i class="bi bi-people me-1"></i>Multiplayer
            </a>
          </div>
        </div>

        <input v-model="search" type="text" class="form-control mb-3" placeholder="Search exams…" />

        <div v-if="loading" class="text-muted small">Loading…</div>
        <div v-else-if="!filteredExams.length" class="text-muted small">No exams found.</div>
        <div v-else class="d-flex flex-column gap-2">
          <div
            v-for="exam in filteredExams" :key="exam.id"
            class="d-flex justify-content-between align-items-center p-3 rounded border"
          >
            <div class="flex-grow-1 me-3">
              <div class="fw-semibold">{{ exam.name }}</div>
              <div class="text-muted small">
                {{ exam.questionCount }} questions drawn
                <span v-if="exam.questionBankName"> · bank: {{ exam.questionBankName }}</span>
                <span v-if="exam.lastScore != null"> · last: {{ exam.lastScore }}/{{ exam.lastTotal }}</span>
              </div>
            </div>
            <div class="d-flex gap-2 flex-shrink-0">
              <RouterLink :to="`/exams/${exam.id}/setup`" class="btn btn-primary btn-sm">
                <i class="bi bi-play-fill me-1"></i>Start
              </RouterLink>
              <RouterLink v-if="exam.canEdit && exam.questionBankId" :to="`/banks/${exam.questionBankId}`" class="btn btn-outline-secondary btn-sm" title="Edit questions">
                <i class="bi bi-pencil"></i>
              </RouterLink>
              <button v-if="exam.canEdit" class="btn btn-danger btn-sm" @click="deleteExam(exam)" title="Delete exam">
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- In Progress -->
    <div v-if="inProgress.length" class="card mt-4">
      <div class="card-body">
        <h2 class="card-title h5 mb-3"><i class="bi bi-hourglass-split me-2"></i>In Progress</h2>
        <div class="d-flex flex-column gap-2">
          <div
            v-for="exam in inProgress" :key="exam.id"
            class="d-flex justify-content-between align-items-center p-3 rounded border"
          >
            <div class="flex-grow-1 me-3">
              <div class="fw-semibold">{{ exam.name }}</div>
              <div class="text-muted small">{{ exam.progressNumChecked }}/{{ exam.progressTotal }} answered</div>
            </div>
            <div class="d-flex gap-2 flex-shrink-0">
              <RouterLink :to="`/exams/${exam.id}/take`" class="btn btn-primary btn-sm">
                <i class="bi bi-play-fill me-1"></i>Resume
              </RouterLink>
              <button class="btn btn-danger btn-sm" @click="deleteProgress(exam)" title="Abandon">
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- New Exam modal -->
  <div v-if="showCreateModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)" @click.self="showCreateModal = false">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="bi bi-plus-circle me-2"></i>New Exam</h5>
          <button class="btn-close" @click="showCreateModal = false"></button>
        </div>
        <div class="modal-body">
          <div v-if="createError" class="alert alert-danger mb-3">{{ createError }}</div>
          <form @submit.prevent="createExam" id="create-exam-form">
            <div class="mb-3">
              <label class="form-label">Name</label>
              <input v-model="form.name" type="text" class="form-control" placeholder="e.g. CompTIA Network+ Practice" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Question Bank</label>
              <select v-model="form.bankId" class="form-select" required>
                <option value="">— select a bank —</option>
                <option v-for="b in banks" :key="b.id" :value="b.id">{{ b.name }} ({{ b.questionCount }} q)</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">Draw size</label>
              <input v-model.number="form.questionCount" type="number" min="1" class="form-control" />
            </div>
          </form>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline-secondary" @click="showCreateModal = false">Cancel</button>
          <button class="btn btn-primary" form="create-exam-form" type="submit" :disabled="creating">
            <i class="bi bi-check2 me-1"></i>{{ creating ? 'Creating…' : 'Create' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api.js'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const exams = ref([])
const banks = ref([])
const loading = ref(true)
const banksLoading = ref(false)
const search = ref('')
const creating = ref(false)
const createError = ref('')
const showCreateModal = ref(false)
const form = ref({ name: '', bankId: '', questionCount: 10 })

const inProgress = computed(() => exams.value.filter((e) => e.progressIndex != null))
const filteredExams = computed(() => {
  const q = search.value.toLowerCase()
  return exams.value.filter((e) => !q || e.name.toLowerCase().includes(q))
})

async function loadExams() {
  loading.value = true
  try {
    exams.value = await api('/api/exams')
  } finally {
    loading.value = false
  }
}

async function loadBanks() {
  if (!auth.canCreateExam && !auth.isStaff) return
  banksLoading.value = true
  try {
    banks.value = await api('/api/banks')
  } catch (_) {
  } finally {
    banksLoading.value = false
  }
}

async function createExam() {
  creating.value = true
  createError.value = ''
  try {
    await api('/api/exams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: form.value.name,
        question_bank_id: form.value.bankId,
        question_count: form.value.questionCount,
      }),
    })
    form.value = { name: '', bankId: '', questionCount: 10 }
    showCreateModal.value = false
    await loadExams()
  } catch (err) {
    createError.value = err.message
  } finally {
    creating.value = false
  }
}

async function deleteExam(exam) {
  if (!confirm(`Delete "${exam.name}"? This cannot be undone.`)) return
  try {
    await api(`/api/exams/${exam.id}`, { method: 'DELETE' })
    await loadExams()
  } catch (err) {
    alert(err.message)
  }
}

async function deleteProgress(exam) {
  if (!confirm(`Abandon your progress on "${exam.name}"?`)) return
  try {
    await api(`/api/exams/${exam.id}/progress`, { method: 'DELETE' })
    await loadExams()
  } catch (err) {
    alert(err.message)
  }
}

onMounted(async () => {
  await auth.load()
  await Promise.all([loadExams(), loadBanks()])
})
</script>
