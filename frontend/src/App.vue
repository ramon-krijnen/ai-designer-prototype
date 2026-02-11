<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

const prompt = ref('')
const isLoading = ref(false)
const error = ref('')
const images = ref([])
const revisedPrompt = ref('')
const activeTab = ref('generate')
const provider = ref('openai')
const size = ref('1024x1024')
const steps = ref('28')
const quality = ref('')
const selectedModels = ref([])

const providerOptions = ref({})

const archiveRuns = ref([])
const archiveError = ref('')
const isArchiveLoading = ref(false)
const archiveOffset = ref(0)
const archivePageSize = 24
const hasMoreArchive = ref(true)
const archiveInitialized = ref(false)
const lightboxImage = ref(null)

const imageCount = computed(() => images.value.length)
const archiveCount = computed(() => archiveRuns.value.length)
const isBusy = computed(() => isLoading.value || isArchiveLoading.value)
const currentProviderOption = computed(() => providerOptions.value[provider.value] || null)
const providerNames = computed(() => Object.keys(providerOptions.value))
const currentModelOptions = computed(() => currentProviderOption.value?.models || [])
const currentSizeOptions = computed(() => currentProviderOption.value?.sizes || [])
const currentQualityOptions = computed(() => currentProviderOption.value?.qualities || [])
const currentSupportsSteps = computed(() => Boolean(currentProviderOption.value?.supports_steps))

function normalizeImageSource(value, mimeType = 'image/png') {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null

  if (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('data:') ||
    trimmed.startsWith('blob:')
  ) {
    return trimmed
  }

  if (trimmed.startsWith('/')) {
    return API_BASE_URL ? `${API_BASE_URL}${trimmed}` : trimmed
  }

  if (API_BASE_URL && (trimmed.startsWith('./') || trimmed.startsWith('../'))) {
    try {
      return new URL(trimmed, `${API_BASE_URL}/`).toString()
    } catch {
      return null
    }
  }

  if (/^[A-Za-z0-9+/=\s]+$/.test(trimmed)) {
    return `data:${mimeType};base64,${trimmed}`
  }

  return null
}

function dedupeImages(items) {
  const seen = new Set()
  return items.filter((item) => {
    if (!item?.src || seen.has(item.src)) return false
    seen.add(item.src)
    return true
  })
}

function parseImageCandidate(candidate, index) {
  if (typeof candidate === 'string') {
    const src = normalizeImageSource(candidate)
    return src ? { src, alt: `Generated image ${index + 1}` } : null
  }
  if (!candidate || typeof candidate !== 'object') return null

  const mimeType = candidate.mime_type || candidate.content_type || 'image/png'
  const src =
    normalizeImageSource(candidate.url) ||
    normalizeImageSource(candidate.src) ||
    normalizeImageSource(candidate.image_url) ||
    normalizeImageSource(candidate.image_base64, mimeType) ||
    normalizeImageSource(candidate.b64_json, mimeType) ||
    normalizeImageSource(candidate.base64, mimeType)

  if (!src) return null
  return { src, alt: candidate.alt || `Generated image ${index + 1}` }
}

function formatTimestamp(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toLocaleString()
}

function parseStoredImageRecord(record, index) {
  if (!record || typeof record !== 'object') return null
  const parsed = parseImageCandidate(record, index)
  if (!parsed) return null

  return {
    ...parsed,
    id: typeof record.id === 'string' ? record.id : `archived-${index}`,
    runId: typeof record.run_id === 'string' ? record.run_id : '',
    prompt: typeof record.prompt === 'string' ? record.prompt.trim() : '',
    provider: typeof record.provider === 'string' ? record.provider.trim() : '',
    model: typeof record.model === 'string' ? record.model.trim() : '',
    createdAt: formatTimestamp(record.created_at),
  }
}

