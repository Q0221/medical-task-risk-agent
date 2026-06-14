<script setup>
import { computed } from "vue";

const props = defineProps({
  level: { type: String, default: "low" },
  compact: Boolean,
});

const config = computed(() => ({
  critical: { label: "紧急风险", className: "critical" },
  high: { label: "高风险", className: "high" },
  medium: { label: "中风险", className: "medium" },
  low: { label: "低风险", className: "low" },
}[props.level] || { label: "低风险", className: "low" }));
</script>

<template>
  <span class="risk-badge" :class="[config.className, { compact }]">
    <i></i>{{ compact ? config.label.replace("风险", "") : config.label }}
  </span>
</template>
