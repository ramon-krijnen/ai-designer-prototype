<script setup>
import { computed, ref } from 'vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

const prompt = ref('')
const isLoading = ref(false)
const isLoadingExisting = ref(false)
const error = ref('')
const images = ref([])
const revisedPrompt = ref('')
const debugLimit = ref(4)
const resultSource = ref('none')

const imageCount = computed(() => images.value.length)
const isBusy = computed(() => isLoading.value || isLoadingExisting.value)

function normalizeImageSource(value, mimeType = 'image/png') {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null

  // Keep absolute and browser-native URL schemes unchanged.
  if (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('data:') ||
    trimmed.startsWith('blob:')
  ) {
    return trimmed
  }

  // Support API responses that return root-relative paths such as /api/images/<id>/file.
  if (trimmed.startsWith('/')) {
    return API_BASE_URL ? `${API_BASE_URL}${trimmed}` : trimmed
  }

  // If an API base URL is configured and we got a relative path, resolve it against that base.
  if (API_BASE_URL && (trimmed.startsWith('./') || trimmed.startsWith('../'))) {
    try {
      return new URL(trimmed, `${API_BASE_URL}/`).toString()
    } catch {
      return null
    }
  }

  // Fallback to raw base64 payloads.
  if (/^[A-Za-z0-9+/=\s]+$/.test(trimmed)) {
    return `data:${mimeType};base64,${trimmed}`
  }

  // Unknown format.
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
    prompt: typeof record.prompt === 'string' ? record.prompt.trim() : '',
    provider: typeof record.provider === 'string' ? record.provider.trim() : '',
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
  resultSource.value = 'generate'
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

async function loadExistingImages() {
  if (isBusy.value) return

  isLoadingExisting.value = true
  error.value = ''
  revisedPrompt.value = ''
  resultSource.value = 'existing'
  images.value = []

  try {
    const response = await fetch(`${API_BASE_URL}/api/images?limit=${debugLimit.value}&offset=0`)
    const payload = await response.json().catch(() => [])

    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Failed to load existing images.')
    }

    if (!Array.isArray(payload)) {
      throw new Error('Unexpected response when loading existing images.')
    }

    images.value = dedupeImages(payload.map((item, index) => parseStoredImageRecord(item, index)).filter(Boolean))

    if (!images.value.length) {
      throw new Error('No stored images found in the database yet.')
    }
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : 'Unexpected error.'
  } finally {
    isLoadingExisting.value = false
  }
}
</script>

<template>
  <main class="app-shell">
    <section class="panel">
      <h1>AI Image Playground</h1>
      <p class="subtitle">Enter a prompt to generate images from the backend API.</p>

      <form class="prompt-form" @submit.prevent="generateImages">
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

      <div class="debug-tools">
        <label for="debug-count">Debug from DB</label>
        <select id="debug-count" v-model.number="debugLimit" :disabled="isBusy">
          <option :value="1">1 image</option>
          <option :value="4">4 images</option>
          <option :value="8">8 images</option>
          <option :value="16">16 images</option>
        </select>
        <button type="button" class="secondary" :disabled="isBusy" @click="loadExistingImages">
          {{ isLoadingExisting ? 'Loading...' : 'Load Existing Images' }}
        </button>
      </div>

      <p v-if="error" class="message error">{{ error }}</p>
      <p v-else-if="revisedPrompt" class="message info">Revised prompt: {{ revisedPrompt }}</p>
    </section>

    <section class="results">
      <div class="results-header">
        <h2>Results</h2>
        <span v-if="imageCount">
          {{ imageCount }} image{{ imageCount === 1 ? '' : 's' }}
          <template v-if="resultSource === 'existing'"> from DB</template>
        </span>
      </div>

      <p v-if="!imageCount && !isBusy" class="empty-state">
        No images yet. Submit a prompt to get started.
      </p>

      <div v-if="imageCount" class="image-grid">
        <article v-for="(image, index) in images" :key="`${image.src}-${index}`" class="image-card">
          <img :src="image.src" :alt="image.alt" loading="lazy" />
          <div v-if="image.prompt || image.provider || image.createdAt" class="image-meta">
            <p v-if="image.prompt" class="image-prompt">{{ image.prompt }}</p>
            <p v-if="image.provider || image.createdAt" class="image-details">
              <span v-if="image.provider">{{ image.provider }}</span>
              <span v-if="image.provider && image.createdAt"> · </span>
              <span v-if="image.createdAt">{{ image.createdAt }}</span>
            </p>
          </div>
        </article>
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

.prompt-form {
  display: grid;
  gap: 0.75rem;
}

.debug-tools {
  margin-top: 0.8rem;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.debug-tools label {
  color: #203a67;
  font-weight: 600;
}

.debug-tools select {
  border: 1px solid #b9c9e3;
  border-radius: 8px;
  padding: 0.4rem 0.55rem;
  font: inherit;
  background: #ffffff;
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
