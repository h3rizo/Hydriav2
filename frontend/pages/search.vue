<template>
  <div class="hydria-page mx-auto max-w-5xl">
    <header class="mb-6"><p class="hydria-kicker">Hydria Terrain</p><h1 class="mt-2 text-3xl font-bold tracking-[-0.04em] sm:text-4xl">{{ copy.title }}</h1><p class="hydria-muted mt-2 max-w-2xl">{{ copy.subtitle }}</p></header>

    <form class="search-shell hydria-panel" role="search" @submit.prevent="performSearch">
      <label for="global-search" class="sr-only">{{ t('search.label') }}</label>
      <div class="search-field">
        <i class="fas fa-magnifying-glass" aria-hidden="true"></i>
        <input id="global-search" ref="searchInput" v-model="searchQuery" type="search" autocomplete="off" :placeholder="copy.placeholder" :aria-describedby="feedbackMessage ? 'search-feedback' : 'offline-search-help'" />
        <button v-if="searchQuery" type="button" class="clear-button" :aria-label="copy.clear" @click="clearSearch"><i class="fas fa-xmark" aria-hidden="true"></i></button>
        <button type="submit" class="search-button" :aria-label="t('search.submit')" :disabled="isLoading"><span v-if="isLoading" class="loading loading-spinner loading-sm" aria-hidden="true"></span><i v-else class="fas fa-arrow-right" aria-hidden="true"></i><span class="hidden sm:inline">{{ t('search.submit') }}</span></button>
      </div>
      <p id="offline-search-help" class="offline-hint"><i class="fas fa-cloud-arrow-down" aria-hidden="true"></i>{{ copy.offlineAvailable }}</p>
      <p v-if="feedbackMessage" id="search-feedback" class="feedback" :class="feedbackType === 'error' ? 'is-error' : ''" role="status"><i :class="feedbackType === 'error' ? 'fas fa-circle-exclamation' : 'fas fa-circle-info'" aria-hidden="true"></i>{{ feedbackMessage }}</p>

      <fieldset class="mt-5"><legend class="sr-only">{{ t('common.filter') }}</legend><div class="filter-list" role="group">
        <button v-for="filter in filters" :key="filter.value" type="button" class="filter-button" :class="{ 'is-active': selectedFilter === filter.value }" :aria-pressed="selectedFilter === filter.value" @click="selectedFilter = filter.value"><i :class="filter.icon" aria-hidden="true"></i>{{ t(filter.labelKey) }}</button>
      </div></fieldset>
    </form>

    <section class="mt-7" aria-live="polite" :aria-busy="isLoading">
      <div v-if="isLoading" class="space-y-3" :aria-label="t('dashboard.loading')"><div v-for="index in 3" :key="index" class="h-28 animate-pulse rounded-2xl" style="background:var(--hydria-surface-soft)"></div></div>

      <template v-else-if="hasSearched && filteredResults.length">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-xl font-bold">{{ copy.results }}</h2><span class="result-count">{{ filteredResults.length }}</span></div>
        <div class="hydria-panel-flat px-4">
          <article v-for="result in filteredResults" :key="result.id" class="hydria-row result-row">
            <span class="hydria-icon"><i :class="getTypeIcon(result.type)" aria-hidden="true"></i></span>
            <div class="min-w-0 flex-1"><span class="result-type">{{ result.type }}</span><h3 class="mt-1 truncate font-bold">{{ result.title }}</h3><p class="hydria-muted mt-1 line-clamp-2 text-sm">{{ result.description }}</p></div>
            <NuxtLink :to="result.url" class="row-action" :aria-label="`${t('search.view')} ${result.title}`"><i class="fas fa-chevron-right" aria-hidden="true"></i></NuxtLink>
          </article>
        </div>
      </template>

      <div v-else-if="hasSearched" class="empty-state hydria-panel-flat"><span class="hydria-icon mx-auto"><i class="fas fa-magnifying-glass" aria-hidden="true"></i></span><h2 class="mt-4 text-xl font-bold">{{ t('search.no_results') }}</h2><p class="hydria-muted mt-2">{{ t('search.try_again') }}</p><button type="button" class="mt-5 text-sm font-bold" style="color:var(--hydria-cyan)" @click="focusSearch">{{ copy.changeSearch }}</button></div>

      <template v-else>
        <section aria-labelledby="nearby-title"><div class="mb-3 flex items-center justify-between"><div><p class="hydria-kicker">{{ copy.field }}</p><h2 id="nearby-title" class="mt-1 text-xl font-bold">{{ copy.nearby }}</h2></div><span class="hydria-muted text-xs"><i class="fas fa-location-crosshairs mr-1" aria-hidden="true"></i>{{ copy.approximate }}</span></div>
          <div class="hydria-panel-flat px-4"><NuxtLink v-for="place in nearby" :key="place.code" :to="place.to" class="hydria-row group"><span class="hydria-icon"><i :class="place.icon" aria-hidden="true"></i></span><span class="min-w-0 flex-1"><strong class="block truncate">{{ place.title }}</strong><small class="hydria-muted mt-1 block">{{ place.code }}</small><span class="place-meta"><i class="fas fa-location-dot" aria-hidden="true"></i>{{ place.distance }}<span aria-hidden="true">·</span><span :class="place.warning ? 'warning-text' : 'success-text'"><i :class="place.warning ? 'fas fa-screwdriver-wrench' : 'fas fa-circle-check'" aria-hidden="true"></i>{{ place.warning ? copy.maintenance : copy.inService }}</span></span></span><i class="fas fa-chevron-right hydria-muted transition group-hover:translate-x-1" aria-hidden="true"></i></NuxtLink></div>
        </section>

        <section class="mt-7" aria-labelledby="recent-title"><h2 id="recent-title" class="mb-3 text-xl font-bold">{{ copy.recent }}</h2><div class="grid gap-3 sm:grid-cols-2"><button v-for="item in recentSearches" :key="item.code" type="button" class="recent-search hydria-panel-flat" @click="runRecent(item.title)"><span class="hydria-icon"><i class="fas fa-clock-rotate-left" aria-hidden="true"></i></span><span class="min-w-0 text-left"><strong class="block truncate">{{ item.title }}</strong><small class="hydria-muted">{{ item.code }}</small></span><i class="fas fa-arrow-up-right hydria-muted ml-auto" aria-hidden="true"></i></button></div></section>
      </template>
    </section>
  </div>
