<template>
  <div ref="root"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'

const props = defineProps({
  modelValue: { type: String, default: '' },
  toolbar: {
    type: Array,
    default: () => [['bold', 'italic', 'underline'], [{ list: 'ordered' }, { list: 'bullet' }], ['link']],
  },
})
const emit = defineEmits(['update:modelValue'])

const root = ref(null)
let quill = null
let settingValue = false

const EMPTY = '<p><br></p>'

onMounted(() => {
  quill = new Quill(root.value, { theme: 'snow', modules: { toolbar: props.toolbar } })
  if (props.modelValue) quill.clipboard.dangerouslyPasteHTML(props.modelValue)
  quill.on('text-change', () => {
    if (settingValue) return
    const html = quill.root.innerHTML
    emit('update:modelValue', html === EMPTY ? '' : html)
  })
})

onBeforeUnmount(() => { quill = null })

watch(() => props.modelValue, (val) => {
  if (!quill) return
  const current = quill.root.innerHTML
  if (val === (current === EMPTY ? '' : current)) return
  settingValue = true
  quill.clipboard.dangerouslyPasteHTML(val ?? '')
  settingValue = false
})
</script>

<style scoped>
:deep(.ql-toolbar.ql-snow) {
  border: 1px solid var(--outline-border);
  border-bottom: none;
  border-radius: 0.375rem 0.375rem 0 0;
  background: var(--input-bg);
}
:deep(.ql-container.ql-snow) {
  border: 1px solid var(--outline-border);
  border-radius: 0 0 0.375rem 0.375rem;
  background: var(--input-bg);
  font-family: inherit;
  font-size: 1rem;
}
:deep(.ql-editor) {
  color: var(--text);
  min-height: 80px;
}
:deep(.ql-editor.ql-blank::before) {
  color: var(--placeholder);
  font-style: normal;
}
:deep(.ql-snow .ql-stroke) { stroke: var(--text-muted); }
:deep(.ql-snow .ql-fill) { fill: var(--text-muted); }
:deep(.ql-snow .ql-picker) { color: var(--text-muted); }
:deep(.ql-toolbar.ql-snow button:hover .ql-stroke),
:deep(.ql-toolbar.ql-snow button.ql-active .ql-stroke) { stroke: var(--accent-primary); }
:deep(.ql-toolbar.ql-snow button:hover .ql-fill),
:deep(.ql-toolbar.ql-snow button.ql-active .ql-fill) { fill: var(--accent-primary); }
:deep(.ql-snow .ql-picker-options) {
  background: var(--bg-glow);
  border-color: var(--outline-border);
  color: var(--text);
}
</style>
