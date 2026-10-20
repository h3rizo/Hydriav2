<template>
  <div class="hydria-page home-page">
    <header class="mb-7 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p class="hydria-kicker">Hydria Terrain</p>
        <h1 class="mt-2 text-3xl font-bold tracking-[-0.035em] sm:text-4xl">{{ copy.greeting }}, {{ firstName }}</h1>
        <p class="hydria-muted mt-2 flex items-center gap-2 text-sm"><i class="fas fa-location-dot" aria-hidden="true"></i>{{ copy.sector }}</p>
      </div>
      <div class="sync-state" :class="isOnline ? 'is-online' : 'is-offline'" role="status">
        <i :class="isOnline ? 'fas fa-circle-check' : 'fas fa-cloud-slash'" aria-hidden="true"></i>
        <span><strong>{{ isOnline ? copy.synced : copy.offline }}</strong><small>{{ isOnline ? copy.syncedTime : copy.offlineHelp }}</small></span>
      </div>
    </header>

    <div class="home-grid">
      <section aria-labelledby="today-title">
        <div class="mb-3 flex items-center justify-between">
          <div><p class="hydria-kicker">{{ copy.today }}</p><h2 id="today-title" class="mt-1 text-2xl font-bold tracking-tight">{{ copy.priorities }}</h2></div>
          <NuxtLink to="/plannings" class="text-sm font-semibold" style="color:var(--hydria-cyan)">{{ copy.seePlanning }} <i class="fas fa-arrow-right ml-1" aria-hidden="true"></i></NuxtLink>
        </div>

        <article class="priority-hero hydria-panel">
          <span class="priority-icon"><i class="fas fa-droplet" aria-hidden="true"></i></span>
          <div><p class="hydria-tabular text-5xl font-bold tracking-[-0.06em]">12</p><p class="hydria-muted mt-1">{{ copy.interventions }}</p></div>
          <div class="priority-urgent"><p class="hydria-tabular text-4xl font-bold">4</p><p>{{ copy.urgent }}</p></div>
        </article>

        <div class="mt-4 hydria-panel-flat px-4">
          <NuxtLink v-for="item in priorities" :key="item.title" :to="item.to" class="hydria-row group">
            <span class="hydria-icon" :class="item.urgent ? 'urgent-icon' : ''"><i :class="item.icon" aria-hidden="true"></i></span>
            <span class="min-w-0 flex-1"><strong class="block truncate">{{ item.title }}</strong><small class="hydria-muted mt-1 flex items-center gap-1.5"><i class="fas fa-location-dot" aria-hidden="true"></i>{{ item.place }}</small></span>
            <span class="status-label" :class="item.urgent ? 'urgent' : 'planned'"><i :class="item.urgent ? 'fas fa-circle-exclamation' : 'fas fa-clock'" aria-hidden="true"></i>{{ item.urgent ? copy.urgent : copy.planned }}</span>
            <i class="fas fa-chevron-right hydria-muted transition group-hover:translate-x-1" aria-hidden="true"></i>
          </NuxtLink>
        </div>
      </section>

      <aside aria-labelledby="field-info-title">
        <div class="mb-3"><p class="hydria-kicker">{{ copy.fieldView }}</p><h2 id="field-info-title" class="mt-1 text-2xl font-bold tracking-tight">{{ copy.keyInfo }}</h2></div>
        <div class="metric-grid">
          <NuxtLink v-for="metric in metrics" :key="metric.label" :to="metric.to" class="metric-card hydria-panel-flat">
            <span class="hydria-icon" :class="metric.tone"><i :class="metric.icon" aria-hidden="true"></i></span>
            <p class="hydria-tabular mt-5 text-3xl font-bold tracking-tight">{{ metric.value }}</p>
            <p class="hydria-muted mt-1 text-sm">{{ metric.label }}</p>
          </NuxtLink>
        </div>

        <section class="mt-5 hydria-panel p-5" aria-labelledby="quick-title">
          <div class="flex items-center justify-between"><h3 id="quick-title" class="text-lg font-bold">{{ copy.quickActions }}</h3><span class="hydria-muted text-xs">{{ copy.touchHint }}</span></div>
          <div class="mt-4 grid grid-cols-2 gap-3">
            <NuxtLink v-for="action in actions" :key="action.to" :to="action.to" class="action-tile">
              <i :class="action.icon" aria-hidden="true"></i><span>{{ action.label }}</span>
            </NuxtLink>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
