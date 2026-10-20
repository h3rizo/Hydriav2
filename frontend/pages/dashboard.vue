<template>
  <div class="hydria-page dashboard-page">
    <header class="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div><p class="hydria-kicker">Hydria Terrain</p><h1 class="mt-2 text-3xl font-bold tracking-[-0.04em] sm:text-4xl">{{ copy.title }}</h1><p class="hydria-muted mt-2">{{ copy.subtitle }}</p></div>
      <label class="sector-filter"><i class="fas fa-sliders" aria-hidden="true"></i><span class="sr-only">{{ copy.filter }}</span><select v-model="sector"><option value="all">{{ copy.allSectors }}</option><option value="ambohidratrimo">Ambohidratrimo</option><option value="ivato">Ivato</option></select></label>
    </header>

    <div v-if="loading" class="space-y-4" aria-busy="true" :aria-label="t('dashboard.loading')">
      <div class="h-60 animate-pulse rounded-2xl" style="background:var(--hydria-surface-soft)"></div><div class="grid gap-4 sm:grid-cols-2"><div class="h-44 animate-pulse rounded-2xl" style="background:var(--hydria-surface-soft)"></div><div class="h-44 animate-pulse rounded-2xl" style="background:var(--hydria-surface-soft)"></div></div>
    </div>

    <div v-else-if="loadError" class="hydria-panel p-8 text-center" role="alert">
      <span class="mx-auto hydria-icon error-icon"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i></span><h2 class="mt-4 text-xl font-bold">{{ copy.loadFailed }}</h2><p class="hydria-muted mt-2">{{ loadError }}</p><button type="button" class="hydria-primary-action mt-5" @click="loadDashboard"><i class="fas fa-rotate" aria-hidden="true"></i>{{ t('common.retry') }}</button>
    </div>

    <template v-else>
      <div class="dashboard-grid">
        <section class="availability hydria-panel" aria-labelledby="availability-title">
          <div class="availability-main"><span class="availability-icon"><i class="fas fa-droplet" aria-hidden="true"></i></span><div><p id="availability-title" class="hydria-muted text-sm font-semibold">{{ copy.availability }}</p><p class="hydria-tabular mt-1 text-6xl font-bold tracking-[-0.065em]">91<span class="ml-1 text-3xl">%</span></p></div></div>
          <div class="trend"><i class="fas fa-arrow-trend-up" aria-hidden="true"></i><strong>+3,2 %</strong><small>{{ copy.thisMonth }}</small></div>
          <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="91" :aria-label="copy.availability"><span style="width:91%"></span></div>
          <div class="progress-scale hydria-tabular"><span>0 %</span><span>50 %</span><span>100 %</span></div>
        </section>

        <section class="metric-strip hydria-panel-flat" :aria-label="copy.keyMetrics">
          <div class="strip-item"><span class="hydria-icon"><i class="fas fa-water" aria-hidden="true"></i></span><div><p class="hydria-muted text-sm">{{ copy.volume }}</p><strong class="hydria-tabular">18 420 m³</strong><small>{{ copy.thisMonth }}</small></div></div>
          <div class="strip-item"><span class="hydria-icon error-icon"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i></span><div><p class="hydria-muted text-sm">{{ copy.incidents }}</p><strong class="hydria-tabular incident-number">7</strong><small>2 {{ copy.urgentPlural }}</small></div></div>
        </section>

        <section class="structure-state hydria-panel" aria-labelledby="structure-title">
          <div class="section-heading"><div><p class="hydria-kicker">{{ copy.network }}</p><h2 id="structure-title" class="mt-1 text-xl font-bold">{{ copy.structureState }}</h2></div><NuxtLink to="/dashboard/infrastructure" class="section-link">{{ t('common.view') }} <i class="fas fa-arrow-right" aria-hidden="true"></i></NuxtLink></div>
          <div class="structure-content"><div class="donut" role="img" :aria-label="copy.structureSummary"><div><strong class="hydria-tabular">142</strong><small>{{ copy.total }}</small></div></div><dl class="state-list"><div v-for="state in structureStates" :key="state.label"><dt><span :style="{background:state.color}"></span>{{ state.label }}</dt><dd class="hydria-tabular">{{ state.value }}</dd></div></dl></div>
        </section>

        <section class="watch-list hydria-panel" aria-labelledby="watch-title">
          <div class="section-heading"><div><p class="hydria-kicker">{{ copy.attention }}</p><h2 id="watch-title" class="mt-1 text-xl font-bold">{{ copy.watch }}</h2></div><span class="watch-count">2</span></div>
          <div class="mt-4">
            <NuxtLink v-for="alert in alerts" :key="alert.title" :to="alert.to" class="hydria-row group">
              <span class="hydria-icon" :class="alert.urgent ? 'error-icon' : 'warning-icon'"><i :class="alert.icon" aria-hidden="true"></i></span><span class="min-w-0 flex-1"><strong class="block truncate">{{ alert.title }}</strong><small :class="alert.urgent ? 'urgent-text' : 'warning-text'">{{ alert.detail }}</small></span><span class="alert-status" :class="alert.urgent ? 'urgent' : 'planned'"><i :class="alert.urgent ? 'fas fa-circle-exclamation' : 'fas fa-clock'" aria-hidden="true"></i>{{ alert.urgent ? copy.urgent : copy.planned }}</span><i class="fas fa-chevron-right hydria-muted transition group-hover:translate-x-1" aria-hidden="true"></i>
            </NuxtLink>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
