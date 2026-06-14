<script setup>
defineProps({
  title: String,
  desc: String,
  eyebrow: String,
});
</script>

<template>
  <header class="page-header">
    <div>
      <span v-if="eyebrow" class="eyebrow">{{ eyebrow }}</span>
      <h1>{{ title }}</h1>
      <p>{{ desc }}</p>
    </div>
    <div class="page-actions">
      <slot />
    </div>
  </header>
</template>