function parseRunRecord(run, index) {
  if (!run || typeof run !== 'object') return null
  const runId = typeof run.run_id === 'string' ? run.run_id : `run-${index}`
  const createdAt = formatTimestamp(run.created_at)
  const imagesForRun = Array.isArray(run.images)
    ? run.images.map((item, imageIndex) => parseStoredImageRecord(item, imageIndex)).filter(Boolean)
    : []
  return {
    runId,
    createdAt,
    imageCount: typeof run.image_count === 'number' ? run.image_count : imagesForRun.length,
    images: imagesForRun,
  }
}

function extractImages(payload, extra = {}) {
  const candidates = []

  // For this backend contract, a single generation may include both image_url and image_base64.
  // Prefer one canonical source to avoid rendering the same image twice.
  const singleImageCandidate = payload?.image_url || payload?.image_base64 || payload?.b64_json
  if (singleImageCandidate) {
    candidates.push(singleImageCandidate)
  }

  if (Array.isArray(payload?.images)) candidates.push(...payload.images)
  if (Array.isArray(payload?.data)) candidates.push(...payload.data)
  if (Array.isArray(payload?.image_urls)) candidates.push(...payload.image_urls)

  return dedupeImages(
    candidates
      .map((item, index) => parseImageCandidate(item, index))
      .filter(Boolean)
      .map((image) => ({ ...image, ...extra })),
  )
}

