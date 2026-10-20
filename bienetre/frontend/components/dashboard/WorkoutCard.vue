<template>
  <article class="wellness-media-card group">
    <div class="relative overflow-hidden rounded-[28px]">
      <img :src="image" :alt="title" class="h-52 w-full object-cover transition duration-500 group-hover:scale-[1.04]" />
      <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent"></div>
      <div class="absolute left-4 top-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-orange-500/20 text-white backdrop-blur">
        <span class="text-lg" aria-hidden="true">{{ icon }}</span>
      </div>
      <div class="absolute bottom-4 left-4 right-4">
        <h3 class="text-2xl font-semibold text-white">{{ title }}</h3>
        <p class="mt-1 text-sm text-white/72">{{ subtitle }}</p>
        <p class="mt-3 text-sm font-medium text-orange-300">{{ count }}</p>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  image: string
  icon: string
  title: string
  subtitle: string
  count: string
}>()
</script>
