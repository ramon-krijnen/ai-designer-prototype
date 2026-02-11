<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const emit = defineEmits(['close'])

function close() {
  emit('close')
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})

const props = defineProps({
  image: {
    type: Object,
    required: true,
  },
})

const imageRef = ref(null)
const promptBodyRef = ref(null)
const isPromptExpanded = ref(false)
const hasPromptOverflow = ref(false)
const syncedPanelHeight = ref(null)

const promptText = computed(() => {
  if (typeof props.image.prompt !== 'string') return ''
  return props.image.prompt.trim()
})

const metadataPanelStyle = computed(() => {
  if (!syncedPanelHeight.value) return {}
  const height = `${syncedPanelHeight.value}px`
  return {
    height,
    maxHeight: height,
  }
})

function syncPanelHeight() {
  if (!window.matchMedia('(min-width: 980px)').matches) {
    syncedPanelHeight.value = null
    return
  }
  const imageElement = imageRef.value
  if (!imageElement) return
  const measuredHeight = Math.round(imageElement.getBoundingClientRect().height)
  if (measuredHeight > 0) {
    syncedPanelHeight.value = measuredHeight
  }
}

function updatePromptOverflow() {
  const promptBody = promptBodyRef.value
  if (!promptBody || isPromptExpanded.value) return
  hasPromptOverflow.value = promptBody.scrollHeight > promptBody.clientHeight + 1
}

function togglePromptExpanded() {
  isPromptExpanded.value = !isPromptExpanded.value
  if (!isPromptExpanded.value) {
    nextTick(() => {
      updatePromptOverflow()
    })
  }
}

function handleImageLoad() {
  syncPanelHeight()
  nextTick(() => {
    updatePromptOverflow()
  })
}

const metadataRows = computed(() => {
  const rows = [
    { label: 'Model', value: props.image.model },
    { label: 'Provider', value: props.image.provider },
    { label: 'Created', value: props.image.createdAt },
    { label: 'Size', value: props.image.size },
    { label: 'Quality', value: props.image.quality },
    { label: 'Image ID', value: props.image.imageId || props.image.id },
    { label: 'Run ID', value: props.image.runId },
    { label: 'SHA256', value: props.image.sha256 },
  ]
  return rows.filter((row) => typeof row.value === 'string' && row.value.trim())
})

watch(
  () => props.image.prompt,
  async () => {
    isPromptExpanded.value = false
    await nextTick()
    syncPanelHeight()
    updatePromptOverflow()
  },
  { immediate: true },
)

function handleResize() {
  syncPanelHeight()
  updatePromptOverflow()
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  nextTick(() => {
    syncPanelHeight()
    updatePromptOverflow()
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <div class="lightbox" @click.self="close">
    <button type="button" class="lightbox-close" @click="close">Close</button>
    <div class="lightbox-content">
      <div class="lightbox-columns">
        <div class="image-wrap">
          <img
            ref="imageRef"
            :src="props.image.src"
            :alt="props.image.alt || 'Preview image'"
            class="lightbox-image"
            @load="handleImageLoad"
          />
        </div>

        <div class="metadata-panel" :style="metadataPanelStyle">
          <h3>Image Details</h3>

          <p v-if="props.image.revisedPrompt" class="metadata-revised">
            <span>Revised prompt:</span> {{ props.image.revisedPrompt }}
          </p>

          <dl class="metadata-list">
            <template v-for="row in metadataRows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </template>
          </dl>

          <section v-if="promptText" class="prompt-section">
            <div class="prompt-header">
              <h4>Prompt</h4>
              <button
                v-if="hasPromptOverflow"
                type="button"
                class="prompt-toggle"
                @click="togglePromptExpanded"
              >
                {{ isPromptExpanded ? 'Collapse' : 'Expand' }}
              </button>
            </div>
            <div ref="promptBodyRef" class="prompt-content" :class="{ expanded: isPromptExpanded }">{{ promptText }}</div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(8, 19, 38, 0.85);
  z-index: 30;
  display: flex;
  align-items: stretch;
  justify-content: center;
  padding: 1rem;
}

.lightbox-content {
  width: min(1200px, 96vw);
  align-content: center;
  max-height: 94vh;
}

.lightbox-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.85rem;
  align-items: start;
}

.image-wrap {
  display: grid;
  place-items: center;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
}

.lightbox-image {
  max-width: 100%;
  max-height: 72vh;
  width: auto;
  height: auto;
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
}

.metadata-panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #c6d5ef;
  padding: 0.9rem;
  overflow: auto;
}

.metadata-panel h3 {
  margin: 0;
  color: #10284f;
  font-size: 1rem;
}

.metadata-revised {
  margin: 0.7rem 0 0;
  color: #2f4f7f;
  font-size: 0.85rem;
  line-height: 1.35;
}

.metadata-revised span {
  font-weight: 600;
}

.metadata-list {
  margin: 0.8rem 0 0;
  display: grid;
  gap: 0.45rem;
}

.metadata-list dt {
  font-size: 0.72rem;
  color: #4d6892;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.metadata-list dd {
  margin: 0;
  color: #172f56;
  font-size: 0.88rem;
  overflow-wrap: anywhere;
}

.prompt-section {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #d7e2f3;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
}

.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.prompt-header h4 {
  margin: 0;
  color: #10284f;
  font-size: 0.9rem;
}

.prompt-toggle {
  border: 1px solid #b7c7e3;
  background: #f4f8ff;
  color: #1f4178;
  border-radius: 8px;
  padding: 0.2rem 0.55rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}

.prompt-content {
  margin-top: 0.55rem;
  border: 1px solid #d7e2f3;
  border-radius: 10px;
  background: #f8fbff;
  color: #163869;
  font-size: 0.88rem;
  line-height: 1.4;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 0.65rem 0.75rem;
  flex: 1 1 auto;
  min-height: 6rem;
  overflow: hidden;
}

.prompt-content.expanded {
  overflow-y: auto;
}

.lightbox-close {
  position: absolute;
  top: 0.9rem;
  right: 0.9rem;
  background: #ffffff;
  color: #173564;
  border: 1px solid #b7c7e3;
  border-radius: 10px;
  padding: 0.55rem 0.8rem;
  font-weight: 600;
  cursor: pointer;
}

@media (min-width: 980px) {
  .lightbox {
    padding: 1.4rem;
  }

  .lightbox-content {
    height: 100%;
  }

  .lightbox-columns {
    grid-template-columns: minmax(0, 1fr) 330px;
    gap: 1rem;
    align-items: start;
  }

  .lightbox-image {
    max-height: 90vh;
  }
}
</style>