const { currentLang } = useLanguage()
const { user } = useAuth()
const isOnline = ref(true)

const copies = {
  fr: { greeting: 'Bonjour', sector: 'Secteur Ambohidratrimo', synced: 'Synchronisé', syncedTime: 'il y a 3 min', offline: 'Mode hors ligne', offlineHelp: 'Les saisies seront synchronisées', today: 'Jeudi 27 août', priorities: 'Priorités du jour', seePlanning: 'Voir le planning', interventions: 'interventions', urgent: 'Urgent', planned: 'Planifié', fieldView: 'Vue terrain', keyInfo: 'Informations clés', structures: 'Ouvrages actifs', sync: 'À synchroniser', alerts: 'Alertes', coverage: 'Disponibilité', quickActions: 'Actions rapides', touchHint: 'Accès direct', search: 'Rechercher', reading: 'Nouveau relevé', note: 'Prendre une note', map: 'Ouvrir la carte' },
  mg: { greeting: 'Manao ahoana', sector: 'Faritra Ambohidratrimo', synced: 'Voarindra', syncedTime: '3 minitra lasa', offline: 'Tsy misy tambajotra', offlineHelp: 'Hirindra rehefa miverina ny tambajotra', today: 'Alakamisy 27 Aogositra', priorities: 'Asa laharam-pahamehana', seePlanning: 'Hijery drafitr’asa', interventions: 'asa', urgent: 'Maika', planned: 'Voalahatra', fieldView: 'Fijery eny an-toerana', keyInfo: 'Angona manan-danja', structures: 'Fotodrafitrasa miasa', sync: 'Miandry fandrindrana', alerts: 'Fampitandremana', coverage: 'Fahafahana miasa', quickActions: 'Asa haingana', touchHint: 'Fidirana mivantana', search: 'Hitady', reading: 'Famakiana vaovao', note: 'Hanoratra', map: 'Hanokatra sarintany' },
}
const copy = computed(() => copies[currentLang.value] || copies.mg)
const firstName = computed(() => user.value?.first_name || user.value?.username || 'Tiana')

const priorities = computed(() => [
  { title: currentLang.value === 'fr' ? 'Fuite réseau' : 'Fivoahan-drano', place: 'Ambohimangakely', icon: 'fas fa-droplet-slash', urgent: true, to: '/plannings' },
  { title: currentLang.value === 'fr' ? 'Relevé compteur' : 'Famakiana metatra', place: 'Talatamaty', icon: 'fas fa-gauge-high', urgent: false, to: '/facturation' },
  { title: currentLang.value === 'fr' ? 'Contrôle pompe' : 'Fizahana paompy', place: 'Ivato', icon: 'fas fa-screwdriver-wrench', urgent: false, to: '/plannings' },
])
const metrics = computed(() => [
  { value: '142', label: copy.value.structures, icon: 'fas fa-water', tone: '', to: '/dashboard/infrastructure' },
  { value: '3', label: copy.value.sync, icon: 'fas fa-cloud-arrow-up', tone: '', to: '/dashboard/payments-volume-offline' },
  { value: '2', label: copy.value.alerts, icon: 'fas fa-bell', tone: 'is-warning', to: '/dashboard' },
  { value: '91 %', label: copy.value.coverage, icon: 'fas fa-signal', tone: '', to: '/dashboard' },
])
const actions = computed(() => [
  { label: copy.value.search, icon: 'fas fa-magnifying-glass', to: '/search' },
  { label: copy.value.reading, icon: 'fas fa-gauge-high', to: '/facturation' },
  { label: copy.value.note, icon: 'fas fa-note-sticky', to: '/notes' },
  { label: copy.value.map, icon: 'fas fa-map-location-dot', to: '/dashboard/map' },
])

