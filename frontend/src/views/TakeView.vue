<template>
  <div v-if="loading" class="text-center py-5">
    <div class="spinner-border text-secondary" role="status"></div>
  </div>
  <div v-else-if="loadError || !take.questions.length" class="text-center py-5">
    <p class="text-muted">{{ loadError || 'No exam in progress.' }}</p>
    <RouterLink to="/" class="btn btn-outline-secondary"><i class="bi bi-house-door me-1"></i>Home</RouterLink>
  </div>
  <div v-else id="view-take" class="quiz-screen">

    <!-- Top bar: exam name + leave + score pills -->
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <span class="text-muted small fw-semibold">{{ take.examName }}</span>
      <div class="d-flex gap-2 align-items-center">
        <span class="pill-badge">{{ totalScore }} pts</span>
        <span class="pill-badge">{{ take.multiplier }}×</span>
<button class="btn btn-outline-secondary btn-sm" @click="leaveExam">
          <i class="bi bi-house-door me-1"></i>Home
        </button>
      </div>
    </div>

    <!-- Progress bar -->
    <div class="progress mb-4" style="height: 6px;">
      <div class="progress-bar" role="progressbar" :style="`width: ${progressPct}%`"></div>
    </div>

    <!-- Bonus meter -->
    <div class="bonus-meter-wrap">
      <div class="bonus-meter-label"><i class="bi bi-lightning-charge-fill"></i>Bonus window</div>
      <div class="progress" style="height: 8px;">
        <div id="take-bonus-bar" class="progress-bar" role="progressbar"
          :style="`width: ${timerPct}%`" :class="timerPct < 20 ? 'bg-danger' : ''"></div>
      </div>
    </div>

    <!-- Question banner -->
    <div class="question-banner-wrap">
      <span class="qnum-pill">Q{{ take.currentIndex + 1 }}/{{ take.questions.length }}</span>
      <div class="question-banner">
        <h2 v-html="sanitize(currentQuestion.questionText)"></h2>
      </div>
    </div>

    <!-- Image -->
    <img v-if="currentQuestion.imageLink"
      :src="currentQuestion.imageLink"
      class="img-fluid rounded mb-4 question-image"
      alt="Question image" />

    <!-- Select hint -->
    <p class="text-center select-hint" :class="checked ? 'd-none' : ''">
      Select {{ selectCount }} answer{{ selectCount > 1 ? 's' : '' }}
    </p>

    <!-- Answer tiles -->
    <div id="take-options" class="tile-grid"
      :style="`grid-template-columns: repeat(${currentQuestion.options.length}, 1fr)`">
      <button
        v-for="(option, idx) in currentQuestion.options" :key="option.id"
        :class="tileClass(option, idx)"
        :disabled="checked"
        @click="selectOption(option)"
      >
        <div class="answer-tile-label" v-html="sanitize(option.text)"></div>
      </button>
    </div>

    <!-- Keyboard tip -->
    <p class="text-center text-muted small mb-4">Tip: press 1–6 on your keyboard to select an option.</p>

    <!-- Feedback -->
    <div id="take-feedback" class="feedback-banner"
      :class="checked ? (checkedResult?.isCorrect ? 'correct' : 'incorrect') : 'd-none'">
      {{ checkedResult?.isCorrect ? `Correct! +${pointsAwarded} pts` : 'Incorrect.' }}
      <div v-if="checkedResult?.explanation"
        class="mt-1 small" style="font-weight:400;opacity:0.9"
        v-html="sanitize(checkedResult.explanation)"></div>
    </div>

    <!-- Action buttons — always present, state-controlled via disabled -->
    <div class="d-flex justify-content-center gap-2 flex-wrap mt-3">
      <button class="btn btn-primary"
        :disabled="!selectedOptions.size || checked"
        @click="checkAnswer">
        Check Answer
      </button>
      <button class="btn btn-outline-secondary"
        :disabled="!checked || isLast"
        @click="nextQuestion">
        Next
      </button>
      <button class="btn btn-outline-danger"
        @click="submitExam">
        Finish Exam
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import DOMPurify from 'dompurify'
import { api } from '../api.js'
import { useTakeStore } from '../stores/take.js'

const route = useRoute()
const router = useRouter()
const take = useTakeStore()

const loading = ref(false)
const loadError = ref('')
const checked = ref(false)
const checkedResult = ref(null)
const selectedOptions = ref(new Set())
const pointsAwarded = ref(0)
const timerPct = ref(100)
let timerInterval = null

const currentQuestion = computed(() => take.questions[take.currentIndex])
const isLast = computed(() => take.currentIndex + 1 >= take.questions.length)
const totalScore = computed(() => take.checked.reduce((sum, c) => sum + (c?.[1]?.pointsAwarded || 0), 0))
const progressPct = computed(() => ((take.currentIndex + 1) / take.questions.length) * 100)
const selectCount = computed(() => currentQuestion.value?.selectCount || 1)