async function generateImages() {
  const trimmedPrompt = prompt.value.trim()
  if (!trimmedPrompt || isBusy.value) return
  const enabledModels = currentModelOptions.value
    .map((option) => option.id)
    .filter((id) => selectedModels.value.includes(id))

  isLoading.value = true
  error.value = ''
  revisedPrompt.value = ''
  activeTab.value = 'generate'
  images.value = []

  try {
    if (!enabledModels.length) {
      throw new Error('Select at least one model.')
    }

    const response = await fetch(`${API_BASE_URL}/api/images/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: trimmedPrompt,
        provider: provider.value,
        models: enabledModels,
        size: size.value.trim() || undefined,
        quality: quality.value || undefined,
        steps: steps.value.trim() ? Number.parseInt(steps.value, 10) : undefined,
      }),
    })

    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Request failed.')
    }

    if (payload.revised_prompt) {
      revisedPrompt.value = payload.revised_prompt
    }

    images.value = extractImages(payload)

    if (!images.value.length) {
      throw new Error('No images were returned by the API.')
    }
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : 'Unexpected error.'
  } finally {
    isLoading.value = false
  }
}

async function loadArchivePage({ reset = false } = {}) {
  if (isArchiveLoading.value) return

  isArchiveLoading.value = true
  archiveError.value = ''

  try {
    const nextOffset = reset ? 0 : archiveOffset.value
    const response = await fetch(`${API_BASE_URL}/api/runs?limit=${archivePageSize}&offset=${nextOffset}`)
    const payload = await response.json().catch(() => [])

    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Failed to load archive.')
    }
    if (!Array.isArray(payload)) {
      throw new Error('Unexpected response when loading archive.')
    }

    const parsed = payload.map((item, index) => parseRunRecord(item, nextOffset + index)).filter(Boolean)
    archiveRuns.value = reset ? parsed : [...archiveRuns.value, ...parsed]
    archiveOffset.value = nextOffset + payload.length
    hasMoreArchive.value = payload.length === archivePageSize
    archiveInitialized.value = true
  } catch (requestError) {
    archiveError.value = requestError instanceof Error ? requestError.message : 'Unexpected error.'
  } finally {
    isArchiveLoading.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab !== 'archive' || archiveInitialized.value) return
  loadArchivePage({ reset: true })
})

function resetProviderDefaults(nextProvider) {
  const options = providerOptions.value[nextProvider]
  if (!options) return

  const models = Array.isArray(options.models) ? options.models.map((item) => item.id || item).filter(Boolean) : []
  selectedModels.value = models

  const sizes = Array.isArray(options.sizes) ? options.sizes : []
  size.value = sizes[0] || ''

  const qualities = Array.isArray(options.qualities) ? options.qualities : []
  quality.value = qualities[0] || ''

  const defaultSteps = options.default_steps
  steps.value = defaultSteps ? String(defaultSteps) : '28'
}

watch(provider, (nextProvider) => {
  resetProviderDefaults(nextProvider)
})

async function loadProviderOptions() {
  const response = await fetch(`${API_BASE_URL}/api/providers`)
  const payload = await response.json().catch(() => ({}))

  if (!response.ok || !payload || typeof payload !== 'object') {
    throw new Error('Failed to load provider options')
  }

  providerOptions.value = payload
  const firstProvider = Object.keys(providerOptions.value)[0]
  if (firstProvider) {
    provider.value = firstProvider
    resetProviderDefaults(firstProvider)
  }
}

onMounted(async () => {
  try {
    await loadProviderOptions()
  } catch (providerError) {
    error.value = providerError instanceof Error ? providerError.message : 'Failed to load providers.'
  }
})

function openLightbox(image) {
  if (!image?.src) return
  lightboxImage.value = image
}

function closeLightbox() {
  lightboxImage.value = null
}
</script>

<template>
  <main class="app-shell">
    <section class="panel">
      <h1>AI Image Playground</h1>
      <p class="subtitle">Generate images, then browse complete run history in Archive.</p>

      <div class="tabs" role="tablist" aria-label="Image tools">
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'generate' }"
          role="tab"
          :aria-selected="activeTab === 'generate'"
          @click="activeTab = 'generate'"
        >
          Generate
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'archive' }"
          role="tab"
          :aria-selected="activeTab === 'archive'"
          @click="activeTab = 'archive'"
        >
          Archive
        </button>
      </div>

      <form v-if="activeTab === 'generate'" class="prompt-form" @submit.prevent="generateImages">
        <div class="provider-controls">
          <div class="control-field">
            <label class="prompt-label" for="provider-select">Provider</label>
            <select id="provider-select" v-model="provider" :disabled="isBusy">
              <option v-for="name in providerNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </div>

          <div class="control-field">
            <label class="prompt-label">Models</label>
            <div class="model-checklist">
              <label v-for="option in currentModelOptions" :key="option.id" class="check-item">
                <input v-model="selectedModels" type="checkbox" :value="option.id" :disabled="isBusy" />
                <span>{{ option.label || option.id }}</span>
              </label>
            </div>
          </div>

          <div class="control-field">
            <label class="prompt-label" for="size-input">Size</label>
            <select id="size-input" v-model="size" :disabled="isBusy || !currentSizeOptions.length">
              <option v-for="option in currentSizeOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </div>

          <div class="control-field" v-if="currentQualityOptions.length">
            <label class="prompt-label" for="quality-input">Quality</label>
            <select id="quality-input" v-model="quality" :disabled="isBusy">
              <option v-for="option in currentQualityOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </div>

          <div class="control-field" v-if="currentSupportsSteps">
            <label class="prompt-label" for="steps-input">Steps</label>
            <input id="steps-input" v-model="steps" type="number" min="1" placeholder="28" :disabled="isBusy" />
          </div>
        </div>

        <label class="prompt-label" for="prompt-input">Prompt</label>
        <textarea
          id="prompt-input"
          v-model="prompt"
          placeholder="e.g. A futuristic city skyline at sunrise, cinematic lighting"
          rows="4"
          :disabled="isBusy"
        />
        <button type="submit" :disabled="isBusy || !prompt.trim()">
          {{ isLoading ? 'Generating...' : 'Generate Images' }}
        </button>
      </form>

      <div v-else class="archive-toolbar">
        <button type="button" class="secondary" :disabled="isArchiveLoading" @click="loadArchivePage({ reset: true })">
          {{ isArchiveLoading ? 'Refreshing...' : 'Refresh Archive' }}
        </button>
        <span class="archive-count">{{ archiveCount }} run{{ archiveCount === 1 ? '' : 's' }} loaded</span>
      </div>

      <p v-if="activeTab === 'generate' && error" class="message error">{{ error }}</p>
      <p v-else-if="activeTab === 'generate' && revisedPrompt" class="message info">Revised prompt: {{ revisedPrompt }}</p>
      <p v-if="activeTab === 'archive' && archiveError" class="message error">{{ archiveError }}</p>
    </section>

    <section v-if="activeTab === 'generate'" class="results">
      <div class="results-header">
        <h2>Results</h2>
        <span v-if="imageCount">{{ imageCount }} image{{ imageCount === 1 ? '' : 's' }}</span>
      </div>

      <p v-if="!imageCount && !isBusy" class="empty-state">
        No images yet. Submit a prompt to get started.
      </p>

      <div v-if="imageCount" class="image-grid">
        <article v-for="(image, index) in images" :key="`${image.src}-${index}`" class="image-card">
          <img :src="image.src" :alt="image.alt" class="clickable-image" loading="lazy" @click="openLightbox(image)" />
          <div v-if="image.provider || image.model" class="image-meta">
            <p class="image-details">
              <span v-if="image.provider">{{ image.provider }}</span>
              <span v-if="image.provider && image.model"> / </span>
              <span v-if="image.model">{{ image.model }}</span>
            </p>
          </div>
        </article>
      </div>
    </section>

    <section v-else class="results">
      <div class="results-header">
        <h2>Archive</h2>
        <span v-if="archiveCount">{{ archiveCount }} run{{ archiveCount === 1 ? '' : 's' }}</span>
      </div>

      <p v-if="!archiveCount && !isArchiveLoading && !archiveError" class="empty-state">
        No archived runs found yet.
      </p>

      <div v-if="archiveCount" class="run-list">
        <article v-for="(run, runIndex) in archiveRuns" :key="`${run.runId}-${runIndex}`" class="run-block">
          <div class="run-header">
            <p class="image-id">Run: {{ run.runId }}</p>
            <p class="image-details">
              <span>{{ run.imageCount }} image{{ run.imageCount === 1 ? '' : 's' }}</span>
              <span v-if="run.createdAt"> · {{ run.createdAt }}</span>
            </p>
          </div>

          <div class="image-grid">
            <article v-for="(image, imageIndex) in run.images" :key="`${image.id}-${imageIndex}`" class="image-card">
              <img
                :src="image.src"
                :alt="image.alt"
                class="clickable-image"
                loading="lazy"
                @click="openLightbox(image)"
              />
              <div class="image-meta">
                <p v-if="image.prompt" class="image-prompt">{{ image.prompt }}</p>
                <p class="image-details">
                  <span v-if="image.provider">{{ image.provider }}</span>
                  <span v-if="image.provider && image.model"> / </span>
                  <span v-if="image.model">{{ image.model }}</span>
                </p>
              </div>
            </article>
          </div>
        </article>
      </div>

      <div class="archive-actions">
        <button type="button" class="secondary" :disabled="isArchiveLoading || !hasMoreArchive" @click="loadArchivePage()">
          {{
            isArchiveLoading
              ? 'Loading...'
              : hasMoreArchive
                ? `Load More (${archivePageSize})`
                : 'All Runs Loaded'
          }}
        </button>
      </div>
    </section>

    <div v-if="lightboxImage" class="lightbox" @click.self="closeLightbox">
      <button type="button" class="lightbox-close" @click="closeLightbox">Close</button>
      <img :src="lightboxImage.src" :alt="lightboxImage.alt || 'Preview image'" class="lightbox-image" />
    </div>
  </main>
</template>

<style scoped>
.app-shell {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1rem 3rem;
  display: grid;
  gap: 1.25rem;
}

.panel,
.results {
  background: #ffffff;
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  padding: 1rem;
}

h1 {
  font-size: 1.5rem;
  margin-bottom: 0.2rem;
  color: #11284f;
}

.subtitle {
  color: #4b5f85;
  margin-bottom: 1rem;
}

.tabs {
  display: flex;
  gap: 0.55rem;
  margin-bottom: 0.85rem;
}

.tab-btn {
  background: #eff5ff;
  border: 1px solid #b9c9e3;
  color: #20457d;
  border-radius: 999px;
  padding: 0.4rem 0.9rem;
  font-weight: 600;
}

.tab-btn.active {
  background: #0e4cb3;
  border-color: #0e4cb3;
  color: #ffffff;
}

.prompt-form {
  display: grid;
  gap: 0.75rem;
}

.provider-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.7rem;
}

.control-field {
  display: grid;
  gap: 0.35rem;
}

.model-checklist {
  display: grid;
  gap: 0.35rem;
  border: 1px solid #b9c9e3;
  border-radius: 10px;
  padding: 0.5rem 0.6rem;
  background: #ffffff;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #1f3f73;
  font-size: 0.92rem;
}

.check-item input {
  width: auto;
}

.archive-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.archive-count {
  color: #516b94;
  font-size: 0.9rem;
}

.prompt-label {
  font-weight: 600;
  color: #203a67;
}

textarea {
  width: 100%;
  border: 1px solid #b9c9e3;
  border-radius: 10px;
  padding: 0.75rem;
  font: inherit;
  resize: vertical;
  min-height: 110px;
}

input,
select {
  width: 100%;
  border: 1px solid #b9c9e3;
  border-radius: 10px;
  padding: 0.55rem 0.7rem;
  font: inherit;
  background: #ffffff;
}

textarea:focus {
  outline: 2px solid #6aa6ff;
  outline-offset: 1px;
}

button {
  justify-self: start;
  background: #0e4cb3;
  color: #ffffff;
  border: 0;
  border-radius: 10px;
  padding: 0.6rem 1rem;
  font-weight: 600;
  cursor: pointer;
}

button:disabled {
  background: #7894c0;
  cursor: not-allowed;
}

button.secondary {
  background: #eaf1ff;
  color: #194790;
  border: 1px solid #b9c9e3;
}

button.secondary:disabled {
  background: #f2f5fb;
  color: #7f92b4;
}

.message {
  margin-top: 0.9rem;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
}

.error {
  background: #ffe8e8;
  color: #8b1c1c;
  border: 1px solid #ffc7c7;
}

.info {
  background: #eaf4ff;
  color: #1e4f8f;
  border: 1px solid #c3ddff;
}

.results-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0.8rem;
}

h2 {
  font-size: 1.2rem;
  color: #11284f;
}

.empty-state {
  color: #5b6f93;
}


.run-list {
  display: grid;
  gap: 0.9rem;
}

.run-block {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  padding: 0.8rem;
  background: #f7faff;
}

.run-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.65rem;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.9rem;
}

.image-card {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  overflow: hidden;
  background: #f4f8ff;
}

.image-card img {
  width: 100%;
  display: block;
  aspect-ratio: 1 / 1;
  object-fit: cover;
}

.clickable-image {
  cursor: zoom-in;
}

.image-meta {
  padding: 0.65rem 0.75rem 0.75rem;
  background: #ffffff;
}

.image-prompt {
  margin: 0;
  color: #163869;
  font-size: 0.9rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.image-details {
  margin: 0.45rem 0 0;
  color: #58719b;
  font-size: 0.8rem;
}

.image-id {
  margin: 0.35rem 0 0;
  color: #7f94b8;
  font-size: 0.75rem;
}

.archive-actions {
  margin-top: 1rem;
  display: flex;
  justify-content: center;
}

.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(8, 19, 38, 0.85);
  z-index: 30;
  display: grid;
  place-items: center;
  padding: 2rem;
}

.lightbox-image {
  max-width: min(95vw, 1600px);
  max-height: 88vh;
  width: auto;
  height: auto;
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
}

.lightbox-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: #ffffff;
  color: #173564;
  border: 1px solid #b7c7e3;
}

@media (min-width: 860px) {
  .app-shell {
    padding: 2rem 1.25rem 3rem;
  }

  .panel,
  .results {
    padding: 1.25rem;
  }
}
</style>
