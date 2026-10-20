<template>
  <article class="wellness-surface p-6">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-sm uppercase tracking-[0.22em] text-[color:var(--ink-soft)]">Courses</p>
        <h3 class="mt-2 text-2xl font-semibold text-[color:var(--ink)]">{{ title }}</h3>
      </div>
      <span class="wellness-chip">{{ items.filter((item) => item.checked).length }}/{{ items.length }}</span>
    </div>
    <div v-if="items.length" class="mt-5 space-y-3">
      <label v-for="item in items" :key="item.label" class="flex items-center gap-3 text-sm text-[color:var(--ink-soft)]">
        <input class="h-4 w-4 rounded border-white/20 bg-transparent accent-orange-500" type="checkbox" :checked="item.checked" />
        <span class="flex-1" :class="item.checked ? 'text-[color:var(--ink-muted)] line-through' : ''">{{ item.label }}</span>
        <span v-if="item.checked" class="text-emerald-400">●</span>
      </label>
    </div>
    <div v-else class="mt-5 rounded-[24px] border border-dashed border-white/15 px-4 py-6 text-sm text-[color:var(--ink-soft)]">
      Aucune liste de courses active pour aujourd'hui.
    </div>
    <NuxtLink :to="ctaTo" class="btn-primary mt-6 block w-full text-center">{{ ctaLabel }}</NuxtLink>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  ctaLabel: string
  ctaTo: string
  items: Array<{ label: string; checked: boolean }>
}>()
</script>