function sanitize(html) {
  return DOMPurify.sanitize(html ?? '', {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'a'],
    ALLOWED_ATTR: ['href'],
  })
}

function tileClass(option, idx) {
  const base = ['answer-tile', `tile-color-${idx % 6}`]
  if (!checked.value) {
    if (selectedOptions.value.has(option.id)) base.push('selected')
    return base.join(' ')
  }
  if (checkedResult.value?.correctOptionIds.includes(String(option.id))) base.push('correct')
  else if (selectedOptions.value.has(option.id)) base.push('incorrect-selected')
  return base.join(' ')
}

function selectOption(option) {
  if (checked.value) return
  if (currentQuestion.value.questionType === 'single') {
    selectedOptions.value = new Set([option.id])
  } else {
    const s = new Set(selectedOptions.value)
    s.has(option.id) ? s.delete(option.id) : s.add(option.id)
    selectedOptions.value = s
  }
}

let focusedTile = -1

function handleKeydown(e) {
  const tiles = Array.from(document.querySelectorAll('#take-options .answer-tile'))
  const count = tiles.length

  if (checked.value) {
    if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); nextQuestion() }
    return
  }

  const n = parseInt(e.key, 10)
  if (n >= 1 && n <= count) {
    e.preventDefault()
    tiles[n - 1].click()
    return
  }
  if (e.key === 'Enter' && selectedOptions.value.size) {
    e.preventDefault()
    checkAnswer()
    return
  }
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault()
    focusedTile = (focusedTile + 1) % count
    tiles[focusedTile]?.focus()
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault()
    focusedTile = (focusedTile - 1 + count) % count
    tiles[focusedTile]?.focus()
  }
}

function startTimer() {
  timerPct.value = 100
  timerInterval = setInterval(() => {
    const elapsed = take.currentElapsed()
    timerPct.value = Math.max(0, 100 - (elapsed / take.bonusWindowSeconds) * 100)
  }, 100)
}

async function checkAnswer() {
  take.pauseBonusTracking()
  clearInterval(timerInterval)
  try {
    const result = await api(`/api/questions/${currentQuestion.value.id}/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_option_ids: [...selectedOptions.value] }),
    })
    checkedResult.value = result
    checked.value = true
    pointsAwarded.value = take.computeAwardedPoints(currentQuestion.value, result.isCorrect)
    take.advanceMultiplier(result.isCorrect)
    take.answers[take.currentIndex] = [...selectedOptions.value]
    // ponytail: tuple format [index, result] matches published checked_json convention
    take.checked[take.currentIndex] = [take.currentIndex, { ...result, pointsAwarded: pointsAwarded.value }]
    await saveProgress()
  } catch (err) {
    alert(err.message)
  }
}

async function nextQuestion() {
  if (isLast.value) {
    await submitExam()
    return
  }
  take.currentIndex++
  selectedOptions.value = new Set()
  checked.value = false
  checkedResult.value = null
  focusedTile = -1
  take.resumeBonusTracking()
  startTimer()
  await saveProgress()
}

async function saveProgress() {
  try {
    await api(`/api/exams/${route.params.id}/progress`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        questions: take.questions,
        answers: take.answers,
        checked: take.checked.map((c, i) => c ?? [i, null]),
        elapsed_seconds: take.elapsedSeconds,
        index: take.currentIndex,
        multiplier: take.multiplier,
        started_at: take.startedAt,
      }),
    })
  } catch (_) {}
}

async function submitExam() {
  const answers = take.questions.map((q, i) => ({
    question_id: q.id,
    selected_option_ids: take.answers[i] || [],
    points_awarded: (take.checked[i]?.[1]?.pointsAwarded) || 0,
  }))
  try {
    const result = await api(`/api/exams/${route.params.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers, started_at: take.startedAt }),
    })
    take.reset()
    router.push(`/instances/${result.instanceId}`)
  } catch (err) {
    alert(err.message)
  }
}

async function leaveExam() {
  if (!confirm('Leave exam? Progress is saved and you can resume later.')) return
  take.pauseBonusTracking()
  clearInterval(timerInterval)
  await saveProgress()
  take.reset()
  router.push('/')
}

onMounted(async () => {
  document.addEventListener('keydown', handleKeydown)
  if (take.questions.length) {
    take.resumeBonusTracking()
    startTimer()
    return
  }
  loading.value = true
  try {
    const data = await api(`/api/exams/${route.params.id}/progress`)
    take.loadFromProgress(data)
    take.examName = data.examName
    take.examId = route.params.id
    if (take.questions.length) {
      take.resumeBonusTracking()
      startTimer()
    }
  } catch (_) {
    loadError.value = 'No saved progress found for this exam.'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  clearInterval(timerInterval)
  take.pauseBonusTracking()
})
</script>
