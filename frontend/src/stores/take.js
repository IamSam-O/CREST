import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useTakeStore = defineStore('take', () => {
  const examId = ref(null)
  const examName = ref('')
  const bonusWindowSeconds = ref(30)
  const questions = ref([])
  const answers = ref([])
  const checked = ref([])
  const elapsedSeconds = ref([])
  const currentIndex = ref(0)
  const multiplier = ref(1)
  const startedAt = ref(null)
  const activeSince = ref(null)

  const MULTIPLIER_MAX = 30

  const currentQuestion = computed(() => questions.value[currentIndex.value] ?? null)
  const isFinished = computed(() => currentIndex.value >= questions.value.length)

  function reset() {
    examId.value = null
    examName.value = ''
    bonusWindowSeconds.value = 30
    questions.value = []
    answers.value = []
    checked.value = []
    elapsedSeconds.value = []
    currentIndex.value = 0
    multiplier.value = 1
    startedAt.value = null
    activeSince.value = null
  }

  function loadFromProgress(data) {
    bonusWindowSeconds.value = data.bonusWindowSeconds
    questions.value = data.questions
    answers.value = data.answers
    checked.value = data.checked
    elapsedSeconds.value = data.elapsedSeconds || []
    currentIndex.value = data.index || 0
    multiplier.value = data.multiplier || 1
    startedAt.value = data.startedAt
  }

  function pauseBonusTracking() {
    if (activeSince.value == null) return
    const qi = currentIndex.value
    const committed = elapsedSeconds.value[qi] || 0
    elapsedSeconds.value[qi] = committed + (Date.now() - activeSince.value) / 1000
    activeSince.value = null
  }

  function resumeBonusTracking() {
    activeSince.value = Date.now()
  }

  function currentElapsed() {
    const qi = currentIndex.value
    const committed = elapsedSeconds.value[qi] || 0
    return activeSince.value != null ? committed + (Date.now() - activeSince.value) / 1000 : committed
  }

  function computeAwardedPoints(question, isCorrect) {
    if (!isCorrect) return 0
    const elapsed = currentElapsed()
    const bonus = elapsed < bonusWindowSeconds.value
      ? Math.round(question.points * (1 - elapsed / bonusWindowSeconds.value))
      : 0
    return (question.points + bonus) * Math.min(multiplier.value, MULTIPLIER_MAX)
  }

  function advanceMultiplier(isCorrect) {
    if (isCorrect) {
      multiplier.value = Math.min(multiplier.value + 1, MULTIPLIER_MAX)
    } else {
      multiplier.value = 1
    }
  }

  return {
    examId, examName, bonusWindowSeconds, questions, answers, checked,
    elapsedSeconds, currentIndex, multiplier, startedAt, activeSince,
    currentQuestion, isFinished,
    reset, loadFromProgress, pauseBonusTracking, resumeBonusTracking,
    currentElapsed, computeAwardedPoints, advanceMultiplier,
  }
})