</template>

<script setup>
const { currentLang, getTranslation: t } = useLanguage()
const config = useRuntimeConfig()
const searchInput = ref(null)
const searchQuery = ref('')
const selectedFilter = ref('all')
const isLoading = ref(false)
const hasSearched = ref(false)
const results = ref([])
const feedbackMessage = ref('')
const feedbackType = ref('info')

const copies = {
  fr: { title: 'Rechercher un ouvrage', subtitle: 'Retrouvez rapidement un ouvrage, un point d’eau, un équipement ou un village.', placeholder: 'Nom, village, code ou GPS', clear: 'Effacer la recherche', offlineAvailable: 'La recherche hors ligne reste disponible pour les données synchronisées.', results: 'Résultats', changeSearch: 'Modifier la recherche', field: 'Autour de vous', nearby: 'À proximité', approximate: 'Distances indicatives', maintenance: 'Maintenance', inService: 'En service', recent: 'Recherches récentes' },
  mg: { title: 'Hitady fotodrafitrasa', subtitle: 'Tadiavo haingana ny fotodrafitrasa, toerana fakana rano, fitaovana na tanàna.', placeholder: 'Anarana, tanàna, kaody na GPS', clear: 'Hamafa ny fikarohana', offlineAvailable: 'Mbola azo tadiavina ny angona efa voarindra na tsy misy tambajotra aza.', results: 'Valin’ny fikarohana', changeSearch: 'Hanova ny fikarohana', field: 'Manodidina anao', nearby: 'Akaiky', approximate: 'Tombana ny halavirana', maintenance: 'Amboarina', inService: 'Miasa', recent: 'Fikarohana farany' },
}
const copy = computed(() => copies[currentLang.value] || copies.mg)
const filters = [
  { value: 'all', labelKey: 'search.all', icon: 'fas fa-border-all' }, { value: 'ouvrage', labelKey: 'search.structures', icon: 'fas fa-water' }, { value: 'point_eau', labelKey: 'search.water_points', icon: 'fas fa-droplet' }, { value: 'equipement', labelKey: 'search.equipment', icon: 'fas fa-gears' }, { value: 'village', labelKey: 'search.villages', icon: 'fas fa-location-dot' },
]
const typeMapping = { ouvrage: 'Ouvrage', point_eau: "Point d'eau", equipement: 'Équipement', village: 'Village' }
const filteredResults = computed(() => selectedFilter.value === 'all' ? results.value : results.value.filter(result => result.type === typeMapping[selectedFilter.value]))
const nearby = computed(() => [
  { title: currentLang.value === 'fr' ? 'Château d’eau Talatamaty' : 'Tilikambon-drano Talatamaty', code: 'TLM-CH-0012', distance: '850 m', icon: 'fas fa-tower-water', warning: false, to: '/dashboard/infrastructure' },
  { title: currentLang.value === 'fr' ? 'Pompe solaire Ambohimanga' : 'Paompy masoandro Ambohimanga', code: 'AMB-PS-0045', distance: '1,4 km', icon: 'fas fa-solar-panel', warning: true, to: '/dashboard/infrastructure' },
  { title: currentLang.value === 'fr' ? 'Borne-fontaine Ivato' : 'Paompin-drano Ivato', code: 'IVA-BF-0108', distance: '2,1 km', icon: 'fas fa-faucet-drip', warning: false, to: '/dashboard/infrastructure' },
])
const recentSearches = computed(() => [{ title: currentLang.value === 'fr' ? 'Réservoir Ankadikely' : 'Fitahirizan-drano Ankadikely', code: 'ANK-RES-0007' }, { title: currentLang.value === 'fr' ? 'Forage Soamanandrariny' : 'Lavadrano Soamanandrariny', code: 'SOA-FOR-0021' }])

