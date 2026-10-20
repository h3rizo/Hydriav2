<template>
  <section class="wellness-hero-shell overflow-hidden p-5 sm:p-8">
    <div class="grid gap-8 xl:grid-cols-[0.98fr_1.02fr] xl:items-center">
      <div class="space-y-6">
        <div class="space-y-4">
          <h1 class="wellness-hero-title">
            Votre bien-etre,<br />
            votre nutrition,<br />
            votre <span class="text-orange-500">equilibre.</span>
          </h1>
          <p class="max-w-2xl text-lg leading-8 text-[color:var(--ink-soft)]">
            Suivez votre alimentation, bougez chaque jour et atteignez vos objectifs durablement.
          </p>
        </div>
        <div class="flex flex-wrap gap-3">
          <NuxtLink to="/meal-plans" class="btn-primary">Commencer maintenant</NuxtLink>
          <NuxtLink to="/dashboard" class="btn-secondary">Voir la demo</NuxtLink>
        </div>
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex -space-x-3">
            <img v-for="(avatar, index) in avatars" :key="`hero-avatar-${index}`" :src="avatar" alt="Utilisateur actif" class="h-12 w-12 rounded-full border-2 border-black/30 object-cover" />
          </div>
          <p class="text-sm leading-6 text-[color:var(--ink-soft)]">
            <span class="font-semibold text-[color:var(--ink)]">+12k utilisateurs actifs</span><br />
            deja en meilleure sante
          </p>
        </div>
      </div>

      <div class="relative">
        <div class="absolute -left-6 bottom-10 z-10 hidden w-36 rounded-[26px] border border-white/10 bg-black/55 p-4 backdrop-blur md:block">
          <p class="text-sm text-orange-300">🔥 Streak</p>
          <p class="mt-2 text-4xl font-semibold text-white">{{ streakDays }}</p>
          <p class="text-sm text-white/70">jours</p>
        </div>
        <img :src="image" alt="Plat sain premium" class="h-full min-h-[320px] w-full rounded-[34px] object-cover shadow-[0_30px_80px_rgba(0,0,0,0.42)]" />
      </div>
    </div>
    <div class="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article v-for="card in quickCards" :key="card.title" class="wellness-quick-card p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="wellness-icon-shell" :style="{ '--wellness-icon-tint': card.tint }">
            <span aria-hidden="true">{{ card.icon }}</span>
          </div>
          <span class="text-sm text-[color:var(--ink-muted)]">→</span>
        </div>
        <h3 class="mt-5 text-xl font-semibold text-[color:var(--ink)]">{{ card.title }}</h3>
        <p class="mt-2 text-sm leading-6 text-[color:var(--ink-soft)]">{{ card.text }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  image: string
  streakDays: number
  avatars: string[]
  quickCards: Array<{ icon: string; title: string; text: string; tint: string }>
}>()
</script>