const { currentLang, getTranslation: t } = useLanguage()
const { fetchDashboard } = useMockData()
const loading = ref(true)
const loadError = ref('')
const dashboardData = ref({ overview: {}, expenses: { categories: [] } })
const sector = ref('all')

const copies = {
  fr: { title: 'Tableau de bord', subtitle: 'Vue opérationnelle · Août 2026', filter: 'Filtrer par secteur', allSectors: 'Tous les secteurs', availability: 'Disponibilité du service', thisMonth: 'ce mois', keyMetrics: 'Indicateurs principaux', volume: 'Volume distribué', incidents: 'Incidents ouverts', urgentPlural: 'urgents', network: 'Réseau', structureState: 'État des ouvrages', structureSummary: '128 en service, 9 en maintenance et 5 à l’arrêt', total: 'ouvrages', attention: 'Attention requise', watch: 'À surveiller', urgent: 'Urgent', planned: 'Planifié', inService: 'En service', maintenance: 'Maintenance', stopped: 'À l’arrêt', loadFailed: 'Impossible de charger les indicateurs' },
  mg: { title: 'Tabilao', subtitle: 'Fijery ny asa · Aogositra 2026', filter: 'Hisivana araka ny faritra', allSectors: 'Faritra rehetra', availability: 'Fahafahan’ny tolotra miasa', thisMonth: 'ity volana ity', keyMetrics: 'Tarehimarika lehibe', volume: 'Rano nozaraina', incidents: 'Olana misokatra', urgentPlural: 'maika', network: 'Tambajotra', structureState: 'Toetry ny fotodrafitrasa', structureSummary: '128 miasa, 9 amboarina ary 5 mijanona', total: 'fotodrafitrasa', attention: 'Mila jerena', watch: 'Arahi-maso', urgent: 'Maika', planned: 'Voalahatra', inService: 'Miasa', maintenance: 'Amboarina', stopped: 'Mijanona', loadFailed: 'Tsy azo ny tarehimarika' },
}
const copy = computed(() => copies[currentLang.value] || copies.mg)
const structureStates = computed(() => [
  { label: copy.value.inService, value: 128, color: 'var(--hydria-cyan)' },
  { label: copy.value.maintenance, value: 9, color: 'var(--hydria-amber)' },
  { label: copy.value.stopped, value: 5, color: 'var(--hydria-coral)' },
])
const alerts = computed(() => [
  { title: currentLang.value === 'fr' ? 'Réservoir Andranotapahina' : 'Fitahirizan-drano Andranotapahina', detail: currentLang.value === 'fr' ? 'Niveau bas' : 'Ambany ny rano', icon: 'fas fa-water-ladder', urgent: false, to: '/dashboard/infrastructure' },
  { title: currentLang.value === 'fr' ? 'Pompe Ambohibao' : 'Paompy Ambohibao', detail: currentLang.value === 'fr' ? 'Vibration élevée' : 'Hovitrovitra mafy', icon: 'fas fa-gears', urgent: true, to: '/plannings' },
])

const loadDashboard = async () => { loading.value = true; loadError.value = ''; try { dashboardData.value = await fetchDashboard() } catch (error) { console.error('Dashboard loading error:', error); loadError.value = t('search.server_error') } finally { loading.value = false } }
onMounted(loadDashboard)
useHead({ title: () => `${copy.value.title} · Hydria Terrain` })
</script>

