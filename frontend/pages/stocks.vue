<template>
  <div class="hydria-page mx-auto max-w-6xl">
    <header class="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><p class="hydria-kicker">Hydria Terrain</p><h1 class="mt-2 text-3xl font-bold tracking-[-0.04em] sm:text-4xl">{{ t('nav.inventory') }}</h1><p class="hydria-muted mt-2">{{ copy.subtitle }}</p></div><span class="stock-summary"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i><strong>1</strong>{{ copy.alert }}</span></header>
    <div v-if="loading" class="space-y-3" aria-busy="true"><div v-for="item in 3" :key="item" class="h-24 animate-pulse rounded-2xl" style="background:var(--hydria-surface-soft)"></div></div>
    <section v-else class="hydria-panel-flat px-4" aria-labelledby="inventory-title"><h2 id="inventory-title" class="sr-only">{{ copy.inventory }}</h2><article v-for="item in inventory" :key="item.id" class="hydria-row stock-row"><span class="hydria-icon" :class="stockTone(item)"><i :class="stockIcon(item)" aria-hidden="true"></i></span><div class="min-w-0 flex-1"><h3 class="truncate font-bold">{{ item.item }}</h3><p class="hydria-muted mt-1 text-sm">{{ item.category }} · {{ formatCurrency(item.unit_price) }}</p><div class="stock-progress"><span :class="stockTone(item)" :style="{ width: `${Math.min(100, item.current_stock / Math.max(item.min_stock * 2, 1) * 100)}%` }"></span></div></div><div class="text-right"><strong class="hydria-tabular block text-2xl">{{ item.current_stock }}</strong><small class="hydria-muted">{{ copy.units }}</small><span v-if="item.current_stock <= item.min_stock * 1.6" class="low-label">{{ copy.low }}</span></div></article></section>
  </div>
</template>
<script setup>
const { currentLang, getTranslation: t } = useLanguage()
const { fetchInventory } = useMockData()
const loading = ref(true)
const inventory = ref([])
const copy = computed(() => currentLang.value === 'fr' ? { subtitle: 'Disponibilité du matériel utile aux équipes terrain.', alert: 'stock à surveiller', inventory: 'Inventaire', units: 'unités', low: 'Faible' } : { subtitle: 'Fahafahan’ny fitaovana ampiasain’ny ekipa eny an-toerana.', alert: 'tahiry arahi-maso', inventory: 'Tahiry', units: 'isa', low: 'Vitsy' })
const formatCurrency = value => new Intl.NumberFormat('mg-MG', { style: 'currency', currency: 'MGA', maximumFractionDigits: 0 }).format(value)
const stockTone = item => item.current_stock <= item.min_stock * 1.6 ? 'is-warning' : ''
const stockIcon = item => item.category === 'Équipement' ? 'fas fa-gears' : item.category === 'Comptage' ? 'fas fa-gauge-high' : 'fas fa-wrench'
onMounted(async () => { try { inventory.value = await fetchInventory() } finally { loading.value = false } })
useHead({ title: () => `${t('nav.inventory')} · Hydria Terrain` })
</script>
<style scoped>
.stock-summary { display: inline-flex; min-height: 2.8rem; width: fit-content; align-items: center; gap: .45rem; border-radius: .85rem; background: color-mix(in srgb,var(--hydria-amber) 12%,transparent); padding: 0 .8rem; color: var(--hydria-amber); font-size: .75rem; }.stock-row { padding: .75rem 0; }.hydria-icon.is-warning { background: color-mix(in srgb,var(--hydria-amber) 12%,transparent); color: var(--hydria-amber); }.stock-progress { width: 100%; max-width: 18rem; height: .35rem; margin-top: .65rem; overflow: hidden; border-radius: 999px; background: var(--hydria-surface-strong); }.stock-progress span { display: block; height: 100%; border-radius: inherit; background: var(--hydria-cyan); }.stock-progress span.is-warning { background: var(--hydria-amber); }.low-label { display: block; margin-top: .35rem; color: var(--hydria-amber); font-size: .65rem; font-weight: 700; }
</style>
