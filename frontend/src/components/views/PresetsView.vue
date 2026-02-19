<script setup>
import { computed, onMounted, ref } from 'vue'

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

const providerOptions = ref({})

const form = ref(defaultForm())

const selectedPreset = computed(() => presets.value.find((preset) => preset.id === selectedPresetId.value) || null)
const modelOptions = computed(() => {
  const provider = form.value.modelConfig.provider
  const providerMeta = providerOptions.value[provider] || {}
  const models = Array.isArray(providerMeta.models) ? providerMeta.models : []
  return models
    .map((model) => {
      if (typeof model === 'string') {
        return { id: model, label: model }
      }
      if (!model || typeof model !== 'object') {
        return null
      }
      const id = typeof model.id === 'string' ? model.id.trim() : ''
      if (!id) return null
      return { id, label: typeof model.label === 'string' && model.label.trim() ? model.label.trim() : id }
    })
    .filter(Boolean)
})

function defaultForm() {
  return {
    mode: 'create',
    sourcePresetId: '',
    name: '',
    description: '',
    tagsCsv: '',
    createdBy: 'local-user',
    modelConfig: {
      provider: '',
      modelId: '',
      modelVariant: '',
    },
    promptingConfig: {
      systemPrompt: '',
      promptTemplate: '',
      negativePrompt: '',
    },
    inputSchema: {
      variables: [],
    },
    generationParams: {
      steps: '',
      guidanceScale: '',
      seedMode: 'random',
      seed: '',
      strength: '',
      aspectRatio: '',
      width: '',
      height: '',
      numImages: '1',
      size: '',
      quality: '',
    },
    referenceRules: {
      referenceMode: 'none',
      maxReferenceImages: '',
      referencePurpose: 'style',
    },
    outputRules: {
      outputFormat: 'png',
      upscale: 'none',
      postprocess: '',
    },
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

function normalizeTags(csv) {
  return String(csv || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function toNumber(value) {
  const text = String(value ?? '').trim()
  if (!text) return undefined
  const parsed = Number(text)
  return Number.isFinite(parsed) ? parsed : undefined
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

  return {
    name: form.value.name,
    description: form.value.description,
    tags: normalizeTags(form.value.tagsCsv),
    createdBy: form.value.createdBy,
    modelConfig: {
      provider: form.value.modelConfig.provider,
      modelId: form.value.modelConfig.modelId,
      modelVariant: String(form.value.modelConfig.modelVariant || '').trim() || undefined,
    },
    promptingConfig: {
      systemPrompt: String(form.value.promptingConfig.systemPrompt || '').trim() || undefined,
      promptTemplate: form.value.promptingConfig.promptTemplate,
      negativePrompt: String(form.value.promptingConfig.negativePrompt || '').trim() || undefined,
    },
    inputSchema: {
      variables,
    },
    generationParams: {
      steps: toNumber(form.value.generationParams.steps),
      guidanceScale: toNumber(form.value.generationParams.guidanceScale),
      seedMode: form.value.generationParams.seedMode,
      seed: toNumber(form.value.generationParams.seed),
      strength: toNumber(form.value.generationParams.strength),
      aspectRatio: String(form.value.generationParams.aspectRatio || '').trim() || undefined,
      width: toNumber(form.value.generationParams.width),
      height: toNumber(form.value.generationParams.height),
      numImages: toNumber(form.value.generationParams.numImages),
      size: String(form.value.generationParams.size || '').trim() || undefined,
      quality: String(form.value.generationParams.quality || '').trim() || undefined,
    },
    referenceRules: {
      referenceMode: form.value.referenceRules.referenceMode,
      maxReferenceImages: toNumber(form.value.referenceRules.maxReferenceImages),
      referencePurpose: form.value.referenceRules.referencePurpose,
    },
    outputRules: {
      outputFormat: form.value.outputRules.outputFormat,
      upscale: form.value.outputRules.upscale,
      postprocess: String(form.value.outputRules.postprocess || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    },
  }
}

function populateFormFromPreset(preset) {
  const version = preset?.version || {}
  const modelConfig = version.modelConfig || {}
  const promptingConfig = version.promptingConfig || {}
  const inputSchema = version.inputSchema || {}
  const generationParams = version.generationParams || {}
  const referenceRules = version.referenceRules || {}
  const outputRules = version.outputRules || {}

  form.value = {
    mode: 'edit',
    sourcePresetId: preset.id,
    name: preset.name || '',
    description: preset.description || '',
    tagsCsv: Array.isArray(preset.tags) ? preset.tags.join(', ') : '',
    createdBy: preset.createdBy || 'local-user',
    modelConfig: {
      provider: modelConfig.provider || '',
      modelId: modelConfig.modelId || modelConfig.model || '',
      modelVariant: modelConfig.modelVariant || '',
    },
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
    generationParams: {
      steps: generationParams.steps ?? '',
      guidanceScale: generationParams.guidanceScale ?? '',
      seedMode: generationParams.seedMode || 'random',
      seed: generationParams.seed ?? '',
      strength: generationParams.strength ?? '',
      aspectRatio: generationParams.aspectRatio || '',
      width: generationParams.width ?? '',
      height: generationParams.height ?? '',
      numImages: generationParams.numImages ?? '1',
      size: generationParams.size || '',
      quality: generationParams.quality || '',
    },
    referenceRules: {
      referenceMode: referenceRules.referenceMode || 'none',
      maxReferenceImages: referenceRules.maxReferenceImages ?? '',
      referencePurpose: referenceRules.referencePurpose || 'style',
    },
    outputRules: {
      outputFormat: outputRules.outputFormat || 'png',
      upscale: outputRules.upscale || 'none',
      postprocess: Array.isArray(outputRules.postprocess) ? outputRules.postprocess.join(', ') : '',
    },
  }
}

function startNewPreset() {
  selectedPresetId.value = ''
  form.value = defaultForm()
}

async function loadProviderOptions() {
  const response = await fetch(`${props.apiBaseUrl}/api/providers`)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || !payload || typeof payload !== 'object') {
    throw new Error('Failed to load provider options.')
  }
  providerOptions.value = payload
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
        createdBy: form.value.createdBy || 'local-user',
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
    await Promise.all([loadProviderOptions(), loadPresets()])
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
            <p v-if="preset.description" class="preset-desc">{{ preset.description }}</p>
            <div v-if="Array.isArray(preset.tags) && preset.tags.length" class="chip-row">
              <span v-for="tag in preset.tags.slice(0, 3)" :key="`${preset.id}-${tag}`" class="chip">#{{ tag }}</span>
            </div>
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
        <h3>Identity</h3>
        <div class="form-grid">
          <div class="control-field">
            <label>Name</label>
            <input v-model="form.name" :disabled="isLoading" />
          </div>
          <div class="control-field">
            <label>Created By</label>
            <input v-model="form.createdBy" :disabled="isLoading" />
          </div>
          <div class="control-field full">
            <label>Description</label>
            <textarea v-model="form.description" rows="2" :disabled="isLoading" />
          </div>
          <div class="control-field full">
            <label>Tags (comma separated)</label>
            <input v-model="form.tagsCsv" :disabled="isLoading" />
          </div>
        </div>
      </div>

      <div class="section-card">
        <h3>Model Config</h3>
        <div class="form-grid">
          <div class="control-field">
            <label>Provider</label>
            <select v-model="form.modelConfig.provider" :disabled="isLoading">
              <option value="">Select provider</option>
              <option v-for="providerName in Object.keys(providerOptions)" :key="providerName" :value="providerName">{{ providerName }}</option>
            </select>
          </div>
          <div class="control-field">
            <label>Model</label>
            <select v-model="form.modelConfig.modelId" :disabled="isLoading">
              <option value="">Select model</option>
              <option v-for="model in modelOptions" :key="model.id" :value="model.id">{{ model.label }}</option>
            </select>
          </div>
        </div>
      </div>

      <div class="section-card">
        <h3>Prompting</h3>
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
        <h3>Generation Params</h3>
        <div class="form-grid">
          <div class="control-field"><label>Steps</label><input v-model="form.generationParams.steps" type="number" /></div>
          <div class="control-field"><label>Guidance Scale</label><input v-model="form.generationParams.guidanceScale" type="number" step="0.1" /></div>
          <div class="control-field"><label>Size</label><input v-model="form.generationParams.size" placeholder="1024x1024" /></div>
          <div class="control-field"><label>Quality</label><input v-model="form.generationParams.quality" /></div>
        </div>
      </div>

      <div class="section-card">
        <h3>Reference Rules</h3>
        <div class="form-grid">
          <div class="control-field">
            <label>Reference Mode</label>
            <select v-model="form.referenceRules.referenceMode">
              <option value="none">none</option>
              <option value="optional">optional</option>
              <option value="required">required</option>
            </select>
          </div>
          <div class="control-field"><label>Max References</label><input v-model="form.referenceRules.maxReferenceImages" type="number" min="0" /></div>
          <div class="control-field">
            <label>Reference Purpose</label>
            <select v-model="form.referenceRules.referencePurpose">
              <option value="style">style</option>
              <option value="content">content</option>
              <option value="both">both</option>
            </select>
          </div>
        </div>
      </div>

      <div class="section-card">
        <h3>Output Rules</h3>
        <div class="form-grid">
          <div class="control-field">
            <label>Output Format</label>
            <select v-model="form.outputRules.outputFormat">
              <option value="png">png</option>
              <option value="jpg">jpg</option>
              <option value="webp">webp</option>
            </select>
          </div>
          <div class="control-field">
            <label>Upscale</label>
            <select v-model="form.outputRules.upscale">
              <option value="none">none</option>
              <option value="2x">2x</option>
              <option value="4x">4x</option>
            </select>
          </div>
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

.preset-desc {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.35;
  color: #7c6454;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chip-row {
  display: flex;
  gap: 0.3rem;
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid #d8cab8;
  background: #fff5e7;
  font-size: 0.68rem;
  padding: 0.12rem 0.45rem;
  color: #684f3f;
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
