<template>
  <article class="wellness-surface p-5">
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-center gap-3">
        <span class="wellness-icon-shell" :style="{ '--wellness-icon-tint': toneColor }">
          <span class="text-lg" aria-hidden="true">{{ icon }}</span>
        </span>
        <div>
          <p class="text-sm font-semibold text-[color:var(--ink)]">{{ label }}</p>
          <p class="mt-1 text-xs text-[color:var(--ink-soft)]">{{ target }}</p>
        </div>
      </div>
      <span class="text-xs font-semibold" :style="{ color: toneColor }">{{ percent }} %</span>
    </div>
    <p class="mt-5 text-3xl font-semibold text-[color:var(--ink)]">{{ value }}</p>
    <div class="wellness-progress-track mt-4">
      <div class="wellness-progress-fill" :style="{ width: `${Math.max(0, Math.min(100, percent))}%`, background: toneGradient }"></div>
    </div>
  </article>
</template>

<script setup lang="ts">
const props = defineProps<{
  icon: string
  label: string
  value: string
  target: string
  percent: number
  tone?: "orange" | "green" | "yellow" | "violet" | "blue"
}>()

const toneMap = {
  orange: {
    color: "#ff8a1e",
    gradient: "linear-gradient(90deg, #ff8a1e, #ffb24c)",
  },
  green: {
    color: "#56d98c",
    gradient: "linear-gradient(90deg, #34d399, #6ee7b7)",
  },
  yellow: {
    color: "#f6c454",
    gradient: "linear-gradient(90deg, #f59e0b, #fcd34d)",
  },
  violet: {
    color: "#b078ff",
    gradient: "linear-gradient(90deg, #a855f7, #d8b4fe)",
  },
  blue: {
    color: "#46b7ff",
    gradient: "linear-gradient(90deg, #0ea5e9, #67e8f9)",
  },
} as const

const toneColor = computed(() => toneMap[props.tone || "orange"].color)
const toneGradient = computed(() => toneMap[props.tone || "orange"].gradient)
</script>
