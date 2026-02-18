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

const selectedEditCapableCount = computed(() => selectedModels.value.filter((item) => item.supportsImageEdit).length)

const selectedUsingReferenceCount = computed(() =>
  selectedModels.value.filter((item) => {
    if (!item.supportsImageEdit) return false
    const settings = selectionSettings.value[item.key]
    return Boolean(settings?.useReferenceImages)
  }).length,
)

const promptCharCount = computed(() => prompt.value.trim().length)

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
    return {
      provider: item.provider,
      model: item.model,
      size: settings.size || undefined,
      quality: settings.quality || undefined,
      steps: item.supportsSteps ? normalizeStepValue(settings.steps) : undefined,
      use_reference_images: item.supportsImageEdit ? Boolean(settings.useReferenceImages) : false,
    }
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
        <div class="section-label">
          <span class="section-label-kicker">Step 1</span>
          <h2>Model Targets</h2>
        </div>

        <div class="model-controls">
          <div class="model-controls-header">
            <p class="summary-line">{{ selectedModels.length }} selected · {{ providerNames.length }} providers</p>
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

        <div class="selection-summary">
          <p><strong>{{ selectedEditCapableCount }}</strong> selected models can consume references.</p>
          <p><strong>{{ selectedUsingReferenceCount }}</strong> currently set to use reference images.</p>
        </div>

        <div class="section-label">
          <span class="section-label-kicker">Step 2</span>
          <h2>Prompt & References</h2>
        </div>

        <div class="control-field">
          <label class="prompt-label" for="prompt-input">Prompt</label>
          <textarea
            id="prompt-input"
            v-model="prompt"
            placeholder="e.g. Brutalist museum atrium with suspended gardens, cinematic light shafts"
            rows="4"
            :disabled="isLoading"
          />
          <p class="field-hint">{{ promptCharCount }} characters</p>
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
            Attach up to {{ MAX_EDIT_IMAGES }} images. They are persisted with the run and only used for models with edit support.
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

      <p v-if="!imageCount && !isLoading" class="empty-state">No images yet. Configure your targets and run a prompt.</p>

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
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  padding: 1rem;
}

.prompt-form {
  display: grid;
  gap: 1rem;
}

.section-label {
  display: grid;
  gap: 0.22rem;
}

.section-label-kicker {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 0.68rem;
  color: #7f5d43;
  font-weight: 700;
}

.section-label h2 {
  margin: 0;
  font-family: 'Fraunces', Georgia, serif;
  font-size: 1.25rem;
  color: #2c2119;
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

.summary-line {
  margin: 0;
  color: #6c5442;
  font-size: 0.88rem;
}

.action-row {
  display: flex;
  gap: 0.5rem;
}

.model-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
}

.model-card {
  border: 1px solid #d9c8b5;
  border-radius: var(--radius-md);
  background: var(--surface-strong);
  padding: 0.72rem;
  display: grid;
  gap: 0.6rem;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.model-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(79, 45, 21, 0.1);
}

.model-card.selected {
  border-color: #0b7f68;
  box-shadow: 0 0 0 2px rgba(11, 127, 104, 0.2);
  background: #f1fff8;
}

.model-toggle {
  display: flex;
  align-items: start;
  gap: 0.55rem;
  cursor: pointer;
}

.model-title {
  margin: 0;
  color: #2a2019;
  font-weight: 700;
  line-height: 1.25;
}

.model-subtitle {
  margin: 0.15rem 0 0;
  color: #6f5a4a;
  text-transform: capitalize;
  font-size: 0.82rem;
}

.model-settings {
  display: grid;
  gap: 0.5rem;
}

.selection-summary {
  background: linear-gradient(135deg, #f8f1e4 0%, #eefcf7 100%);
  border: 1px solid #d9cab6;
  border-radius: var(--radius-md);
  padding: 0.65rem 0.75rem;
  display: grid;
  gap: 0.25rem;
}

.selection-summary p {
  margin: 0;
  color: #584638;
  font-size: 0.84rem;
}

.control-field {
  display: grid;
  gap: 0.35rem;
}

.prompt-label {
  font-weight: 700;
  color: #3a2b1f;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #3f2f24;
  font-size: 0.9rem;
}

.check-item input {
  width: auto;
}

textarea,
input,
select {
  width: 100%;
  border: 1px solid #cab8a4;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  font: inherit;
  color: #2b2018;
  background: #fffdf8;
}

textarea {
  resize: vertical;
  min-height: 110px;
}

textarea:focus,
input:focus,
select:focus {
  outline: 2px solid rgba(6, 122, 101, 0.4);
  outline-offset: 1px;
}

button {
  justify-self: start;
  background: linear-gradient(130deg, #0b7f68 0%, #055145 100%);
  color: #f4fff9;
  border: 0;
  border-radius: 11px;
  padding: 0.62rem 1.05rem;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  background: #9f9a90;
  cursor: not-allowed;
}

button.secondary {
  background: #fff5e8;
  border: 1px solid #d8c5ae;
  color: #5e4738;
}

button.secondary:disabled {
  background: #f1ebe2;
  color: #988b7d;
}

.field-hint {
  margin: 0;
  color: #746253;
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
  background: #e6fbf5;
  color: #0f5f50;
  border: 1px solid #b8e5d9;
}

.results-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0.8rem;
}

.results-header h2 {
  margin: 0;
  font-family: 'Fraunces', Georgia, serif;
  color: #2a1e17;
}

.empty-state {
  color: #5f4d3e;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.9rem;
}

.image-card {
  border: 1px solid #d7c6b1;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #fff9ee;
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
  background: #fff;
}

.image-prompt {
  margin: 0;
  color: #3b2d21;
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
  color: #6f594a;
  font-size: 0.8rem;
}

@media (min-width: 860px) {
  .panel,
  .results {
    padding: 1.25rem;
  }
}
</style>