const performSearch = async () => { const query = searchQuery.value.trim(); feedbackMessage.value = ''; if (query.length < 2) { feedbackType.value = 'error'; feedbackMessage.value = t('search.min_length'); return } isLoading.value = true; hasSearched.value = true; try { const response = await $fetch(`${config.public.apiBaseUrl}/api/search/`, { params: { q: query } }); results.value = response.success ? response.results : []; if (!response.success) { feedbackType.value = 'error'; feedbackMessage.value = response.error || t('search.server_error') } } catch (error) { console.error('Search error:', error); results.value = []; feedbackType.value = 'error'; feedbackMessage.value = t('search.server_error') } finally { isLoading.value = false } }
const clearSearch = () => { searchQuery.value = ''; results.value = []; hasSearched.value = false; feedbackMessage.value = ''; nextTick(() => searchInput.value?.focus()) }
const focusSearch = () => nextTick(() => searchInput.value?.focus())
const runRecent = title => { searchQuery.value = title; performSearch() }
const getTypeIcon = type => ({ Ouvrage: 'fas fa-water', "Point d'eau": 'fas fa-droplet', Équipement: 'fas fa-gears', Village: 'fas fa-location-dot', Employé: 'fas fa-user' }[type] || 'fas fa-circle')
useHead({ title: () => `${copy.value.title} · Hydria Terrain` })
</script>

<style scoped>
.search-shell { padding: 1rem; }.search-field { display: grid; grid-template-columns: auto 1fr auto auto; align-items: center; gap: .7rem; min-height: 3.6rem; border: 1px solid color-mix(in srgb,var(--hydria-cyan) 38%,var(--hydria-line)); border-radius: 1rem; background: var(--hydria-surface-soft); padding: .35rem .4rem .35rem 1rem; }.search-field > i { color: var(--hydria-cyan); font-size: 1.05rem; }.search-field input { min-width: 0; height: 2.8rem; border: 0; background: transparent; color: var(--hydria-text); font-size: 1rem; outline: 0; }.search-field input::placeholder { color: var(--hydria-muted); opacity: .85; }.clear-button { display: grid; width: 2.5rem; height: 2.5rem; place-items: center; border-radius: .75rem; color: var(--hydria-muted); }.search-button { display: inline-flex; min-width: 2.9rem; min-height: 2.9rem; align-items: center; justify-content: center; gap: .45rem; border-radius: .8rem; background: var(--hydria-cyan); padding: 0 .85rem; color: #041a20; font-weight: 700; }.search-button:disabled { opacity: .65; }.offline-hint, .feedback { display: flex; align-items: flex-start; gap: .55rem; margin-top: .8rem; color: var(--hydria-cyan); font-size: .75rem; }.feedback.is-error { color: var(--hydria-coral); }.filter-list { display: flex; gap: .55rem; overflow-x: auto; padding-bottom: .2rem; scrollbar-width: thin; }.filter-button { display: inline-flex; min-height: 2.65rem; flex: 0 0 auto; align-items: center; gap: .45rem; border: 1px solid var(--hydria-line); border-radius: .8rem; padding: 0 .8rem; color: var(--hydria-muted); font-size: .75rem; font-weight: 600; }.filter-button.is-active { border-color: var(--hydria-cyan); background: color-mix(in srgb,var(--hydria-cyan) 10%,transparent); color: var(--hydria-cyan); }.result-count { display: grid; width: 2rem; height: 2rem; place-items: center; border-radius: .65rem; background: color-mix(in srgb,var(--hydria-cyan) 12%,transparent); color: var(--hydria-cyan); font-size: .75rem; font-weight: 800; }.result-row { padding: .65rem 0; }.result-type { color: var(--hydria-cyan); font-size: .65rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }.row-action { display: grid; width: 2.75rem; height: 2.75rem; place-items: center; border-radius: .8rem; color: var(--hydria-muted); }.row-action:hover { background: var(--hydria-surface-soft); color: var(--hydria-cyan); }.empty-state { padding: 3rem 1.25rem; text-align: center; }.place-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-top: .45rem; color: var(--hydria-cyan); font-size: .72rem; }.place-meta .success-text { color: var(--hydria-success); }.place-meta .warning-text { color: var(--hydria-amber); }.place-meta span { display: inline-flex; align-items: center; gap: .3rem; }.recent-search { display: flex; min-height: 4.5rem; align-items: center; gap: .8rem; padding: .7rem; transition: border-color 180ms ease, transform 180ms ease; }.recent-search:hover { border-color: color-mix(in srgb,var(--hydria-cyan) 42%,transparent); transform: translateY(-1px); }
@media (min-width: 640px) { .search-shell { padding: 1.35rem; }.search-field { min-height: 4rem; }.search-field input { font-size: 1.1rem; } }
</style>
