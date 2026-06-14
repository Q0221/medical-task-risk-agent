<script setup>
defineProps({
  label: String,
  value: [String, Number],
  desc: String,
  icon: Object,
  tone: { type: String, default: "blue" },
  trend: String,
});
</script>

<template>
  <div class="metric-card">
    <div class="metric-icon" :class="tone">
      <el-icon><component :is="icon" /></el-icon>
    </div>
    <div class="metric-content">
      <span class="metric-label">{{ label }}</span>
      <div class="metric-line">
        <strong>{{ value }}</strong>
        <small v-if="trend" class="metric-trend">{{ trend }}</small>
      </div>
      <span class="metric-desc">{{ desc }}</span>
    </div>
  </div>
</template>
