<template>
  <div class="container mx-auto px-4 py-6">
    <!-- En-tête avec titre et actions -->
    <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold text-base-content mb-2">
          <span :key="langKey">{{ getTranslation('dashboard.map') }}</span>
        </h1>
        <div class="breadcrumbs text-sm">
          <ul>
            <li><NuxtLink to="/dashboard"><span :key="langKey">{{ getTranslation('nav.dashboard') }}</span></NuxtLink></li>
            <li><span :key="langKey">{{ getTranslation('dashboard.map') }}</span></li>
          </ul>
        </div>
      </div>

      <div class="flex gap-2 mt-4 lg:mt-0">
        <button @click="centerMap" class="btn btn-primary btn-sm">
          <i class="fas fa-crosshairs mr-2"></i>
          <span :key="langKey">{{ currentLang === 'fr' ? 'Centrer' : 'Afovoany' }}</span>
        </button>
        <button @click="toggleFullscreen" class="btn btn-outline btn-sm">
          <i class="fas fa-expand mr-2"></i>
          <span :key="langKey">{{ currentLang === 'fr' ? 'Plein écran' : 'Efijery feno' }}</span>
        </button>
      </div>
    </div>

    <!-- Panneau de contrôles -->
    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-6">
      <!-- Filtres de la carte -->
      <div class="lg:col-span-1">
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-filter mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Filtres' : 'Sivana' }}</span>
          </h3>

          <!-- Couches de la carte -->
          <div class="space-y-3">
            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text">
                  <i class="fas fa-tint mr-2 text-blue-500"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Points d\'eau' : 'Toerana rano' }}</span>
                </span>
                <input v-model="layers.pointsEau" type="checkbox" class="checkbox checkbox-primary" />
              </label>
            </div>

            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text">
                  <i class="fas fa-building mr-2 text-green-500"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Infrastructures' : 'Fotodrafitrasa' }}</span>
                </span>
                <input v-model="layers.infrastructures" type="checkbox" class="checkbox checkbox-success" />
              </label>
            </div>

            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text">
                  <i class="fas fa-route mr-2 text-orange-500"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Itinéraires' : 'Lalana' }}</span>
                </span>
                <input v-model="layers.itineraires" type="checkbox" class="checkbox checkbox-warning" />
              </label>
            </div>

            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text">
                  <i class="fas fa-users mr-2 text-purple-500"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Population' : 'Mponina' }}</span>
                </span>
                <input v-model="layers.population" type="checkbox" class="checkbox checkbox-secondary" />
              </label>
            </div>
          </div>

          <div class="divider"></div>

          <!-- Filtres par statut -->
          <div class="space-y-3">
            <h4 class="font-medium text-sm">
              <span :key="langKey">{{ currentLang === 'fr' ? 'Statut des ouvrages' : 'Toe-javatra asa' }}</span>
            </h4>

            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text text-success">
                  <i class="fas fa-check-circle mr-2"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Bon état' : 'Tsara' }}</span>
                </span>
                <input v-model="statusFilters.bon" type="checkbox" class="checkbox checkbox-success checkbox-sm" />
              </label>
            </div>

            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text text-warning">
                  <i class="fas fa-exclamation-triangle mr-2"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Maintenance' : 'Fikojakojana' }}</span>
                </span>
                <input v-model="statusFilters.maintenance" type="checkbox" class="checkbox checkbox-warning checkbox-sm" />
              </label>
            </div>

            <div class="form-control">
              <label class="label cursor-pointer">
                <span class="label-text text-error">
                  <i class="fas fa-times-circle mr-2"></i>
                  <span :key="langKey">{{ currentLang === 'fr' ? 'Hors service' : 'Tsy miasa' }}</span>
                </span>
                <input v-model="statusFilters.horsService" type="checkbox" class="checkbox checkbox-error checkbox-sm" />
              </label>
            </div>
          </div>
        </div>

        <!-- Légende -->
        <div class="dashboard-card mt-4">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-map-signs mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Légende' : 'Fandikan-teny' }}</span>
          </h3>

          <div class="space-y-2 text-sm">
            <div class="flex items-center">
              <div class="w-4 h-4 bg-blue-500 rounded-full mr-2"></div>
              <span><span :key="langKey">{{ currentLang === 'fr' ? 'Forage' : 'Lavaka' }}</span></span>
            </div>
            <div class="flex items-center">
              <div class="w-4 h-4 bg-green-500 rounded-full mr-2"></div>
              <span><span :key="langKey">{{ currentLang === 'fr' ? 'Borne fontaine' : 'Fantani-drano' }}</span></span>
            </div>
            <div class="flex items-center">
              <div class="w-4 h-4 bg-yellow-500 rounded-full mr-2"></div>
              <span><span :key="langKey">{{ currentLang === 'fr' ? 'Réservoir' : 'Fitoeran-drano' }}</span></span>
            </div>
            <div class="flex items-center">
              <div class="w-4 h-4 bg-purple-500 rounded-full mr-2"></div>
              <span><span :key="langKey">{{ currentLang === 'fr' ? 'Station pompage' : 'Paompy' }}</span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- Zone de la carte -->
      <div class="lg:col-span-3">
        <div class="dashboard-card p-0 overflow-hidden">
          <!-- Barre d'outils de la carte -->
          <div class="flex justify-between items-center p-4 bg-base-200 border-b">
            <div class="flex items-center gap-2">
              <button @click="zoomIn" class="btn btn-ghost btn-sm">
                <i class="fas fa-plus"></i>
              </button>
              <button @click="zoomOut" class="btn btn-ghost btn-sm">
                <i class="fas fa-minus"></i>
              </button>
              <div class="badge badge-outline">Zoom: {{ currentZoom }}x</div>
            </div>

            <div class="flex items-center gap-2">
              <select v-model="selectedRegion" @change="centerOnRegion" class="select select-bordered select-sm">
                <option value="" :key="langKey + '-region-all'">{{ currentLang === 'fr' ? 'Toutes les régions' : 'Faritra rehetra' }}</option>
                <option value="analamanga">Analamanga</option>
                <option value="vakinankaratra">Vakinankaratra</option>
                <option value="matsiatra-ambony">Matsiatra Ambony</option>
              </select>
            </div>
          </div>

          <!-- Container de la carte -->
          <div class="relative">
            <div id="map-container" class="w-full" :style="{ height: mapHeight + 'px' }">
              <!-- Simulation de carte avec des points -->
              <div class="absolute inset-0 bg-gradient-to-br from-blue-100 to-green-100 dark:from-blue-900 dark:to-green-900">
                <!-- Grille de fond pour simuler une carte -->
                <div class="absolute inset-0 opacity-20">
                  <svg width="100%" height="100%">
                    <defs>
                      <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
                        <path d="M 50 0 L 0 0 0 50" fill="none" stroke="currentColor" stroke-width="1"/>
                      </pattern>
                    </defs>
                    <rect width="100%" height="100%" fill="url(#grid)" />
                  </svg>
                </div>

                <!-- Points d'eau simulés -->
                <div v-if="layers.pointsEau" v-for="point in visiblePoints" :key="point.id"
                     :style="{ left: point.x + '%', top: point.y + '%' }"
                     class="absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer"
                     @click="selectPoint(point)">
                  <div class="relative group">
                    <div :class="getPointClass(point)" class="w-4 h-4 rounded-full border-2 border-white shadow-lg transition-all duration-200 group-hover:scale-125">
                    </div>
                    <!-- Tooltip -->
                    <div class="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-base-100 text-xs rounded shadow-lg border opacity-0 group-hover:opacity-100 transition-opacity duration-200 whitespace-nowrap z-10">
                      {{ point.nom }}
                      <div class="text-xs text-base-content/60">{{ getStatusText(point.status) }}</div>
                    </div>
                  </div>
                </div>

                <!-- Zones de population (si activée) -->
                <div v-if="layers.population" class="absolute inset-0 opacity-30">
                  <div v-for="zone in populationZones" :key="zone.id"
                       :style="{ left: zone.x + '%', top: zone.y + '%', width: zone.size + 'px', height: zone.size + 'px' }"
                       class="absolute transform -translate-x-1/2 -translate-y-1/2 bg-purple-300 rounded-full">
                  </div>
                </div>
              </div>

              <!-- Indicateur de chargement -->
              <div v-if="mapLoading" class="absolute inset-0 flex items-center justify-center bg-base-100/80">
                <span class="loading loading-spinner loading-lg text-primary"></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Informations sur le point sélectionné -->
    <div v-if="selectedPoint" class="dashboard-card">
      <div class="flex justify-between items-start mb-4">
        <h3 class="text-lg font-semibold">
          <i :class="getPointIcon(selectedPoint.type)" class="mr-2 text-primary"></i>
          {{ selectedPoint.nom }}
        </h3>
        <button @click="selectedPoint = null" class="btn btn-ghost btn-sm">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div>
          <h4 class="font-medium mb-2"><span :key="langKey">{{ currentLang === 'fr' ? 'Informations générales' : 'Fampahalalana ankapobeny' }}</span></h4>
          <div class="space-y-2 text-sm">
            <div><strong><span :key="langKey">{{ currentLang === 'fr' ? 'Type:' : 'Karazana:' }}</span></strong> {{ getTypeName(selectedPoint.type) }}</div>
            <div><strong><span :key="langKey">{{ currentLang === 'fr' ? 'Localisation:' : 'Toerana:' }}</span></strong> {{ selectedPoint.location }}</div>
            <div><strong><span :key="langKey">{{ currentLang === 'fr' ? 'État:' : 'Toe-javatra:' }}</span></strong>
              <span :class="getStatusTextClass(selectedPoint.status)">{{ getStatusText(selectedPoint.status) }}</span>
            </div>
          </div>
        </div>

        <div>
          <h4 class="font-medium mb-2"><span :key="langKey">{{ currentLang === 'fr' ? 'Données techniques' : 'Angon-drakitra teknika' }}</span></h4>
          <div class="space-y-2 text-sm">
            <div><strong><span :key="langKey">{{ currentLang === 'fr' ? 'Débit:' : 'Fikorianan-drano:' }}</span></strong> {{ selectedPoint.debit }} L/min</div>
            <div><strong><span :key="langKey">{{ currentLang === 'fr' ? 'Profondeur:' : 'Halaliny:' }}</span></strong> {{ selectedPoint.profondeur }} m</div>
            <div><strong><span :key="langKey">{{ currentLang === 'fr' ? 'Installation:' : 'Fanorenana:' }}</span></strong> {{ formatDate(selectedPoint.installation) }}</div>
          </div>
        </div>

        <div>
          <h4 class="font-medium mb-2"><span :key="langKey">{{ currentLang === 'fr' ? 'Actions rapides' : 'Hetsika haingana' }}</span></h4>
          <div class="space-y-2">
            <button class="btn btn-primary btn-sm w-full">
              <i class="fas fa-wrench mr-2"></i>
              <span :key="langKey">{{ currentLang === 'fr' ? 'Programmer maintenance' : 'Manomana fikojakojana' }}</span>
            </button>
            <button class="btn btn-success btn-sm w-full">
              <i class="fas fa-chart-bar mr-2"></i>
              <span :key="langKey">{{ currentLang === 'fr' ? 'Voir statistiques' : 'Hijery statistika' }}</span>
            </button>
            <button class="btn btn-info btn-sm w-full">
              <i class="fas fa-route mr-2"></i>
              <span :key="langKey">{{ currentLang === 'fr' ? 'Planifier visite' : 'Manomana fitsidihana' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Statistiques de la carte -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
      <div class="stat-card">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-primary-content/75 text-sm font-medium">
              <span :key="langKey">{{ currentLang === 'fr' ? 'Points visibles' : 'Toerana hita' }}</span>
            </div>
            <div class="text-2xl font-bold">{{ visiblePoints.length }}</div>
          </div>
          <div class="text-3xl opacity-75">
            <i class="fas fa-eye"></i>
          </div>
        </div>
      </div>

      <div class="stat-card success">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-success-content/75 text-sm font-medium">
              <span :key="langKey">{{ currentLang === 'fr' ? 'En bon état' : 'Toe-javatra tsara' }}</span>
            </div>
            <div class="text-2xl font-bold">{{ getPointsByStatus('bon').length }}</div>
          </div>
          <div class="text-3xl opacity-75">
            <i class="fas fa-check-circle"></i>
          </div>
        </div>
      </div>

      <div class="stat-card warning">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-warning-content/75 text-sm font-medium">
              <span :key="langKey">{{ currentLang === 'fr' ? 'Maintenance' : 'Fikojakojana' }}</span>
            </div>
            <div class="text-2xl font-bold">{{ getPointsByStatus('maintenance').length }}</div>
          </div>
          <div class="text-3xl opacity-75">
            <i class="fas fa-wrench"></i>
          </div>
        </div>
      </div>

      <div class="stat-card error">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-error-content/75 text-sm font-medium">
              <span :key="langKey">{{ currentLang === 'fr' ? 'Hors service' : 'Tsy miasa' }}</span>
            </div>
            <div class="text-2xl font-bold">{{ getPointsByStatus('hs').length }}</div>
          </div>
          <div class="text-3xl opacity-75">
            <i class="fas fa-times-circle"></i>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Composables
const { currentLang, langKey, getTranslation } = useLanguage()
const { mockApiCall } = useMockData()

// État réactif
const mapLoading = ref(false)
const mapHeight = ref(500)
const currentZoom = ref(1)
const selectedRegion = ref('')
const selectedPoint = ref(null)

// Couches et filtres
const layers = ref({
  pointsEau: true,
  infrastructures: true,
  itineraires: false,
  population: false
})

const statusFilters = ref({
  bon: true,
  maintenance: true,
  horsService: true
})

// Données simulées
const points = ref([
  { id: 1, nom: 'Forage Antananarivo Nord', type: 'forage', status: 'bon', x: 25, y: 30, location: 'Antananarivo I', debit: 120, profondeur: 45, installation: '2020-03-15' },
  { id: 2, nom: 'Borne Centre Ville', type: 'borne', status: 'bon', x: 30, y: 35, location: 'Antananarivo II', debit: 80, profondeur: 0, installation: '2019-07-22' },
  { id: 3, nom: 'Réservoir Antsirabe', type: 'reservoir', status: 'maintenance', x: 45, y: 55, location: 'Antsirabe I', debit: 200, profondeur: 8, installation: '2018-11-10' },
  { id: 4, nom: 'Station Pompage Sud', type: 'pompe', status: 'hs', x: 60, y: 75, location: 'Fianarantsoa I', debit: 0, profondeur: 30, installation: '2017-05-08' },
  { id: 5, nom: 'Forage Ambatolampy', type: 'forage', status: 'maintenance', x: 40, y: 50, location: 'Ambatolampy', debit: 90, profondeur: 38, installation: '2021-01-12' }
])

const populationZones = ref([
  { id: 1, x: 28, y: 33, size: 60 },
  { id: 2, x: 47, y: 57, size: 40 },
  { id: 3, x: 62, y: 77, size: 30 }
])

// Calculs
const visiblePoints = computed(() => {
  return points.value.filter(point => {
    // Filtrer par couche
    if (!layers.value.pointsEau) return false

    // Filtrer par statut
    if (point.status === 'bon' && !statusFilters.value.bon) return false
    if ((point.status === 'maintenance' || point.status === 'moyen') && !statusFilters.value.maintenance) return false
    if (point.status === 'hs' && !statusFilters.value.horsService) return false

    return true
  })
})

// Fonctions
const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleDateString('fr-FR')
}

const getPointClass = (point) => {
  const baseClass = 'w-4 h-4 rounded-full border-2 border-white shadow-lg transition-all duration-200 group-hover:scale-125'
  const statusClasses = {
    bon: 'bg-green-500',
    maintenance: 'bg-yellow-500',
    moyen: 'bg-yellow-500',
    hs: 'bg-red-500'
  }
  const typeClasses = {
    forage: 'rounded-full',
    borne: 'rounded-sm',
    reservoir: 'rounded-lg',
    pompe: 'rounded-none'
  }

  return `${baseClass} ${statusClasses[point.status] || 'bg-gray-500'}`
}

const getPointIcon = (type) => {
  const icons = {
    forage: 'fas fa-tint',
    borne: 'fas fa-faucet',
    reservoir: 'fas fa-database',
    pompe: 'fas fa-cogs'
  }
  return icons[type] || 'fas fa-map-marker'
}

const getTypeName = (type) => {
  const names = {
    fr: {
      forage: 'Forage',
      borne: 'Borne fontaine',
      reservoir: 'Réservoir',
      pompe: 'Station pompage'
    },
    mg: {
      forage: 'Lavaka',
      borne: 'Fantani-drano',
      reservoir: 'Fitoeran-drano',
      pompe: 'Paompy'
    }
  }
  return names[currentLang.value]?.[type] || type
}

const getStatusText = (status) => {
  const texts = {
    fr: {
      bon: 'Bon état',
      maintenance: 'Maintenance requise',
      moyen: 'État moyen',
      hs: 'Hors service'
    },
    mg: {
      bon: 'Tsara',
      maintenance: 'Mila fikojakojana',
      moyen: 'Antonony',
      hs: 'Tsy miasa'
    }
  }
  return texts[currentLang.value]?.[status] || status
}

const getStatusTextClass = (status) => {
  const classes = {
    bon: 'text-success',
    maintenance: 'text-warning',
    moyen: 'text-warning',
    hs: 'text-error'
  }
  return classes[status] || 'text-base-content'
}

const getPointsByStatus = (status) => {
  if (status === 'maintenance') {
    return points.value.filter(p => p.status === 'maintenance' || p.status === 'moyen')
  }
  return points.value.filter(p => p.status === status)
}

const selectPoint = (point) => {
  selectedPoint.value = point
}

const centerMap = () => {
  // Simulation du centrage de la carte
}

const centerOnRegion = () => {
  mapLoading.value = true
  setTimeout(() => {
    mapLoading.value = false
  }, 1000)
}

const zoomIn = () => {
  if (currentZoom.value < 5) {
    currentZoom.value += 0.5
  }
}

const zoomOut = () => {
  if (currentZoom.value > 0.5) {
    currentZoom.value -= 0.5
  }
}

const toggleFullscreen = () => {
  if (mapHeight.value === 500) {
    mapHeight.value = 700
  } else {
    mapHeight.value = 500
  }
}

// Cycle de vie
onMounted(async () => {
  try {
    mapLoading.value = true
    await mockApiCall(1500)
  } catch (error) {
    console.error('Erreur lors du chargement de la carte:', error)
  } finally {
    mapLoading.value = false
  }
})

// Meta tags
useHead({
  title: 'Carte Interactive - Hydria'
})
</script>

<style scoped>
.dashboard-card {
  @apply bg-base-100 rounded-lg shadow-md p-6 border border-base-300;
}

.stat-card {
  @apply bg-primary text-primary-content rounded-lg p-4 shadow-lg;
}

.stat-card.warning {
  @apply bg-warning text-warning-content;
}

.stat-card.error {
  @apply bg-error text-error-content;
}

.stat-card.success {
  @apply bg-success text-success-content;
}

#map-container {
  min-height: 400px;
  position: relative;
  overflow: hidden;
}
</style>