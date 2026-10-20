<template>
  <article class="wellness-surface overflow-hidden p-6">
    <div class="flex items-center justify-between gap-4">
      <div>
        <p class="text-sm uppercase tracking-[0.22em] text-[color:var(--ink-soft)]">Suivi de progression</p>
        <h3 class="mt-2 text-2xl font-semibold text-[color:var(--ink)]">{{ title }}</h3>
      </div>
      <span class="wellness-chip">{{ periodLabel }}</span>
    </div>
    <div class="mt-6">
      <svg viewBox="0 0 320 120" class="h-36 w-full">
        <defs>
          <linearGradient id="progressLine" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#ff8a1e" />
            <stop offset="100%" stop-color="#ffb24c" />
          </linearGradient>
        </defs>
        <path d="M10 86 C40 98, 55 90, 78 72 S125 30, 158 40 S225 82, 256 54 S295 45, 310 52" fill="none" stroke="url(#progressLine)" stroke-width="4" stroke-linecap="round" />
        <circle cx="158" cy="40" r="6" fill="#ff8a1e" />
        <circle cx="256" cy="54" r="5" fill="#ff8a1e" />
      </svg>
    </div>
    <div class="grid gap-4 md:grid-cols-3">
      <div v-for="metric in metrics" :key="metric.label">
        <p class="text-xs uppercase tracking-[0.18em] text-[color:var(--ink-muted)]">{{ metric.label }}</p>
        <p class="mt-2 text-xl font-semibold text-[color:var(--ink)]">{{ metric.value }}</p>
      </div>
    </div>
    <p v-if="deltaLabel" class="mt-4 text-sm font-medium text-orange-300">{{ deltaLabel }}</p>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  periodLabel: string
  deltaLabel?: string
  metrics: Array<{ label: string; value: string }>
}>()
</script>
