<script setup>
import { ref } from 'vue'
import ArchiveView from './components/views/ArchiveView.vue'
import GenerationView from './components/views/GenerationView.vue'
import LightboxModal from './components/LightboxModal.vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

const activeTab = ref('generate')
const lightboxImage = ref(null)

function openLightbox(image) {
  if (!image?.src) return
  lightboxImage.value = image
}

function closeLightbox() {
  lightboxImage.value = null
}
</script>

<template>
  <main class="app-shell">
    <section class="panel">
      <h1>Flexible AI Research Tool (FART)</h1>
      <p class="subtitle">Generate images, then browse complete run history in Archive.</p>

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
          :class="{ active: activeTab === 'archive' }"
          role="tab"
          :aria-selected="activeTab === 'archive'"
          @click="activeTab = 'archive'"
        >
          Archive
        </button>
      </div>
    </section>

    <GenerationView v-if="activeTab === 'generate'" :api-base-url="API_BASE_URL" @open-image="openLightbox" />
    <ArchiveView v-else :api-base-url="API_BASE_URL" @open-image="openLightbox" />

    <LightboxModal v-if="lightboxImage" :image="lightboxImage" @close="closeLightbox" />
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

.panel {
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

.tabs {
  display: flex;
  gap: 0.55rem;
}

.tab-btn {
  background: #eff5ff;
  border: 1px solid #b9c9e3;
  color: #20457d;
  border-radius: 999px;
  padding: 0.4rem 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.tab-btn.active {
  background: #0e4cb3;
  border-color: #0e4cb3;
  color: #ffffff;
}

@media (min-width: 860px) {
  .app-shell {
    padding: 2rem 1.25rem 3rem;
  }

  .panel {
    padding: 1.25rem;
  }
}
</style>
