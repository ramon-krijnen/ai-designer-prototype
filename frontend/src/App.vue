<script setup>
import { computed, ref } from 'vue'
import ArchiveView from './components/views/ArchiveView.vue'
import GenerationView from './components/views/GenerationView.vue'
import PresetsView from './components/views/PresetsView.vue'
import LightboxModal from './components/LightboxModal.vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

const activeTab = ref('generate')
const lightboxImage = ref(null)
const presetSelection = ref(null)

const activeDescription = computed(() => {
  if (activeTab.value === 'generate') {
    return 'Compose runs across providers, or apply a saved preset for reproducible output.'
  }
  if (activeTab.value === 'presets') {
    return 'Build reusable generation setups with versioned prompt templates and model settings.'
  }
  return 'Inspect historical runs, compare prompts, and revisit references.'
})

function openLightbox(image) {
  if (!image?.src) return
  lightboxImage.value = image
}

function closeLightbox() {
  lightboxImage.value = null
}

function handleUsePreset(payload) {
  if (!payload || typeof payload !== 'object') return
  presetSelection.value = {
    presetId: typeof payload.presetId === 'string' ? payload.presetId : '',
    presetVersion: typeof payload.presetVersion === 'number' ? payload.presetVersion : undefined,
  }
  activeTab.value = 'generate'
}
</script>

<template>
  <main class="app-shell">
    <section class="hero">
      <p class="kicker">AI Design Studio</p>
      <h1>Flexible<br>AI<br>Research<br>Tool</h1>
      <p class="subtitle">{{ activeDescription }}</p>

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
          :class="{ active: activeTab === 'presets' }"
          role="tab"
          :aria-selected="activeTab === 'presets'"
          @click="activeTab = 'presets'"
        >
          Presets
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
    </section>

    <GenerationView
      v-if="activeTab === 'generate'"
      :api-base-url="API_BASE_URL"
      :preset-selection="presetSelection"
      @open-image="openLightbox"
    />
    <PresetsView
      v-else-if="activeTab === 'presets'"
      :api-base-url="API_BASE_URL"
      @use-preset="handleUsePreset"
    />
    <ArchiveView v-else :api-base-url="API_BASE_URL" @open-image="openLightbox" />

    <LightboxModal v-if="lightboxImage" :image="lightboxImage" @close="closeLightbox" />
  </main>
</template>

<style scoped>
.app-shell {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem 1rem 3rem;
  display: grid;
  gap: 1.25rem;
}

.hero {
  background: linear-gradient(140deg, rgba(255, 249, 239, 0.94) 0%, rgba(250, 240, 225, 0.98) 62%, rgba(232, 251, 245, 0.96) 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  padding: 1.1rem 1.1rem 1.3rem;
}

.kicker {
  margin: 0;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 0.72rem;
  color: var(--accent-strong);
  font-weight: 700;
}

h1 {
  font-family: 'Fraunces', Georgia, serif;
  font-size: clamp(1.5rem, 4vw, 2.2rem);
  line-height: 1.12;
  margin: 0.35rem 0 0.35rem;
  color: #2a1f18;
  max-width: 16ch;
}

.subtitle {
  color: var(--ink-soft);
  margin: 0 0 1rem;
  max-width: 60ch;
}

.tabs {
  display: inline-flex;
  gap: 0.4rem;
  background: rgba(255, 252, 247, 0.9);
  border: 1px solid #ddcbb5;
  border-radius: 999px;
  padding: 0.28rem;
}

.tab-btn {
  background: transparent;
  border: 0;
  color: #5f4a3e;
  border-radius: 999px;
  padding: 0.42rem 0.95rem;
  font-weight: 700;
  cursor: pointer;
}

.tab-btn.active {
  background: linear-gradient(130deg, #0b7f68 0%, #056253 100%);
  color: #f7fff9;
}

@media (min-width: 860px) {
  .app-shell {
    padding: 2rem 1.25rem 3rem;
  }

  .hero {
    padding: 1.35rem 1.35rem 1.5rem;
  }
}
</style>
