<script setup>
import { computed, onMounted, ref } from 'vue'
import { dedupeImages, extractImages } from '../../utils/imageParsers'

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

const providerOptions = ref({})
const selectedModelKeys = ref([])
const selectionSettings = ref({})
const editImages = ref([])

const MAX_EDIT_IMAGES = 16
const POLL_INTERVAL_MS = 700

const imageCount = computed(() => images.value.length)
const editImageCount = computed(() => editImages.value.length)
const providerNames = computed(() => Object.keys(providerOptions.value))

const modelCatalog = computed(() => {
  const items = []
  providerNames.value.forEach((providerName) => {
    const providerConfig = providerOptions.value[providerName] || {}
    const models = Array.isArray(providerConfig.models) ? providerConfig.models : []

    models.forEach((modelItem) => {
      const modelId =
        typeof modelItem === 'string' ? modelItem.trim() : typeof modelItem?.id === 'string' ? modelItem.id.trim() : ''
      if (!modelId) return

      const modelLabel =
        typeof modelItem === 'object' && typeof modelItem?.label === 'string' && modelItem.label.trim()
          ? modelItem.label.trim()
          : modelId
      const modelSupportsImageEdit =
        typeof modelItem === 'object' && typeof modelItem?.supports_image_edit === 'boolean'
          ? Boolean(modelItem.supports_image_edit)
          : Boolean(providerConfig.supports_image_edit)

      const key = buildModelKey(providerName, modelId)
      items.push({
        key,
        provider: providerName,
        model: modelId,
        label: modelLabel,
        sizes: normalizeStringOptions(providerConfig.sizes),
        qualities: normalizeStringOptions(providerConfig.qualities),
        supportsSteps: Boolean(providerConfig.supports_steps),
        supportsImageEdit: modelSupportsImageEdit,
        defaultSize: normalizeOptionalString(providerConfig.default_size),
        defaultQuality: normalizeOptionalString(providerConfig.default_quality),
        defaultSteps: Number.isFinite(providerConfig.default_steps) ? Number(providerConfig.default_steps) : 28,
      })
    })
  })
  return items
})

const selectedModels = computed(() => {
  const selected = new Set(selectedModelKeys.value)
  return modelCatalog.value.filter((item) => selected.has(item.key))
})

function buildModelKey(providerName, modelId) {
  return `${providerName}::${modelId}`
}

function normalizeStringOptions(value) {
  if (!Array.isArray(value)) return []
  return value.filter((item) => typeof item === 'string' && item.trim())
}

function normalizeOptionalString(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

function getDefaultSettings(item) {
  return {
    size: item.defaultSize || item.sizes[0] || '',
    quality: item.defaultQuality || item.qualities[0] || '',
    steps: String(item.defaultSteps > 0 ? item.defaultSteps : 28),
    useReferenceImages: item.supportsImageEdit,
  }
}

function ensureSettings(item) {
  if (selectionSettings.value[item.key]) return
  selectionSettings.value[item.key] = getDefaultSettings(item)
}

function initializeSelections() {
  const keys = []
  const nextSettings = {}

  modelCatalog.value.forEach((item) => {
    keys.push(item.key)
    nextSettings[item.key] = getDefaultSettings(item)
  })

  selectedModelKeys.value = keys
  selectionSettings.value = nextSettings
}

function selectAllModels() {
  selectedModelKeys.value = modelCatalog.value.map((item) => item.key)
  modelCatalog.value.forEach((item) => ensureSettings(item))
}

function clearModelSelection() {
  selectedModelKeys.value = []
}

function toggleModelSelection(itemKey) {
  const selected = new Set(selectedModelKeys.value)
  if (selected.has(itemKey)) {
    selected.delete(itemKey)
  } else {
    selected.add(itemKey)
    const item = modelCatalog.value.find((entry) => entry.key === itemKey)
    if (item) ensureSettings(item)
  }
  selectedModelKeys.value = Array.from(selected)
}

function normalizeStepValue(rawValue) {
  const value = typeof rawValue === 'string' ? rawValue.trim() : String(rawValue ?? '').trim()
  if (!value) return undefined
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed) || parsed <= 0) return undefined
  return parsed
}

async function loadProviderOptions() {
  const response = await fetch(`${props.apiBaseUrl}/api/providers`)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || !payload || typeof payload !== 'object') {
    throw new Error('Failed to load provider options.')
  }

  providerOptions.value = payload
  if (!modelCatalog.value.length) {
    throw new Error('No models are currently available.')
  }

  initializeSelections()
}

