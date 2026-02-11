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

const archiveCount = computed(() => archiveRuns.value.length)

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

      <p v-if="archiveError" class="message error">{{ archiveError }}</p>
    </section>

    <section class="results">
      <div class="results-header">
        <h2>Archive</h2>
        <span v-if="archiveCount">{{ archiveCount }} run{{ archiveCount === 1 ? '' : 's' }}</span>
      </div>

      <p v-if="!archiveCount && !isArchiveLoading && !archiveError" class="empty-state">No archived runs found yet.</p>

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
  background: #ffffff;
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  padding: 1rem;
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

@media (min-width: 860px) {
  .panel,
  .results {
    padding: 1.25rem;
  }
}
</style>
