<template>
  <article class="wellness-media-card group">
    <div class="relative overflow-hidden rounded-[28px]">
      <img :src="image" :alt="title" class="h-56 w-full object-cover transition duration-500 group-hover:scale-[1.04]" />
      <div class="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-black/90 via-black/40 to-transparent"></div>
      <button class="absolute right-4 top-4 rounded-full border border-white/20 bg-black/35 p-2 text-white backdrop-blur" type="button" :aria-label="`Sauvegarder ${title}`">
        ♡
      </button>
      <div class="absolute bottom-4 left-4 right-4">
        <p class="text-xs uppercase tracking-[0.24em] text-orange-300">{{ category }}</p>
        <h3 class="mt-2 text-xl font-semibold text-white">{{ title }}</h3>
        <p class="mt-1 text-sm text-white/70">{{ subtitle }}</p>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  image: string
  category: string
  title: string
  subtitle: string
}>()
</script>
