<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="h4 mb-0"><i class="bi bi-clock-history me-2"></i>My History</h1>
      <RouterLink to="/" class="btn btn-outline-secondary btn-sm">
        <i class="bi bi-house-door me-1"></i>Home
      </RouterLink>
    </div>
    <div v-if="loading" class="text-muted">Loading…</div>
    <div v-else-if="!instances.length" class="text-muted">No exam history yet.</div>
    <div v-else class="d-flex flex-column gap-2">
      <div v-for="inst in instances" :key="inst.id" class="d-flex justify-content-between align-items-center p-3 rounded border">
        <div>
          <div class="fw-semibold">{{ inst.examName || `Exam #${inst.exam}` }}</div>
          <div class="text-muted small">
            {{ new Date(inst.finishedAt).toLocaleString() }} ·
            {{ inst.numCorrect }}/{{ inst.numQuestions }} correct ·
            {{ pct(inst) }}%
            <span v-if="inst.grade" class="badge bg-info text-dark ms-1">{{ inst.grade }}</span>
          </div>
        </div>
        <RouterLink :to="`/instances/${inst.id}`" class="btn btn-outline-secondary btn-sm">
          <i class="bi bi-search me-1"></i>Review
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api.js'

const instances = ref([])
const loading = ref(true)

function pct(inst) {
  return inst.numQuestions ? Math.round(inst.numCorrect / inst.numQuestions * 100) : 0
}

onMounted(async () => {
  try {
    // Load all exams to get instance history across all
    const exams = await api('/api/exams')
    const all = []
    await Promise.all(exams.map(async (e) => {
      try {
        const insts = await api(`/api/exams/${e.id}/instances`)
        insts.forEach((i) => { i.examName = e.name })
        all.push(...insts)
      } catch (_) {}
    }))
    all.sort((a, b) => new Date(b.finishedAt) - new Date(a.finishedAt))
    instances.value = all
  } finally {
    loading.value = false
  }
})
</script>
