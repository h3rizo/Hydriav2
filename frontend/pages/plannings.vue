<template>
  <div class="hydria-page mx-auto max-w-5xl">
    <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div><p class="hydria-kicker">Hydria Terrain</p><h1 class="mt-2 text-3xl font-bold tracking-[-0.04em] sm:text-4xl">{{ copy.title }}</h1><p class="hydria-muted mt-2">{{ copy.subtitle }}</p></div>
      <div class="sync-badge"><i class="fas fa-cloud-arrow-up" aria-hidden="true"></i><span><strong>{{ copy.synced }}</strong><small>{{ copy.syncedTime }}</small></span></div>
    </header>

    <section class="planning-toolbar hydria-panel" :aria-label="copy.navigation">
      <div class="date-navigation"><button type="button" class="toolbar-button" :aria-label="copy.previous" @click="shiftDay(-1)"><i class="fas fa-chevron-left" aria-hidden="true"></i></button><div><i class="fas fa-calendar-day" aria-hidden="true"></i><strong>{{ formattedDate }}</strong></div><button type="button" class="toolbar-button" :aria-label="copy.next" @click="shiftDay(1)"><i class="fas fa-chevron-right" aria-hidden="true"></i></button></div>
      <div class="view-switch" role="group" :aria-label="copy.view"><button type="button" :class="{ 'is-active': viewMode === 'day' }" :aria-pressed="viewMode === 'day'" @click="viewMode = 'day'">{{ copy.day }}</button><button type="button" :class="{ 'is-active': viewMode === 'week' }" :aria-pressed="viewMode === 'week'" @click="viewMode = 'week'">{{ copy.week }}</button></div>
    </section>

    <section class="progress-summary hydria-panel-flat" aria-labelledby="progress-title"><span class="progress-check"><i class="fas fa-check" aria-hidden="true"></i></span><div class="min-w-0 flex-1"><h2 id="progress-title" class="font-bold">{{ copy.progress }}</h2><div class="progress-line" role="progressbar" aria-valuemin="0" aria-valuemax="5" aria-valuenow="3"><span style="width:60%"></span></div></div><strong class="hydria-tabular">60 %</strong></section>

    <section class="mt-6" aria-labelledby="timeline-title">
      <div class="mb-3 flex items-center justify-between"><div><p class="hydria-kicker">{{ viewMode === 'day' ? copy.dayView : copy.weekView }}</p><h2 id="timeline-title" class="mt-1 text-xl font-bold">{{ copy.activities }}</h2></div><span class="hydria-muted text-xs">4 {{ copy.items }}</span></div>
      <ol class="timeline hydria-panel-flat px-4">
        <li v-for="activity in activities" :key="activity.id" class="timeline-item" :class="[`is-${activity.status}`, { 'is-expanded': activeActivityId === activity.id }]">
          <span class="timeline-marker"><i :class="statusIcon(activity.status)" aria-hidden="true"></i></span>
          <button type="button" class="activity-main" :aria-expanded="activeActivityId === activity.id" @click="toggleActivity(activity.id)">
            <time class="hydria-tabular">{{ activity.time }}</time><span class="min-w-0 flex-1 text-left"><strong class="block truncate">{{ activity.title }}</strong><small class="hydria-muted mt-1 flex items-center gap-1.5"><i class="fas fa-location-dot" aria-hidden="true"></i>{{ activity.place }}</small></span><span class="activity-status">{{ statusLabel(activity.status) }}</span><i class="fas fa-chevron-down hydria-muted chevron" aria-hidden="true"></i>
          </button>
          <div v-if="activeActivityId === activity.id" class="activity-detail">
            <div><span><i class="fas fa-user" aria-hidden="true"></i>{{ activity.agent }}</span><span><i class="fas fa-clock" aria-hidden="true"></i>{{ activity.duration }}</span></div>
            <NuxtLink :to="activity.to" class="hydria-primary-action"><i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i>{{ copy.openRecord }}</NuxtLink>
          </div>
        </li>
      </ol>
    </section>

    <NuxtLink to="/dashboard/payments-volume-offline" class="sync-pending hydria-panel-flat"><span class="hydria-icon"><i class="fas fa-cloud-arrow-up" aria-hidden="true"></i></span><span class="min-w-0 flex-1"><strong class="block">{{ copy.pending }}</strong><small class="hydria-muted mt-1 block">{{ copy.pendingHelp }}</small></span><i class="fas fa-chevron-right hydria-muted" aria-hidden="true"></i></NuxtLink>
  </div>
</template>

