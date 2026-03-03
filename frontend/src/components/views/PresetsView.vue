<script setup>
import { computed, onMounted, ref } from 'vue'
import { readFileAsDataUrl } from '../../utils/imageParsers'

const props = defineProps({
  apiBaseUrl: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['use-preset'])

const presets = ref([])
const selectedPresetId = ref('')
const isLoading = ref(false)
const error = ref('')
const success = ref('')

const form = ref(defaultForm())
const presetReferenceImages = ref([])
const uploadedReferenceImages = ref([])
const MAX_REFERENCE_IMAGES = 16

const selectedPreset = computed(() => presets.value.find((preset) => preset.id === selectedPresetId.value) || null)
const effectiveReferenceImages = computed(() =>
  uploadedReferenceImages.value.length ? uploadedReferenceImages.value : presetReferenceImages.value,
)

function defaultForm() {
  return {
    mode: 'create',
    sourcePresetId: '',
    promptingConfig: {
      systemPrompt: '',
      promptTemplate: '',
      negativePrompt: '',
    },
    inputSchema: {
      variables: [],
    },
    i2iOnly: false,
  }
}

function addVariable() {
  form.value.inputSchema.variables.push({
    name: '',
    type: 'string',
    required: false,
    default: '',
    allowedValuesText: '',
    description: '',
  })
}

function removeVariable(index) {
  form.value.inputSchema.variables.splice(index, 1)
}

function buildPayload() {
  const variables = form.value.inputSchema.variables
    .map((entry) => {
      const name = String(entry.name || '').trim()
      if (!name) return null
      return {
        name,
        type: String(entry.type || 'string').trim() || 'string',
        required: Boolean(entry.required),
        default: String(entry.default || '').trim() || undefined,
        allowedValues: String(entry.allowedValuesText || '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        description: String(entry.description || '').trim() || undefined,
      }
    })
    .filter(Boolean)

  const payload = {
    promptingConfig: {
      systemPrompt: String(form.value.promptingConfig.systemPrompt || '').trim() || undefined,
      promptTemplate: form.value.promptingConfig.promptTemplate,
      negativePrompt: String(form.value.promptingConfig.negativePrompt || '').trim() || undefined,
    },
    inputSchema: {
      variables,
    },
    i2iOnly: Boolean(form.value.i2iOnly),
  }
  if (uploadedReferenceImages.value.length) {
    payload.referenceImages = uploadedReferenceImages.value.map((image) => ({
      name: image.name,
      mime_type: image.mime_type,
      data_url: image.data_url,
    }))
  }
  return payload
}

function populateFormFromPreset(preset) {
  const version = preset?.version || {}
  const promptingConfig = version.promptingConfig || {}
  const inputSchema = version.inputSchema || {}

  form.value = {
    mode: 'edit',
    sourcePresetId: preset.id,
    promptingConfig: {
      systemPrompt: promptingConfig.systemPrompt || '',
      promptTemplate: promptingConfig.promptTemplate || '',
      negativePrompt: promptingConfig.negativePrompt || '',
    },
    inputSchema: {
      variables: Array.isArray(inputSchema.variables)
        ? inputSchema.variables.map((entry) => ({
            name: entry.name || '',
            type: entry.type || 'string',
            required: Boolean(entry.required),
            default: entry.default || '',
            allowedValuesText: Array.isArray(entry.allowedValues) ? entry.allowedValues.join(', ') : '',
            description: entry.description || '',
          }))
        : [],
    },
    i2iOnly: Boolean(version.i2iOnly),
  }
  presetReferenceImages.value = Array.isArray(version.referenceImages) ? version.referenceImages : []
  uploadedReferenceImages.value = []
}

function startNewPreset() {
  selectedPresetId.value = ''
  form.value = defaultForm()
  presetReferenceImages.value = []
  uploadedReferenceImages.value = []
}

async function handlePresetReferenceImagesChange(event) {
  const fileList = Array.from(event?.target?.files || [])
  if (!fileList.length) {
    uploadedReferenceImages.value = []
    return
  }
  const limitedFiles = fileList.slice(0, MAX_REFERENCE_IMAGES)
  try {
    uploadedReferenceImages.value = await Promise.all(
      limitedFiles.map(async (file) => {
        const dataUrl = await readFileAsDataUrl(file)
        return {
          id: `upload-${file.name}-${file.size}-${file.lastModified}`,
          name: file.name || 'preset-reference.png',
          mime_type: file.type || 'image/png',
          data_url: dataUrl,
          image_url: dataUrl,
        }
      }),
    )
  } catch (uploadError) {
    uploadedReferenceImages.value = []
    error.value = uploadError instanceof Error ? uploadError.message : 'Failed to parse preset reference images.'
  }
}

function clearPresetReferenceUploads() {
  uploadedReferenceImages.value = []
}

async function loadPresets() {
  const response = await fetch(`${props.apiBaseUrl}/api/presets`)
  const payload = await response.json().catch(() => [])
  if (!response.ok || !Array.isArray(payload)) {
    throw new Error('Failed to load presets.')
  }
  presets.value = payload
}

async function savePreset() {
  if (isLoading.value) return
  isLoading.value = true
  error.value = ''
  success.value = ''

  try {
    const payload = buildPayload()
    const isEdit = form.value.mode === 'edit' && form.value.sourcePresetId
    const endpoint = isEdit
      ? `${props.apiBaseUrl}/api/presets/${form.value.sourcePresetId}/versions`
      : `${props.apiBaseUrl}/api/presets`

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(data.error || 'Failed to save preset.')
    }

    await loadPresets()
    selectedPresetId.value = data.id
    populateFormFromPreset(data)
    success.value = isEdit ? `Created version v${data.latestVersion}.` : 'Preset created.'
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : 'Failed to save preset.'
  } finally {
    isLoading.value = false
  }
}

async function duplicateSelectedPreset() {
  if (!selectedPreset.value) return
  const duplicateName = `${selectedPreset.value.name} Copy`
  isLoading.value = true
  error.value = ''
  success.value = ''

  try {
    const response = await fetch(`${props.apiBaseUrl}/api/presets/${selectedPreset.value.id}/duplicate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: duplicateName,
      }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data.error || 'Failed to duplicate preset.')
    }
    await loadPresets()
    selectedPresetId.value = data.id
    populateFormFromPreset(data)
    success.value = `Duplicated as '${duplicateName}'.`
  } catch (dupError) {
    error.value = dupError instanceof Error ? dupError.message : 'Failed to duplicate preset.'
  } finally {
    isLoading.value = false
  }
}

function useSelectedPreset() {
  if (!selectedPreset.value?.id) return
  emit('use-preset', {
    presetId: selectedPreset.value.id,
    presetVersion: selectedPreset.value.latestVersion,
  })
}

function onSelectPreset() {
  const preset = selectedPreset.value
  if (!preset) return
  populateFormFromPreset(preset)
}

onMounted(async () => {
  try {
    await loadPresets()
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Failed to load presets.'
  }
})
</script>

<template>
  <div class="preset-grid">
    <section class="panel list-panel">
      <div class="list-header">
        <div>
          <p class="eyebrow">Library</p>
          <h2>Presets</h2>
        </div>
        <button type="button" class="secondary" :disabled="isLoading" @click="startNewPreset">New Preset</button>
      </div>
      <p v-if="!presets.length" class="field-hint">No presets yet.</p>
      <div class="preset-list">
        <button
          v-for="preset in presets"
          :key="preset.id"
          type="button"
          class="preset-item"
          :class="{ active: selectedPresetId === preset.id }"
          @click="selectedPresetId = preset.id; onSelectPreset()"
        >
          <div class="preset-main">
            <strong>{{ preset.name }}</strong>
          </div>
          <span class="version-badge">v{{ preset.latestVersion }}</span>
        </button>
      </div>
    </section>

    <section class="panel form-panel">
      <div class="form-header">
        <div>
          <p class="eyebrow">Editor</p>
          <h2>{{ form.mode === 'edit' ? 'Edit Preset (New Version)' : 'Create Preset' }}</h2>
        </div>
        <div class="action-row">
          <button type="button" class="secondary" :disabled="!selectedPreset || isLoading" @click="useSelectedPreset">Use In Generate</button>
          <button type="button" class="secondary" :disabled="!selectedPreset || isLoading" @click="duplicateSelectedPreset">Duplicate</button>
        </div>
      </div>

      <div class="section-card">
        <h3>Prompting</h3>
        <p class="field-hint">Presets define design language and prompt structure. Model selection stays in Generate.</p>
        <label class="flag">
          <input v-model="form.i2iOnly" type="checkbox" :disabled="isLoading" />
          limit to i2i-capable models only
        </label>
        <div class="control-field">
          <label>Prompt Template</label>
          <textarea v-model="form.promptingConfig.promptTemplate" rows="3" :disabled="isLoading" placeholder="Poster about {{title}} in {{style}} style" />
        </div>
        <div class="form-grid">
          <div class="control-field">
            <label>System Prompt</label>
            <textarea v-model="form.promptingConfig.systemPrompt" rows="2" :disabled="isLoading" />
          </div>
          <div class="control-field">
            <label>Negative Prompt</label>
            <textarea v-model="form.promptingConfig.negativePrompt" rows="2" :disabled="isLoading" />
          </div>
        </div>
      </div>

      <div class="section-card">
        <div class="section-head">
          <h3>Input Variables</h3>
          <button type="button" class="secondary" :disabled="isLoading" @click="addVariable">Add Variable</button>
        </div>
        <div v-if="!form.inputSchema.variables.length" class="field-hint">No variables yet. Add placeholders used by your prompt template.</div>
        <div v-for="(variable, index) in form.inputSchema.variables" :key="index" class="variable-row">
          <input v-model="variable.name" placeholder="name" :disabled="isLoading" />
          <select v-model="variable.type" :disabled="isLoading">
            <option value="string">string</option>
            <option value="number">number</option>
          </select>
          <label class="flag"><input v-model="variable.required" type="checkbox" :disabled="isLoading" /> required</label>
          <input v-model="variable.default" placeholder="default" :disabled="isLoading" />
          <input v-model="variable.allowedValuesText" placeholder="allowed values (a,b,c)" :disabled="isLoading" />
          <button type="button" class="secondary" :disabled="isLoading" @click="removeVariable(index)">Remove</button>
        </div>
      </div>

      <div class="section-card">
        <div class="section-head">
          <h3>Preset Reference Images</h3>
          <button
            v-if="uploadedReferenceImages.length"
            type="button"
            class="secondary"
            :disabled="isLoading"
            @click="clearPresetReferenceUploads"
          >
            Revert Uploads
          </button>
        </div>
        <div class="control-field">
          <label for="preset-reference-images">Upload references (optional)</label>
          <input
            id="preset-reference-images"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            :disabled="isLoading"
            @change="handlePresetReferenceImagesChange"
          />
          <p class="field-hint">
            {{ uploadedReferenceImages.length ? 'Uploads will replace current preset references on save.' : 'Leave empty to keep existing references.' }}
          </p>
        </div>
        <div v-if="effectiveReferenceImages.length" class="reference-grid">
          <img
            v-for="(image, index) in effectiveReferenceImages"
            :key="image.id || `${image.image_url}-${index}`"
            :src="image.image_url"
            :alt="image.name || `Preset reference ${index + 1}`"
          />
        </div>
      </div>

      <div class="action-row">
        <button type="button" :disabled="isLoading" @click="savePreset">{{ isLoading ? 'Saving...' : 'Save Preset' }}</button>
      </div>

      <p v-if="error" class="message error">{{ error }}</p>
      <p v-if="success" class="message info">{{ success }}</p>
    </section>
  </div>
</template>

<style scoped>
.preset-grid {
  display: grid;
  gap: 1.25rem;
  align-items: start;
}

@media (min-width: 980px) {
  .preset-grid {
    grid-template-columns: 340px minmax(0, 1fr);
  }
}

.panel {
  background: var(--surface);
  border: 1px solid #d8c6af;
  border-radius: 18px;
  box-shadow: var(--shadow-soft);
  padding: 1rem;
  animation: panelIn 0.45s ease both;
}

.list-panel {
  position: sticky;
  top: 1rem;
  background:
    radial-gradient(circle at 90% 8%, rgba(5, 104, 88, 0.08), transparent 35%),
    radial-gradient(circle at 6% 86%, rgba(173, 121, 79, 0.12), transparent 30%),
    #fff8ee;
}

.eyebrow {
  margin: 0;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 0.68rem;
  font-weight: 800;
  color: #80634f;
}

.list-header,
.form-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  flex-wrap: wrap;
}

h2,
h3 {
  margin: 0.4rem 0;
  font-family: 'Fraunces', Georgia, serif;
  color: #2f2218;
}

.preset-list {
  display: grid;
  gap: 0.6rem;
  margin-top: 0.8rem;
  max-height: min(65vh, 620px);
  overflow: auto;
  padding-right: 0.25rem;
}

.preset-item {
  text-align: left;
  border: 1px solid #d5c0a6;
  border-radius: 14px;
  background: #fffefb;
  color: #453529;
  padding: 0.68rem 0.75rem;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.6rem;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.preset-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(67, 35, 16, 0.12);
}

.preset-main {
  display: grid;
  gap: 0.28rem;
}

.preset-main strong {
  line-height: 1.2;
}

.version-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3ch;
  font-size: 0.76rem;
  font-weight: 700;
  border-radius: 999px;
  padding: 0.18rem 0.5rem;
  background: #f0fbf7;
  border: 1px solid #b8ddd2;
  color: #0f5e50;
}

.preset-item.active {
  border-color: #0b7f68;
  box-shadow: 0 0 0 2px rgba(11, 127, 104, 0.18), 0 10px 30px rgba(8, 98, 82, 0.12);
  background: linear-gradient(145deg, #f9fff9, #fffbf3);
}

.section-card {
  border: 1px solid #dbc8b1;
  border-radius: 14px;
  padding: 0.8rem;
  background:
    linear-gradient(165deg, rgba(255, 251, 244, 0.96), rgba(254, 247, 236, 0.98));
  margin-bottom: 0.75rem;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.7rem;
  flex-wrap: wrap;
}

.form-grid {
  display: grid;
  gap: 0.7rem;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}

.form-grid .full {
  grid-column: 1 / -1;
}

.control-field {
  display: grid;
  gap: 0.35rem;
}

.control-field label {
  font-weight: 700;
  color: #3a2b1f;
  font-size: 0.84rem;
}

input,
textarea,
select {
  width: 100%;
  border: 1px solid #cab8a4;
  border-radius: 10px;
  padding: 0.55rem 0.65rem;
  font: inherit;
  color: #2b2018;
  background: #fffdf8;
}

textarea {
  resize: vertical;
}

.flag {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-weight: 700;
  font-size: 0.82rem;
  color: #4b3b2f;
}

.action-row {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
  margin: 0.65rem 0;
}

button {
  background: linear-gradient(130deg, #0b7f68 0%, #055145 100%);
  color: #f4fff9;
  border: 0;
  border-radius: 11px;
  padding: 0.58rem 0.95rem;
  font-weight: 700;
  cursor: pointer;
}

button.secondary {
  background: #fff5e8;
  border: 1px solid #d8c5ae;
  color: #5e4738;
}

button:disabled {
  background: #9f9a90;
  color: #f4f4f4;
  cursor: not-allowed;
}

.variable-row {
  display: grid;
  gap: 0.5rem;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  margin-bottom: 0.6rem;
  border: 1px solid #ddccb8;
  border-radius: 12px;
  padding: 0.55rem;
  background: #fffdf8;
}

.reference-grid {
  display: grid;
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
}

.reference-grid img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid #d9c7b2;
  background: #fffdf8;
}

.field-hint {
  margin: 0;
  color: #746253;
  font-size: 0.82rem;
}

.message {
  margin: 0.6rem 0 0;
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

@keyframes panelIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 979px) {
  .list-panel {
    position: static;
  }
}
</style>
