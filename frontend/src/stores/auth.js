import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api.js'

export const useAuthStore = defineStore('auth', () => {
  const isStaff = ref(false)
  const canCreateExam = ref(false)
  const loaded = ref(false)

  async function load() {
    if (loaded.value) return
    try {
      const data = await api('/api/admin/manage/whoami/')
      isStaff.value = data.isStaff
      canCreateExam.value = data.canCreateExam
    } catch (_) {}
    loaded.value = true
  }

  return { isStaff, canCreateExam, loaded, load }
})
