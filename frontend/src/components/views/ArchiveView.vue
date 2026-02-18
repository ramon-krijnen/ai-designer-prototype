<script setup>
import { computed, onMounted, ref } from 'vue'
import { parseRunRecord } from '../../utils/imageParsers'

const props = defineProps({
  apiBaseUrl: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['open-image'])

const archiveRuns = ref([])
const archiveError = ref('')
const isArchiveLoading = ref(false)
const archiveOffset = ref(0)
const archivePageSize = 24
const hasMoreArchive = ref(true)
const archiveQuery = ref('')

const archiveCount = computed(() => archiveRuns.value.length)
const MAX_TARGET_LABELS = 4

const filteredRuns = computed(() => {
  const query = archiveQuery.value.trim().toLowerCase()
  if (!query) return archiveRuns.value

  return archiveRuns.value.filter((run) => {
    if (run.runId?.toLowerCase().includes(query)) return true
    if (run.modelTargets?.some((target) => targetLabel(target).toLowerCase().includes(query))) return true
    if (run.images?.some((image) => (image.prompt || '').toLowerCase().includes(query))) return true
    return false
  })
})

function targetLabel(target) {
  if (!target) return ''
  const provider = typeof target.provider === 'string' ? target.provider.trim() : ''
  const model = typeof target.model === 'string' ? target.model.trim() : ''
  if (provider && model) return `${provider} / ${model}`
  return provider || model
}

async function loadArchivePage({ reset = false } = {}) {
  if (isArchiveLoading.value) return

  isArchiveLoading.value = true
  archiveError.value = ''

  try {
    const nextOffset = reset ? 0 : archiveOffset.value
    const response = await fetch(`${props.apiBaseUrl}/api/runs?limit=${archivePageSize}&offset=${nextOffset}`)
    const payload = await response.json().catch(() => [])

    if (!response.ok) {
      throw new Error(payload.error || payload.details || 'Failed to load archive.')
    }
    if (!Array.isArray(payload)) {
      throw new Error('Unexpected response when loading archive.')
    }

    const parsed = payload.map((item, index) => parseRunRecord(item, nextOffset + index, props.apiBaseUrl)).filter(Boolean)
    archiveRuns.value = reset ? parsed : [...archiveRuns.value, ...parsed]
    archiveOffset.value = nextOffset + payload.length
    hasMoreArchive.value = payload.length === archivePageSize
  } catch (requestError) {
    archiveError.value = requestError instanceof Error ? requestError.message : 'Unexpected error.'
  } finally {
    isArchiveLoading.value = false
  }
}

function openImage(image) {
  if (!image?.src) return
  emit('open-image', image)
}

onMounted(() => {
  loadArchivePage({ reset: true })
})
</script>

<template>
  <div class="view-grid">
    <section class="panel">
      <div class="archive-toolbar">
        <button type="button" class="secondary" :disabled="isArchiveLoading" @click="loadArchivePage({ reset: true })">
          {{ isArchiveLoading ? 'Refreshing...' : 'Refresh Archive' }}
        </button>
        <span class="archive-count">{{ archiveCount }} run{{ archiveCount === 1 ? '' : 's' }} loaded</span>
      </div>

      <div class="search-wrap">
        <label for="archive-search">Filter runs</label>
        <input id="archive-search" v-model="archiveQuery" type="search" placeholder="Search run id, model, or prompt" />
      </div>

      <p v-if="archiveError" class="message error">{{ archiveError }}</p>
    </section>

    <section class="results">
      <div class="results-header">
        <h2>Archive</h2>
        <span>{{ filteredRuns.length }} visible</span>
      </div>

      <p v-if="!filteredRuns.length && !isArchiveLoading && !archiveError" class="empty-state">No matching archived runs found.</p>

      <div v-if="filteredRuns.length" class="run-list">
        <article v-for="(run, runIndex) in filteredRuns" :key="`${run.runId}-${runIndex}`" class="run-block">
          <div class="run-header">
            <p class="image-id">Run: {{ run.runId }}</p>
            <p class="image-details">
              <span>{{ run.imageCount }} image{{ run.imageCount === 1 ? '' : 's' }}</span>
              <span v-if="run.createdAt"> · {{ run.createdAt }}</span>
            </p>
          </div>

          <p v-if="run.modelTargets?.length" class="run-targets">
            Targets:
            {{
              run.modelTargets
                .slice(0, MAX_TARGET_LABELS)
                .map((target) => targetLabel(target))
                .filter(Boolean)
                .join(', ')
            }}
            <span v-if="run.modelTargets.length > MAX_TARGET_LABELS"> +{{ run.modelTargets.length - MAX_TARGET_LABELS }} more</span>
          </p>

          <div v-if="run.referenceImages?.length" class="reference-block">
            <p class="reference-title">Reference images ({{ run.referenceImages.length }})</p>
            <div class="reference-grid">
              <img
                v-for="(referenceImage, referenceIndex) in run.referenceImages"
                :key="`${referenceImage.id}-${referenceIndex}`"
                :src="referenceImage.src"
                :alt="referenceImage.name || `Run reference image ${referenceIndex + 1}`"
                loading="lazy"
                class="clickable-image"
                @click="openImage(referenceImage)"
              />
            </div>
          </div>

          <div class="image-grid">
            <article v-for="(image, imageIndex) in run.images" :key="`${image.id}-${imageIndex}`" class="image-card">
              <img :src="image.src" :alt="image.alt" class="clickable-image" loading="lazy" @click="openImage(image)" />
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
          {{ isArchiveLoading ? 'Loading...' : hasMoreArchive ? `Load More (${archivePageSize})` : 'All Runs Loaded' }}
        </button>
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

.archive-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.6rem;
}

