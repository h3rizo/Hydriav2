<template>
  <div class="dropdown dropdown-end">
    <!-- Bouton pour ouvrir le menu -->
    <div tabindex="0" role="button" class="btn btn-ghost btn-circle">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        stroke-width="1.5"
        stroke="currentColor"
        class="w-5 h-5"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="M10.5 21l5.25-11.25L21 21m-9-3h7.5M3 5.621a48.474 48.474 0 016-.371m0 0c1.605 0 3.192.083 4.758.249m-4.758-.249c1.433-7.51 9.257-7.51 10.69 0A48.55 48.55 0 0112 5.621m0 0c3.445 0 6.775.84 9.622 2.437M12 5.621c-3.445 0-6.775.84-9.622 2.437"
        />
      </svg>
    </div>

    <!-- Menu déroulant -->
    <ul
      tabindex="0"
      class="menu dropdown-content z-[1] p-2 shadow bg-base-100 rounded-box w-52 mt-4"
    >
      <!-- Affichage de la langue actuelle -->
      <li class="menu-title">
        <span>{{ $t('language') }}</span>
      </li>
      <div class="divider my-0"></div>

      <!-- Liste des langues disponibles -->
      <li v-for="locale in availableLocales" :key="locale.code">
        <router-link
          :to="switchLocalePath(locale.code)"
          :class="{
            'active': $i18n.locale === locale.code,
            'font-semibold': $i18n.locale === locale.code
          }"
          class="flex items-center gap-2"
        >
          <!-- Icône pour la langue actuelle -->
          <svg
            v-if="$i18n.locale === locale.code"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke-width="1.5"
            stroke="currentColor"
            class="w-4 h-4"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>

          <!-- Espace réservé pour l'alignement si pas la langue actuelle -->
          <div v-else class="w-4 h-4"></div>

          {{ locale.name }}
        </router-link>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
// Utilisation du composable i18n pour accéder aux informations de langue
const { locale, locales } = useI18n()
const switchLocalePath = useSwitchLocalePath()

// Calcul des langues disponibles
const availableLocales = computed(() => {
  return locales.value.filter((l) => typeof l !== 'string')
})
</script>

<style scoped>
/* Styles personnalisés si nécessaires */
.dropdown-content {
  border: 1px solid hsl(var(--bc) / 0.2);
}

.menu-title span {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.6;
}
</style>