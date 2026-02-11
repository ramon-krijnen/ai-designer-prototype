<script setup>
defineProps({
  image: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['close'])

function close() {
  emit('close')
}
</script>

<template>
  <div class="lightbox" @click.self="close">
    <button type="button" class="lightbox-close" @click="close">Close</button>
    <img :src="image.src" :alt="image.alt || 'Preview image'" class="lightbox-image" />
  </div>
</template>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(8, 19, 38, 0.85);
  z-index: 30;
  display: grid;
  place-items: center;
  padding: 2rem;
}

.lightbox-image {
  max-width: min(95vw, 1600px);
  max-height: 88vh;
  width: auto;
  height: auto;
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
}

.lightbox-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: #ffffff;
  color: #173564;
  border: 1px solid #b7c7e3;
  border-radius: 10px;
  padding: 0.55rem 0.8rem;
  font-weight: 600;
  cursor: pointer;
}
</style>