<script setup>
const { currentLang } = useLanguage()
const selectedDate = ref(new Date(2026, 7, 27))
const viewMode = ref('day')
const activeActivityId = ref(2)

const copies = {
  fr: { title: 'Planning', subtitle: 'Vos interventions et contrôles terrain', synced: 'Synchronisé', syncedTime: 'il y a 3 min', navigation: 'Navigation dans le planning', previous: 'Jour précédent', next: 'Jour suivant', view: 'Mode d’affichage', day: 'Jour', week: 'Semaine', progress: '3 interventions sur 5 terminées', dayView: 'Aujourd’hui', weekView: 'Cette semaine', activities: 'Interventions', items: 'activités', done: 'Terminé', current: 'En cours', urgent: 'Urgent', upcoming: 'À venir', openRecord: 'Ouvrir la fiche', pending: '2 modifications à synchroniser', pendingHelp: 'Les données seront envoyées dès le retour en ligne.' },
  mg: { title: 'Drafitr’asa', subtitle: 'Ireo asa sy fizahana eny an-toerana', synced: 'Voarindra', syncedTime: '3 minitra lasa', navigation: 'Fitetezana ny drafitr’asa', previous: 'Andro teo aloha', next: 'Andro manaraka', view: 'Fomba fijery', day: 'Andro', week: 'Herinandro', progress: 'Asa 3 amin’ny 5 no vita', dayView: 'Androany', weekView: 'Ity herinandro ity', activities: 'Asa', items: 'asa', done: 'Vita', current: 'Eo am-panaovana', urgent: 'Maika', upcoming: 'Ho avy', openRecord: 'Hanokatra ny fiche', pending: 'Fanovana 2 miandry fandrindrana', pendingHelp: 'Halefa ny angona rehefa miverina ny tambajotra.' },
}
const copy = computed(() => copies[currentLang.value] || copies.mg)
const formattedDate = computed(() => {
  if (currentLang.value === 'fr') return new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }).format(selectedDate.value)
  const weekdays = ['Alahady', 'Alatsinainy', 'Talata', 'Alarobia', 'Alakamisy', 'Zoma', 'Asabotsy']
  const months = ['Janoary', 'Febroary', 'Martsa', 'Aprily', 'Mey', 'Jona', 'Jolay', 'Aogositra', 'Septambra', 'Oktobra', 'Novambra', 'Desambra']
  return `${weekdays[selectedDate.value.getDay()]} ${selectedDate.value.getDate()} ${months[selectedDate.value.getMonth()]}`
})
const activities = computed(() => [
  { id: 1, time: '08:30', title: currentLang.value === 'fr' ? 'Relevé compteur' : 'Famakiana metatra', place: 'Talatamaty', status: 'done', agent: 'Tiana R.', duration: '45 min', to: '/facturation' },
  { id: 2, time: '10:15', title: currentLang.value === 'fr' ? 'Contrôle pompe' : 'Fizahana paompy', place: 'Ivato', status: 'current', agent: 'Tiana R.', duration: '1 h 15', to: '/notes' },
  { id: 3, time: '13:30', title: currentLang.value === 'fr' ? 'Réparer fuite' : 'Hanamboatra fivoahana', place: 'Ambohimangakely', status: 'urgent', agent: 'Équipe maintenance', duration: '2 h', to: '/notes' },
  { id: 4, time: '15:45', title: currentLang.value === 'fr' ? 'Inspection réservoir' : 'Fizahana fitahirizan-drano', place: 'Andranotapahina', status: 'upcoming', agent: 'Tiana R.', duration: '50 min', to: '/dashboard/infrastructure' },
])
const statusLabel = status => ({ done: copy.value.done, current: copy.value.current, urgent: copy.value.urgent, upcoming: copy.value.upcoming }[status])
const statusIcon = status => ({ done: 'fas fa-check', current: 'fas fa-clock', urgent: 'fas fa-exclamation', upcoming: 'fas fa-circle' }[status])
const toggleActivity = id => { activeActivityId.value = activeActivityId.value === id ? null : id }
const shiftDay = offset => { const next = new Date(selectedDate.value); next.setDate(next.getDate() + offset); selectedDate.value = next }
useHead({ title: () => `${copy.value.title} · Hydria Terrain` })
</script>

