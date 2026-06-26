<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="h4 mb-0"><i class="bi bi-database me-2"></i>Question Banks</h1>
      <RouterLink to="/" class="btn btn-outline-secondary btn-sm">
        <i class="bi bi-house-door me-1"></i>Home
      </RouterLink>
    </div>

    <!-- Import new bank -->
    <div class="card mb-4">
      <div class="card-body">
        <h2 class="card-title h5 mb-3"><i class="bi bi-upload me-2"></i>Import Bank from CSV</h2>
        <form @submit.prevent="importBank" class="row g-3">
          <div class="col-12 col-md-5">
            <label class="form-label">Bank name (optional)</label>
            <input v-model="form.name" type="text" class="form-control" placeholder="Defaults to filename" />
          </div>
          <div class="col-12 col-md-5">
            <label class="form-label">CSV file</label>
            <input ref="fileInput" type="file" class="form-control" accept=".csv" required />
          </div>
          <div class="col-12 d-flex gap-2 align-items-center">
            <button type="submit" class="btn btn-primary" :disabled="importing">
              <i class="bi bi-upload me-1"></i>{{ importing ? 'Importing…' : 'Import' }}
            </button>
            <a href="/template.csv" download class="btn btn-outline-secondary btn-sm">
              <i class="bi bi-download me-1"></i>CSV Template
            </a>
            <span v-if="importError" class="text-danger small">{{ importError }}</span>
          </div>
        </form>
      </div>
    </div>

    <!-- Bank list -->
    <div class="card">
      <div class="card-body">
        <div v-if="loading" class="text-muted small">Loading…</div>
        <div v-else-if="!banks.length" class="text-muted small">No question banks yet.</div>
        <div v-else class="table-responsive">
          <table class="table table-sm align-middle mb-0">
            <thead><tr><th>Name</th><th>Questions</th><th>Created</th><th></th></tr></thead>
            <tbody>
              <tr v-for="bank in banks" :key="bank.id">
                <td><RouterLink :to="`/banks/${bank.id}`">{{ bank.name }}</RouterLink></td>
                <td>{{ bank.questionCount }}</td>
                <td class="text-muted small">{{ new Date(bank.createdAt).toLocaleDateString() }}</td>
                <td class="text-end text-nowrap">
                  <RouterLink :to="`/banks/${bank.id}`" class="btn btn-primary btn-sm me-1" title="Edit">
                    <i class="bi bi-pencil"></i>
                  </RouterLink>
                  <button class="btn btn-danger btn-sm" @click="deleteBank(bank)" title="Delete">
                    <i class="bi bi-trash"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api.js'

const banks = ref([])
const loading = ref(true)
const importing = ref(false)
const importError = ref('')
const form = ref({ name: '' })
const fileInput = ref(null)

async function load() {
  loading.value = true
  try {
    banks.value = await api('/api/banks')
  } finally {
    loading.value = false
  }
}

async function importBank() {
  importing.value = true
  importError.value = ''
  const file = fileInput.value?.files[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  if (form.value.name.trim()) fd.append('name', form.value.name.trim())
  try {
    await api('/api/banks', { method: 'POST', body: fd })
    form.value.name = ''
    fileInput.value.value = ''
    await load()
  } catch (err) {
    importError.value = err.message
  } finally {
    importing.value = false
  }
}

async function deleteBank(bank) {
  if (!confirm(`Delete bank "${bank.name}"? This will also remove all its questions and may break exams that reference it.`)) return
  try {
    await api(`/api/banks/${bank.id}`, { method: 'DELETE' })
    await load()
  } catch (err) {
    alert(err.message)
  }
}

onMounted(load)
</script>