.search-wrap {
  margin-top: 0.85rem;
  display: grid;
  gap: 0.35rem;
}

.search-wrap label {
  font-size: 0.82rem;
  color: #6e5949;
  font-weight: 700;
}

.search-wrap input {
  width: 100%;
  border: 1px solid #cab8a4;
  border-radius: 10px;
  padding: 0.62rem 0.75rem;
  font: inherit;
  color: #2b2018;
  background: #fffdf8;
}

.archive-count {
  color: #5c493a;
  font-size: 0.9rem;
}

button {
  justify-self: start;
  background: linear-gradient(130deg, #0b7f68 0%, #055145 100%);
  color: #f4fff9;
  border: 0;
  border-radius: 10px;
  padding: 0.6rem 1rem;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  background: #989186;
  cursor: not-allowed;
}

button.secondary {
  background: #fff5e8;
  color: #5c4739;
  border: 1px solid #d8c5ae;
}

button.secondary:disabled {
  background: #f1ebe2;
  color: #928577;
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

.run-list {
  display: grid;
  gap: 0.9rem;
}

.run-block {
  border: 1px solid #d8c7b2;
  border-radius: var(--radius-md);
  padding: 0.8rem;
  background: #fff8ed;
}

.run-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.65rem;
}

.run-targets {
  margin: 0 0 0.6rem;
  color: #5f4a3b;
  font-size: 0.82rem;
}

.reference-block {
  margin: 0 0 0.7rem;
  padding: 0.65rem;
  border: 1px solid #ddccb8;
  border-radius: 10px;
  background: #fffdf9;
}

.reference-title {
  margin: 0 0 0.5rem;
  color: #564233;
  font-size: 0.82rem;
  font-weight: 700;
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(60px, 1fr));
  gap: 0.45rem;
}

.reference-grid img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #ddccb8;
  background: #f4f8ff;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.9rem;
}

.image-card {
  border: 1px solid #d7c6b1;
  border-radius: 10px;
  overflow: hidden;
  background: #fffaf1;
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
  color: #3a2d22;
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
  color: #6a5648;
  font-size: 0.8rem;
}

.image-id {
  margin: 0.35rem 0 0;
  color: #7b6757;
  font-size: 0.75rem;
}

.archive-actions {
  margin-top: 1rem;
  display: flex;
  justify-content: center;
}

@media (min-width: 860px) {
  .panel,
  .results {
    padding: 1.25rem;
  }
}
</style>