<style scoped>
.sync-badge { display: flex; width: fit-content; min-height: 3rem; align-items: center; gap: .7rem; border-radius: .9rem; background: color-mix(in srgb,var(--hydria-success) 12%,transparent); padding: .55rem .8rem; color: var(--hydria-success); }.sync-badge strong, .sync-badge small { display: block; }.sync-badge strong { font-size: .78rem; }.sync-badge small { margin-top: .1rem; font-size: .67rem; opacity: .8; }.planning-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; padding: .8rem; }.date-navigation { display: flex; min-width: 0; align-items: center; gap: .5rem; }.date-navigation > div { display: flex; min-width: 0; align-items: center; gap: .6rem; padding: 0 .5rem; text-transform: capitalize; }.date-navigation strong { white-space: nowrap; }.date-navigation > div i { color: var(--hydria-cyan); }.toolbar-button { display: grid; width: 2.85rem; height: 2.85rem; flex: 0 0 auto; place-items: center; border: 1px solid var(--hydria-line); border-radius: .85rem; background: var(--hydria-surface-soft); }.view-switch { display: inline-flex; border: 1px solid var(--hydria-line); border-radius: .85rem; background: var(--hydria-surface-soft); padding: .25rem; }.view-switch button { min-height: 2.35rem; border-radius: .65rem; padding: 0 .8rem; color: var(--hydria-muted); font-size: .75rem; font-weight: 700; }.view-switch button.is-active { background: color-mix(in srgb,var(--hydria-cyan) 14%,transparent); color: var(--hydria-cyan); }.progress-summary { display: flex; align-items: center; gap: .9rem; margin-top: 1rem; padding: 1rem; }.progress-check { display: grid; width: 2.6rem; height: 2.6rem; place-items: center; border: 1px solid var(--hydria-cyan); border-radius: .85rem; color: var(--hydria-cyan); }.progress-line { height: .45rem; margin-top: .65rem; overflow: hidden; border-radius: 999px; background: var(--hydria-surface-strong); }.progress-line span { display: block; height: 100%; border-radius: inherit; background: var(--hydria-cyan); }.timeline { position: relative; }.timeline::before { position: absolute; top: 2.6rem; bottom: 2.6rem; left: 2.05rem; width: 2px; background: var(--hydria-line); content: ''; }.timeline-item { position: relative; border-bottom: 1px solid var(--hydria-line); padding-left: 3.2rem; }.timeline-item:last-child { border-bottom: 0; }.timeline-marker { position: absolute; z-index: 1; left: .55rem; top: 1.25rem; display: grid; width: 3rem; height: 3rem; place-items: center; border: 2px solid var(--hydria-muted); border-radius: 50%; background: var(--hydria-surface); color: var(--hydria-muted); }.activity-main { display: grid; width: 100%; min-height: 5.5rem; grid-template-columns: auto minmax(0,1fr) auto auto; align-items: center; gap: .85rem; }.activity-main time { font-size: 1.2rem; font-weight: 700; }.activity-status { border: 1px solid currentColor; border-radius: .7rem; padding: .35rem .55rem; font-size: .68rem; font-weight: 700; }.chevron { transition: transform 180ms ease; }.is-expanded .chevron { transform: rotate(180deg); }.is-done .timeline-marker, .is-done .activity-status { color: var(--hydria-success); }.is-current .timeline-marker, .is-current .activity-status { color: var(--hydria-amber); }.is-urgent .timeline-marker, .is-urgent .activity-status { color: var(--hydria-coral); }.is-current.is-expanded { background: color-mix(in srgb,var(--hydria-amber) 5%,transparent); }.activity-detail { margin: -.2rem 0 1rem; border-radius: 1rem; background: var(--hydria-surface-soft); padding: 1rem; }.activity-detail > div { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: .8rem; color: var(--hydria-muted); font-size: .75rem; }.activity-detail span { display: flex; align-items: center; gap: .4rem; }.activity-detail .hydria-primary-action { width: 100%; }.sync-pending { display: flex; min-height: 5.5rem; align-items: center; gap: .9rem; margin-top: 1.25rem; padding: 1rem; }
@media (max-width: 620px) { .planning-toolbar { align-items: stretch; }.date-navigation { justify-content: space-between; width: 100%; }.view-switch { width: 100%; }.view-switch button { flex: 1; }.activity-main { grid-template-columns: auto minmax(0,1fr) auto; }.activity-main time { grid-column: 1; grid-row: 1; }.activity-main > span:nth-of-type(1) { grid-column: 2; }.activity-status { grid-column: 2; grid-row: 2; justify-self: start; }.activity-main .chevron { grid-column: 3; grid-row: 1 / span 2; }.timeline::before { left: 1.65rem; }.timeline-marker { left: .35rem; width: 2.6rem; height: 2.6rem; }.timeline-item { padding-left: 2.7rem; } }
</style>
