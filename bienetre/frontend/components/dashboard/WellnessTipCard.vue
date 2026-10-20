<template>
  <article class="wellness-surface wellness-tip-card overflow-hidden p-6">
    <div class="grid gap-6 md:grid-cols-[1fr_180px] md:items-end">
      <div>
        <p class="text-sm uppercase tracking-[0.22em] text-[color:var(--ink-soft)]">Conseils du jour</p>
        <h3 class="mt-2 text-2xl font-semibold text-[color:var(--ink)]">{{ title }}</h3>
        <p class="mt-4 max-w-xl text-sm leading-7 text-[color:var(--ink-soft)]">{{ text }}</p>
        <button class="btn-secondary mt-6" type="button">{{ ctaLabel }}</button>
      </div>
      <img :src="image" :alt="title" class="h-40 w-full rounded-[28px] object-cover" />
    </div>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  text: string
  ctaLabel: string
  image: string
}>()
</script>
