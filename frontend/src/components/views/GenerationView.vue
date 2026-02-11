<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { extractImages } from '../../utils/imageParsers'

const props = defineProps({
  apiBaseUrl: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['open-image'])

const prompt = ref('')
const isLoading = ref(false)
const error = ref('')
const revisedPrompt = ref('')
const images = ref([])

const provider = ref('openai')
const size = ref('1024x1024')
const steps = ref('28')
const quality = ref('')
const selectedModels = ref([])
const providerOptions = ref({})

const imageCount = computed(() => images.value.length)
const providerNames = computed(() => Object.keys(providerOptions.value))
const currentProviderOption = computed(() => providerOptions.value[provider.value] || null)
const currentModelOptions = computed(() => {
  const models = currentProviderOption.value?.models || []
  return models
    .map((item) => {
      if (typeof item === 'string') {
        return { id: item, label: item }
      }
      if (!item || typeof item !== 'object') {
        return null
      }
      const id = typeof item.id === 'string' ? item.id.trim() : ''
      if (!id) return null
      return {
        id,
        label: typeof item.label === 'string' && item.label.trim() ? item.label.trim() : id,
      }
    })
    .filter(Boolean)
})
const currentSizeOptions = computed(() => {
  const sizes = currentProviderOption.value?.sizes
  return Array.isArray(sizes) ? sizes.filter((item) => typeof item === 'string' && item.trim()) : []
})
const currentQualityOptions = computed(() => {
  const qualities = currentProviderOption.value?.qualities
  return Array.isArray(qualities) ? qualities.filter((item) => typeof item === 'string' && item.trim()) : []
})
const currentSupportsSteps = computed(() => Boolean(currentProviderOption.value?.supports_steps))

function resetProviderDefaults(nextProvider) {
  const options = providerOptions.value[nextProvider]
  if (!options || typeof options !== 'object') return

  selectedModels.value = currentModelOptions.value.map((item) => item.id)

  const defaultSize = typeof options.default_size === 'string' ? options.default_size : ''
  size.value = defaultSize || currentSizeOptions.value[0] || ''

  const defaultQuality = typeof options.default_quality === 'string' ? options.default_quality : ''
  quality.value = defaultQuality || currentQualityOptions.value[0] || ''

  const defaultSteps = options.default_steps
  steps.value = Number.isFinite(defaultSteps) ? String(defaultSteps) : '28'
}

watch(provider, (nextProvider) => {
  resetProviderDefaults(nextProvider)
})

async function loadProviderOptions() {
  const response = await fetch(`${props.apiBaseUrl}/api/providers`)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || !payload || typeof payload !== 'object') {
    throw new Error('Failed to load provider options.')
  }

  providerOptions.value = payload
  const availableProviders = providerNames.value
  if (!availableProviders.length) {
    throw new Error('No providers are currently available.')
  }

  const nextProvider = availableProviders.includes(provider.value) ? provider.value : availableProviders[0]
  provider.value = nextProvider
  resetProviderDefaults(nextProvider)
}

async function generateImages() {
  const trimmedPrompt = prompt.value.trim()
  if (!trimmedPrompt || isLoading.value) return

  const enabledModels = currentModelOptions.value
    .map((option) => option.id)
    .filter((id) => selectedModels.value.includes(id))

  isLoading.value = true
  error.value = ''
  revisedPrompt.value = ''
  images.value = []

  try {
    if (!enabledModels.length) {
      throw new Error('Select at least one model.')
    }

    const response = await fetch(`${props.apiBaseUrl}/api/images/generate`, {
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

    if (typeof payload.revised_prompt === 'string' && payload.revised_prompt.trim()) {
      revisedPrompt.value = payload.revised_prompt
    }

    images.value = extractImages(payload, props.apiBaseUrl, {
      prompt: typeof payload.prompt === 'string' ? payload.prompt : trimmedPrompt,
    })

    if (!images.value.length) {
      throw new Error('No images were returned by the API.')
    }
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : 'Unexpected error.'
  } finally {
    isLoading.value = false
  }
}

function openImage(image) {
  if (!image?.src) return
  emit('open-image', image)
}

onMounted(async () => {
  try {
    await loadProviderOptions()
  } catch (providerError) {
    error.value = providerError instanceof Error ? providerError.message : 'Failed to load providers.'
  }
})
</script>

<template>
  <div class="view-grid">
    <section class="panel">
      <form class="prompt-form" @submit.prevent="generateImages">
        <div class="provider-controls">
          <div class="control-field">
            <label class="prompt-label" for="provider-select">Provider</label>
            <select id="provider-select" v-model="provider" :disabled="isLoading">
              <option v-for="name in providerNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </div>

          <div class="control-field">
            <label class="prompt-label">Models</label>
            <div class="model-checklist">
              <label v-for="option in currentModelOptions" :key="option.id" class="check-item">
                <input v-model="selectedModels" type="checkbox" :value="option.id" :disabled="isLoading" />
                <span>{{ option.label }}</span>
              </label>
            </div>
          </div>

          <div class="control-field">
            <label class="prompt-label" for="size-input">Size</label>
            <select id="size-input" v-model="size" :disabled="isLoading || !currentSizeOptions.length">
              <option v-for="option in currentSizeOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </div>

          <div v-if="currentQualityOptions.length" class="control-field">
            <label class="prompt-label" for="quality-input">Quality</label>
            <select id="quality-input" v-model="quality" :disabled="isLoading">
              <option v-for="option in currentQualityOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </div>

          <div v-if="currentSupportsSteps" class="control-field">
            <label class="prompt-label" for="steps-input">Steps</label>
            <input id="steps-input" v-model="steps" type="number" min="1" placeholder="28" :disabled="isLoading" />
          </div>
        </div>

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

      <p v-if="!imageCount && !isLoading" class="empty-state">No images yet. Submit a prompt to get started.</p>

      <div v-if="imageCount" class="image-grid">
        <article v-for="(image, index) in images" :key="`${image.src}-${index}`" class="image-card">
          <img :src="image.src" :alt="image.alt" class="clickable-image" loading="lazy" @click="openImage(image)" />
          <div class="image-meta">
            <p v-if="image.prompt" class="image-prompt">{{ image.prompt }}</p>
            <p v-if="image.provider || image.model" class="image-details">
              <span v-if="image.provider">{{ image.provider }}</span>
              <span v-if="image.provider && image.model"> / </span>
              <span v-if="image.model">{{ image.model }}</span>
            </p>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.view-grid {
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

.prompt-label {
  font-weight: 600;
  color: #203a67;
}

textarea,
input,
select {
  width: 100%;
  border: 1px solid #b9c9e3;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  font: inherit;
  background: #ffffff;
}

textarea {
  resize: vertical;
  min-height: 110px;
}

textarea:focus,
input:focus,
select:focus {
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

@media (min-width: 860px) {
  .panel,
  .results {
    padding: 1.25rem;
  }
}
</style>
