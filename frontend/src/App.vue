<script setup>
import { computed, ref, watch } from 'vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

const prompt = ref('')
const isLoading = ref(false)
const error = ref('')
const images = ref([])
const revisedPrompt = ref('')
const activeTab = ref('generate')

const archiveRuns = ref([])
const archiveError = ref('')
const isArchiveLoading = ref(false)
const archiveOffset = ref(0)
const archivePageSize = 24
const hasMoreArchive = ref(true)
const archiveInitialized = ref(false)

const imageCount = computed(() => images.value.length)
const archiveCount = computed(() => archiveRuns.value.length)
const isBusy = computed(() => isLoading.value || isArchiveLoading.value)

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
    prompt: typeof record.prompt === 'string' ? record.prompt.trim() : '',
    provider: typeof record.provider === 'string' ? record.provider.trim() : '',
    model: typeof record.model === 'string' ? record.model.trim() : '',
    createdAt: formatTimestamp(record.created_at),
  }
}

function extractImages(payload) {
  const candidates = []

  if (Array.isArray(payload?.images)) candidates.push(...payload.images)
  if (Array.isArray(payload?.data)) candidates.push(...payload.data)
  if (Array.isArray(payload?.image_urls)) candidates.push(...payload.image_urls)
  if (payload?.image_url) candidates.push(payload.image_url)
  if (payload?.image_base64) candidates.push(payload.image_base64)
  if (payload?.b64_json) candidates.push(payload.b64_json)

  return dedupeImages(candidates.map((item, index) => parseImageCandidate(item, index)).filter(Boolean))
}

async function generateImages() {
  const trimmedPrompt = prompt.value.trim()
  if (!trimmedPrompt || isBusy.value) return

  isLoading.value = true
  error.value = ''
  revisedPrompt.value = ''
  activeTab.value = 'generate'
  images.value = []

  try {
    const response = await fetch(`${API_BASE_URL}/api/images/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ prompt: trimmedPrompt }),
    })

    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Request failed.')
    }

    revisedPrompt.value = payload.revised_prompt || ''
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
    const response = await fetch(`${API_BASE_URL}/api/images?limit=${archivePageSize}&offset=${nextOffset}`)
    const payload = await response.json().catch(() => [])

    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Failed to load archive.')
    }
    if (!Array.isArray(payload)) {
      throw new Error('Unexpected response when loading archive.')
    }

    const parsed = payload.map((item, index) => parseStoredImageRecord(item, nextOffset + index)).filter(Boolean)
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
          <img :src="image.src" :alt="image.alt" loading="lazy" />
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

      <div v-if="archiveCount" class="image-grid">
        <article v-for="(run, index) in archiveRuns" :key="`${run.id}-${index}`" class="image-card">
          <img :src="run.src" :alt="run.alt" loading="lazy" />
          <div class="image-meta">
            <p v-if="run.prompt" class="image-prompt">{{ run.prompt }}</p>
            <p class="image-details">
              <span v-if="run.provider">{{ run.provider }}</span>
              <span v-if="run.provider && run.model"> / </span>
              <span v-if="run.model">{{ run.model }}</span>
              <span v-if="(run.provider || run.model) && run.createdAt"> · </span>
              <span v-if="run.createdAt">{{ run.createdAt }}</span>
            </p>
            <p class="image-id">Run: {{ run.id }}</p>
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

.image-meta {
  padding: 0.65rem 0.75rem 0.75rem;
  background: #ffffff;
}

.image-prompt {
  margin: 0;
  color: #163869;
  font-size: 0.9rem;
  line-height: 1.35;
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