<style scoped>
.dashboard-grid { display: grid; gap: 1rem; }.sector-filter { display: inline-flex; min-height: 3rem; width: fit-content; align-items: center; gap: .65rem; border: 1px solid var(--hydria-line); border-radius: .9rem; background: var(--hydria-surface); padding: 0 .85rem; color: var(--hydria-cyan); }.sector-filter select { min-height: 2.75rem; border: 0; background: transparent; color: var(--hydria-text); font-size: .85rem; font-weight: 600; outline: none; }
.availability { position: relative; display: grid; grid-template-columns: 1fr auto; gap: 1rem; overflow: hidden; padding: 1.25rem; }.availability::after { position: absolute; inset: auto -4rem -7rem auto; width: 16rem; height: 16rem; border: 1px solid color-mix(in srgb,var(--hydria-cyan) 14%,transparent); border-radius: 50%; content: ''; }.availability-main { display: flex; align-items: center; gap: 1rem; }.availability-icon { display: grid; width: 4.5rem; height: 4.5rem; place-items: center; border: 1px solid color-mix(in srgb,var(--hydria-cyan) 45%,transparent); border-radius: 1.25rem; background: color-mix(in srgb,var(--hydria-cyan) 10%,transparent); color: var(--hydria-cyan); font-size: 1.7rem; }.trend { display: flex; flex-direction: column; align-items: flex-end; justify-content: center; color: var(--hydria-success); }.trend strong { margin-top: .25rem; }.trend small { color: var(--hydria-muted); }.progress-track { grid-column: 1 / -1; height: .65rem; overflow: hidden; border-radius: 999px; background: var(--hydria-surface-strong); }.progress-track span { display: block; height: 100%; border-radius: inherit; background: var(--hydria-cyan); box-shadow: 0 0 24px color-mix(in srgb,var(--hydria-cyan) 28%,transparent); }.progress-scale { grid-column: 1 / -1; display: flex; justify-content: space-between; color: var(--hydria-muted); font-size: .68rem; }
.metric-strip { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); padding: 1rem; }.strip-item { display: flex; min-width: 0; align-items: center; gap: .85rem; padding: .5rem; }.strip-item + .strip-item { border-left: 1px solid var(--hydria-line); padding-left: 1rem; }.strip-item strong, .strip-item small { display: block; }.strip-item strong { margin-top: .2rem; font-size: 1.35rem; }.strip-item small { margin-top: .1rem; color: var(--hydria-muted); font-size: .68rem; }.incident-number, .urgent-text { color: var(--hydria-coral); }
.structure-state, .watch-list { padding: 1.25rem; }.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }.section-link { color: var(--hydria-cyan); font-size: .78rem; font-weight: 700; }.structure-content { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 1.25rem; margin-top: 1.4rem; }.donut { display: grid; width: 8.25rem; height: 8.25rem; place-items: center; border-radius: 50%; background: conic-gradient(var(--hydria-cyan) 0 90.1%, var(--hydria-amber) 90.1% 96.5%, var(--hydria-coral) 96.5% 100%); }.donut::before { grid-area: 1/1; width: 5.8rem; height: 5.8rem; border-radius: 50%; background: var(--hydria-surface); content: ''; }.donut div { z-index: 1; grid-area: 1/1; text-align: center; }.donut strong, .donut small { display: block; }.donut strong { font-size: 1.7rem; }.donut small { color: var(--hydria-muted); font-size: .65rem; }.state-list div { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--hydria-line); padding: .7rem 0; }.state-list div:last-child { border-bottom: 0; }.state-list dt { display: flex; align-items: center; gap: .55rem; color: var(--hydria-muted); font-size: .78rem; }.state-list dt span { width: .55rem; height: .55rem; border-radius: 50%; }.state-list dd { font-weight: 700; }.watch-count { display: grid; width: 2rem; height: 2rem; place-items: center; border-radius: .7rem; background: color-mix(in srgb,var(--hydria-amber) 14%,transparent); color: var(--hydria-amber); font-size: .78rem; font-weight: 800; }.warning-icon { background: color-mix(in srgb,var(--hydria-amber) 12%,transparent); color: var(--hydria-amber); }.error-icon { background: color-mix(in srgb,var(--hydria-coral) 12%,transparent); color: var(--hydria-coral); }.warning-text { color: var(--hydria-amber); }.alert-status { display: inline-flex; min-height: 2rem; align-items: center; gap: .35rem; border: 1px solid currentColor; border-radius: .7rem; padding: .3rem .55rem; font-size: .68rem; font-weight: 700; }.alert-status.urgent { color: var(--hydria-coral); }.alert-status.planned { color: var(--hydria-amber); }
@media (min-width: 840px) { .dashboard-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }.availability { grid-column: 1 / -1; padding: 1.6rem; }.metric-strip { grid-column: 1 / -1; }.structure-state, .watch-list { min-height: 22rem; } }
@media (max-width: 520px) { .availability { grid-template-columns: 1fr; }.trend { position: absolute; right: 1.25rem; top: 1.5rem; }.availability-main { align-items: flex-end; }.availability-icon { width: 3.5rem; height: 3.5rem; }.metric-strip { grid-template-columns: 1fr; }.strip-item + .strip-item { border-top: 1px solid var(--hydria-line); border-left: 0; padding-left: .5rem; }.structure-content { grid-template-columns: 1fr; }.donut { margin: 0 auto; }.alert-status { display: none; } }
</style>
