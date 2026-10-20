<template>
  <article class="wellness-surface p-6">
    <div class="flex items-center justify-between gap-4">
      <div>
        <p class="text-sm uppercase tracking-[0.22em] text-[color:var(--ink-soft)]">Objectif du jour</p>
        <h3 class="mt-2 text-2xl font-semibold text-[color:var(--ink)]">{{ title }}</h3>
      </div>
      <div class="wellness-ring">
        <div class="wellness-ring-core">
          <strong>{{ progress }}%</strong>
        </div>
      </div>
    </div>
    <div class="mt-6 space-y-4">
      <div v-for="item in items" :key="item.label" class="space-y-2">
        <div class="flex items-center justify-between gap-3 text-sm">
          <span class="text-[color:var(--ink)]">{{ item.label }}</span>
          <span class="text-[color:var(--ink-soft)]">{{ item.value }}</span>
        </div>
        <div class="wellness-progress-track">
          <div class="wellness-progress-fill" :style="{ width: `${item.percent}%`, background: item.color }"></div>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  progress: number
  items: Array<{ label: string; value: string; percent: number; color: string }>
}>()
</script>
