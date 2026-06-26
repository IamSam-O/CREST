<template>
  <nav class="navbar navbar-dark mb-4">
    <div class="container d-flex justify-content-between align-items-center">
      <RouterLink to="/" class="navbar-brand mb-0 h1">
        <i class="bi bi-shield-fill me-2"></i>CREST
        <small class="d-none d-md-inline fw-normal opacity-75 fs-6">Collaborative Rich-text Exam Self-hosted Tool</small>
      </RouterLink>
      <div class="d-flex gap-2">
        <button class="btn btn-outline-secondary btn-sm" title="Toggle theme" @click="toggleTheme">
          <i :class="isDark ? 'bi bi-moon-stars-fill' : 'bi bi-sun-fill'"></i>
        </button>
        <a href="/manage/" class="btn btn-outline-secondary btn-sm">
          <i class="bi bi-sliders me-1"></i>Manage
        </a>
      </div>
    </div>
  </nav>

  <main class="container pb-5">
    <RouterView />
  </main>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useAuthStore } from './stores/auth.js'

const auth = useAuthStore()
onMounted(() => auth.load())

const isDark = ref(true)

function applyTheme(dark) {
  document.body.classList.toggle('theme-light', !dark)
}

function toggleTheme() {
  isDark.value = !isDark.value
  applyTheme(isDark.value)
}

// Apply persisted theme on load
const saved = localStorage.getItem('crest-theme')
if (saved === 'light') {
  isDark.value = false
  applyTheme(false)
}

watch(isDark, (v) => localStorage.setItem('crest-theme', v ? 'dark' : 'light'))
</script>