const updateOnline = () => { isOnline.value = navigator.onLine }
onMounted(() => { updateOnline(); window.addEventListener('online', updateOnline); window.addEventListener('offline', updateOnline) })
onUnmounted(() => { window.removeEventListener('online', updateOnline); window.removeEventListener('offline', updateOnline) })
useHead({ title: 'Hydria Terrain' })
</script>

<style scoped>
.home-grid { display: grid; gap: 1.75rem; }
.sync-state { display: flex; width: fit-content; min-height: 3rem; align-items: center; gap: .7rem; border-radius: 1rem; padding: .6rem .85rem; }.sync-state i { font-size: 1.2rem; }.sync-state strong, .sync-state small { display: block; }.sync-state strong { font-size: .8rem; }.sync-state small { margin-top: .1rem; font-size: .68rem; opacity: .8; }.sync-state.is-online { background: color-mix(in srgb, var(--hydria-success) 12%, transparent); color: var(--hydria-success); }.sync-state.is-offline { background: color-mix(in srgb, var(--hydria-amber) 13%, transparent); color: var(--hydria-amber); }
.priority-hero { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 1rem; padding: 1.25rem; }.priority-icon { display: grid; width: 4.75rem; height: 4.75rem; place-items: center; border: 1px solid color-mix(in srgb, var(--hydria-cyan) 45%, transparent); border-radius: 1.35rem; background: color-mix(in srgb, var(--hydria-cyan) 10%, transparent); color: var(--hydria-cyan); font-size: 1.8rem; }.priority-urgent { border-left: 1px solid var(--hydria-line); padding-left: 1.1rem; color: var(--hydria-coral); text-align: center; }
.status-label { display: inline-flex; min-height: 2rem; align-items: center; gap: .35rem; border: 1px solid currentColor; border-radius: .7rem; padding: .3rem .55rem; font-size: .7rem; font-weight: 700; }.status-label.urgent { color: var(--hydria-coral); }.status-label.planned { color: var(--hydria-amber); }.urgent-icon { background: color-mix(in srgb, var(--hydria-coral) 12%, transparent); color: var(--hydria-coral); }
.metric-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .8rem; }.metric-card { min-height: 9.5rem; padding: 1rem; transition: transform 180ms ease, border-color 180ms ease; }.metric-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--hydria-cyan) 42%, transparent); }.hydria-icon.is-warning { background: color-mix(in srgb, var(--hydria-amber) 12%, transparent); color: var(--hydria-amber); }
.action-tile { display: flex; min-height: 5rem; flex-direction: column; justify-content: space-between; border: 1px solid var(--hydria-line); border-radius: .95rem; background: var(--hydria-surface-soft); padding: .9rem; font-size: .78rem; font-weight: 700; transition: border-color 180ms ease, transform 180ms ease; }.action-tile i { color: var(--hydria-cyan); font-size: 1.1rem; }.action-tile:hover { border-color: color-mix(in srgb, var(--hydria-cyan) 45%, transparent); transform: translateY(-1px); }
@media (min-width: 900px) { .home-grid { grid-template-columns: minmax(0,1.25fr) minmax(20rem,.75fr); align-items: start; }.priority-hero { padding: 1.6rem; }.metric-card { min-height: 10.5rem; } }
@media (max-width: 520px) { .priority-hero { grid-template-columns: auto 1fr; }.priority-icon { width: 3.8rem; height: 3.8rem; }.priority-urgent { grid-column: 1 / -1; display: flex; align-items: baseline; justify-content: center; gap: .5rem; border-top: 1px solid var(--hydria-line); border-left: 0; padding: .8rem 0 0; }.status-label { display: none; } }
</style>
