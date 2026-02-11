<script setup>
import { computed, ref } from 'vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

const prompt = ref('')
const isLoading = ref(false)
const error = ref('')
const images = ref([])
const revisedPrompt = ref('')

const imageCount = computed(() => images.value.length)

function normalizeImageSource(value, mimeType = 'image/png') {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('data:')) {
    return trimmed
  }
  return `data:${mimeType};base64,${trimmed}`
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

function extractImages(payload) {
  const candidates = []

  if (Array.isArray(payload?.images)) candidates.push(...payload.images)
  if (Array.isArray(payload?.data)) candidates.push(...payload.data)
  if (Array.isArray(payload?.image_urls)) candidates.push(...payload.image_urls)
  if (payload?.image_url) candidates.push(payload.image_url)
  if (payload?.image_base64) candidates.push(payload.image_base64)
  if (payload?.b64_json) candidates.push(payload.b64_json)

  return candidates
    .map((item, index) => parseImageCandidate(item, index))
    .filter(Boolean)
}

async function generateImages() {
  const trimmedPrompt = prompt.value.trim()
  if (!trimmedPrompt || isLoading.value) return

  isLoading.value = true
  error.value = ''
  revisedPrompt.value = ''
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
          :disabled="isLoading"
        />
        <button type="submit" :disabled="isLoading || !prompt.trim()">
          {{ isLoading ? 'Generating...' : 'Generate Images' }}
        </button>
      </form>

      <p v-if="error" class="message error">{{ error }}</p>
      <p v-else-if="revisedPrompt" class="message info">Revised prompt: {{ revisedPrompt }}</p>
    </section>

    <section class="results">
      <div class="results-header">
        <h2>Results</h2>
        <span v-if="imageCount">{{ imageCount }} image{{ imageCount === 1 ? '' : 's' }}</span>
      </div>

      <p v-if="!imageCount && !isLoading" class="empty-state">
        No images yet. Submit a prompt to get started.
      </p>

      <div v-if="imageCount" class="image-grid">
        <article v-for="(image, index) in images" :key="`${image.src}-${index}`" class="image-card">
          <img :src="image.src" :alt="image.alt" loading="lazy" />
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