function buildSelectionsPayload() {
  return selectedModels.value.map((item) => {
    const settings = selectionSettings.value[item.key] || getDefaultSettings(item)
    const payload = {
      provider: item.provider,
      model: item.model,
      size: settings.size || undefined,
      quality: settings.quality || undefined,
      steps: item.supportsSteps ? normalizeStepValue(settings.steps) : undefined,
      use_reference_images: item.supportsImageEdit ? Boolean(settings.useReferenceImages) : false,
    }
    return payload
  })
}

async function generateImages() {
  const trimmedPrompt = prompt.value.trim()
  if (!trimmedPrompt || isLoading.value) return

  isLoading.value = true
  error.value = ''
  revisedPrompt.value = ''
  images.value = []

  try {
    if (!selectedModels.value.length) {
      throw new Error('Select at least one model.')
    }

    const selections = buildSelectionsPayload()
    const response = await fetch(`${props.apiBaseUrl}/api/images/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: trimmedPrompt,
        selections,
        edit_images: editImages.value.length
          ? editImages.value.map((image) => ({
              name: image.name,
              mime_type: image.mime_type,
              data_url: image.data_url,
            }))
          : undefined,
      }),
    })

    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Request failed.')
    }

    const runId = typeof payload.run_id === 'string' ? payload.run_id.trim() : ''
    if (!runId) {
      throw new Error('Missing run id in generate response.')
    }

    const status = await pollRunStatus(runId, trimmedPrompt)
    if (status.failed > 0) {
      error.value = `${status.failed} model request(s) failed. Showing successful images.`
    }

    if (!images.value.length) {
      throw new Error('No images were returned by the API.')
    }
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : 'Unexpected error.'
  } finally {
    isLoading.value = false
  }
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

async function pollRunStatus(runId, fallbackPrompt) {
  while (true) {
    const response = await fetch(`${props.apiBaseUrl}/api/runs/${runId}/status`)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Failed to fetch run status.')
    }

    if (typeof payload.revised_prompt === 'string' && payload.revised_prompt.trim()) {
      revisedPrompt.value = payload.revised_prompt
    }

    const nextImages = extractImages(payload, props.apiBaseUrl, {
      prompt: typeof payload.prompt === 'string' ? payload.prompt : fallbackPrompt,
    })
    images.value = dedupeImages([...images.value, ...nextImages])

    if (payload.done) {
      return {
        failed: typeof payload.failed === 'number' ? payload.failed : 0,
      }
    }
    await sleep(POLL_INTERVAL_MS)
  }
}

function openImage(image) {
  if (!image?.src) return
  emit('open-image', image)
}

function clearEditImages() {
  editImages.value = []
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result !== 'string') {
        reject(new Error(`Unable to read '${file.name}'.`))
        return
      }
      resolve(reader.result)
    }
    reader.onerror = () => {
      reject(new Error(`Unable to read '${file.name}'.`))
    }
    reader.readAsDataURL(file)
  })
}

async function handleEditImagesChange(event) {
  const fileList = Array.from(event?.target?.files || [])
  if (!fileList.length) {
    editImages.value = []
    return
  }

  if (fileList.length > MAX_EDIT_IMAGES) {
    error.value = `You can attach up to ${MAX_EDIT_IMAGES} reference images.`
  } else {
    error.value = ''
  }

  const limitedFiles = fileList.slice(0, MAX_EDIT_IMAGES)
  try {
    editImages.value = await Promise.all(
      limitedFiles.map(async (file) => ({
        name: file.name || 'reference-image.png',
        mime_type: file.type || 'image/png',
        data_url: await readFileAsDataUrl(file),
      })),
    )
  } catch (uploadError) {
    editImages.value = []
    error.value = uploadError instanceof Error ? uploadError.message : 'Failed to parse reference images.'
  }
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
        <div class="model-controls">
          <div class="model-controls-header">
            <label class="prompt-label">Model Targets</label>
            <div class="action-row">
              <button type="button" class="secondary" :disabled="isLoading" @click="selectAllModels">Select All</button>
              <button type="button" class="secondary" :disabled="isLoading" @click="clearModelSelection">Clear</button>
            </div>
          </div>

          <div class="model-grid">
            <article
              v-for="item in modelCatalog"
              :key="item.key"
              class="model-card"
              :class="{ selected: selectedModelKeys.includes(item.key) }"
            >
              <label class="model-toggle">
                <input
                  type="checkbox"
                  :checked="selectedModelKeys.includes(item.key)"
                  :disabled="isLoading"
                  @change="toggleModelSelection(item.key)"
                />
                <div>
                  <p class="model-title">{{ item.label }}</p>
                  <p class="model-subtitle">{{ item.provider }}</p>
                </div>
              </label>

              <div v-if="selectedModelKeys.includes(item.key)" class="model-settings">
                <div v-if="item.sizes.length" class="control-field">
                  <label class="prompt-label" :for="`size-${item.key}`">Size</label>
                  <select
                    :id="`size-${item.key}`"
                    v-model="selectionSettings[item.key].size"
                    :disabled="isLoading"
                    @focus="ensureSettings(item)"
                  >
                    <option v-for="option in item.sizes" :key="option" :value="option">{{ option }}</option>
                  </select>
                </div>

                <div v-if="item.qualities.length" class="control-field">
                  <label class="prompt-label" :for="`quality-${item.key}`">Quality</label>
                  <select
                    :id="`quality-${item.key}`"
                    v-model="selectionSettings[item.key].quality"
                    :disabled="isLoading"
                    @focus="ensureSettings(item)"
                  >
                    <option v-for="option in item.qualities" :key="option" :value="option">{{ option }}</option>
                  </select>
                </div>

                <div v-if="item.supportsSteps" class="control-field">
                  <label class="prompt-label" :for="`steps-${item.key}`">Steps</label>
                  <input
                    :id="`steps-${item.key}`"
                    v-model="selectionSettings[item.key].steps"
                    type="number"
                    min="1"
                    :disabled="isLoading"
                    @focus="ensureSettings(item)"
                  />
                </div>

                <label v-if="item.supportsImageEdit" class="check-item">
                  <input
                    v-model="selectionSettings[item.key].useReferenceImages"
                    type="checkbox"
                    :disabled="isLoading"
                    @focus="ensureSettings(item)"
                  />
                  <span>Use reference images</span>
                </label>
              </div>
            </article>
          </div>
        </div>

        <div class="control-field">
          <label class="prompt-label" for="prompt-input">Prompt</label>
          <textarea
            id="prompt-input"
            v-model="prompt"
            placeholder="e.g. A futuristic city skyline at sunrise, cinematic lighting"
            rows="4"
            :disabled="isLoading"
          />
        </div>

        <div class="control-field">
          <label class="prompt-label" for="edit-images-input">Reference Images (Optional)</label>
          <input
            id="edit-images-input"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            :disabled="isLoading"
            @change="handleEditImagesChange"
          />
          <p class="field-hint">
            Attach up to {{ MAX_EDIT_IMAGES }} images. They are stored with the run and only used for selected models that support image edit.
          </p>
          <div v-if="editImageCount" class="edit-images-summary">
            <p class="field-hint">{{ editImageCount }} image{{ editImageCount === 1 ? '' : 's' }} selected</p>
            <button type="button" class="secondary" :disabled="isLoading" @click="clearEditImages">Clear</button>
          </div>
        </div>

        <button type="submit" :disabled="isLoading || !prompt.trim() || !selectedModels.length">
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
  gap: 1rem;
}

.model-controls {
  display: grid;
  gap: 0.75rem;
}

.model-controls-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.action-row {
  display: flex;
  gap: 0.5rem;
}

.model-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}

.model-card {
  border: 1px solid #bfd0ea;
  border-radius: 12px;
  background: #f8fbff;
  padding: 0.7rem;
  display: grid;
  gap: 0.6rem;
}

.model-card.selected {
  border-color: #2b6ecf;
  box-shadow: 0 0 0 2px rgba(43, 110, 207, 0.15);
  background: #f1f7ff;
}

.model-toggle {
  display: flex;
  align-items: start;
  gap: 0.55rem;
  cursor: pointer;
}

.model-title {
  margin: 0;
  color: #123764;
  font-weight: 600;
  line-height: 1.25;
}

.model-subtitle {
  margin: 0.2rem 0 0;
  color: #58719b;
  text-transform: capitalize;
  font-size: 0.82rem;
}

.model-settings {
  display: grid;
  gap: 0.5rem;
}

.control-field {
  display: grid;
  gap: 0.35rem;
}

.prompt-label {
  font-weight: 600;
  color: #203a67;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #1f3f73;
  font-size: 0.9rem;
}

.check-item input {
  width: auto;
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

button.secondary {
  background: #eaf1ff;
  border: 1px solid #b9c9e3;
  color: #194790;
}

button.secondary:disabled {
  background: #f2f5fb;
  color: #7f92b4;
}

.field-hint {
  margin: 0;
  color: #5f7498;
  font-size: 0.82rem;
}

.edit-images-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
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
