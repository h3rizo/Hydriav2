<template>
  <div class="container mx-auto px-4 py-6">
    <!-- En-tête avec titre et actions -->
    <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold text-base-content mb-2">
          <span :key="langKey">{{ getTranslation('dashboard.infrastructure') }}</span>
        </h1>
        <div class="breadcrumbs text-sm">
          <ul>
            <li><NuxtLink to="/dashboard"><span :key="langKey">{{ getTranslation('nav.dashboard') }}</span></NuxtLink></li>
            <li><span :key="langKey">{{ getTranslation('dashboard.infrastructure') }}</span></li>
          </ul>
        </div>
      </div>

      <div class="flex gap-2 mt-4 lg:mt-0">
        <button @click="refreshData" class="btn btn-primary btn-sm" :disabled="loading">
          <i class="fas fa-sync-alt mr-2" :class="{ 'animate-spin': loading }"></i>
          <span :key="langKey">{{ currentLang === 'fr' ? 'Actualiser' : 'Havaozina' }}</span>
        </button>
        <button @click="exportData" class="btn btn-outline btn-sm">
          <i class="fas fa-download mr-2"></i>
          <span :key="langKey">{{ currentLang === 'fr' ? 'Exporter' : 'Avoaka' }}</span>
        </button>
      </div>
    </div>

    <!-- Panneau de filtres -->
    <div class="filter-panel bg-base-200 rounded-lg p-4 mb-6">
      <div class="flex flex-wrap gap-4 items-end">
        <div class="form-control">
          <label class="label">
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'Type d\'ouvrage' : 'Karazana asa' }}</span></span>
          </label>
          <select v-model="filters.type" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="" :key="langKey + '-type-all'">{{ currentLang === 'fr' ? 'Tous les types' : 'Karazana rehetra' }}</option>
            <option value="forage" :key="langKey + '-type-forage'">{{ currentLang === 'fr' ? 'Forage' : 'Lavaka' }}</option>
            <option value="borne" :key="langKey + '-type-borne'">{{ currentLang === 'fr' ? 'Borne fontaine' : 'Fantani-drano' }}</option>
            <option value="reservoir" :key="langKey + '-type-reservoir'">{{ currentLang === 'fr' ? 'Réservoir' : 'Fitoeran-drano' }}</option>
            <option value="pompe" :key="langKey + '-type-pompe'">{{ currentLang === 'fr' ? 'Station de pompage' : 'Paompy' }}</option>
          </select>
        </div>

        <div class="form-control">
          <label class="label">
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'État' : 'Toe-javatra' }}</span></span>
          </label>
          <select v-model="filters.etat" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="" :key="langKey + '-state-all'">{{ currentLang === 'fr' ? 'Tous les états' : 'Toe-javatra rehetra' }}</option>
            <option value="bon" :key="langKey + '-state-good'">{{ currentLang === 'fr' ? 'Bon' : 'Tsara' }}</option>
            <option value="moyen" :key="langKey + '-state-average'">{{ currentLang === 'fr' ? 'Moyen' : 'Antonony' }}</option>
            <option value="mauvais" :key="langKey + '-state-bad'">{{ currentLang === 'fr' ? 'Mauvais' : 'Ratsy' }}</option>
            <option value="hs" :key="langKey + '-state-outofservice'">{{ currentLang === 'fr' ? 'Hors service' : 'Tsy miasa' }}</option>
          </select>
        </div>

        <div class="form-control">
          <label class="label">
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'Région' : 'Faritra' }}</span></span>
          </label>
          <select v-model="filters.region" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="" :key="langKey + '-region-all'">{{ currentLang === 'fr' ? 'Toutes les régions' : 'Faritra rehetra' }}</option>
            <option value="analamanga">Analamanga</option>
            <option value="vakinankaratra">Vakinankaratra</option>
            <option value="matsiatra-ambony">Matsiatra Ambony</option>
          </select>
        </div>

        <button @click="resetFilters" class="btn btn-ghost btn-sm">
          <i class="fas fa-times mr-2"></i>
          <span :key="langKey">{{ currentLang === 'fr' ? 'Réinitialiser' : 'Averina' }}</span>
        </button>
      </div>
    </div>

    <!-- Indicateur de chargement -->
    <div v-if="loading" class="flex justify-center py-8">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <!-- Contenu principal -->
    <div v-else>
      <!-- Statistiques principales -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <!-- Total ouvrages -->
        <div class="stat-card">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-primary-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Total Ouvrages' : 'Asa tanteraka' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.total_ouvrages }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-tools"></i>
            </div>
          </div>
        </div>

        <!-- Ouvrages en bon état -->
        <div class="stat-card success">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-success-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'En Bon État' : 'Toe-javatra tsara' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.bon_etat }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-check-circle"></i>
            </div>
          </div>
        </div>

        <!-- Ouvrages nécessitant maintenance -->
        <div class="stat-card warning">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-warning-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Maintenance' : 'Fikojakojana' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.maintenance }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-wrench"></i>
            </div>
          </div>
        </div>

        <!-- Ouvrages hors service -->
        <div class="stat-card error">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-error-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Hors Service' : 'Tsy miasa' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.hors_service }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-times-circle"></i>
            </div>
          </div>
        </div>
      </div>

      <!-- Graphiques -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <!-- Répartition par état -->
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-chart-pie mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Répartition par État' : 'Fizarana araka ny toe-javatra' }}</span>
          </h3>
          <div class="chart-container">
            <canvas ref="etatChart"></canvas>
          </div>
        </div>

        <!-- Répartition par type -->
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-chart-bar mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Répartition par Type' : 'Fizarana araka ny karazana' }}</span>
          </h3>
          <div class="chart-container">
            <canvas ref="typeChart"></canvas>
          </div>
        </div>
      </div>

      <!-- Alertes et priorités -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <!-- Interventions urgentes -->
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4 text-error">
            <i class="fas fa-exclamation-triangle mr-2"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Interventions Urgentes' : 'Fitsaboana maika' }}</span>
          </h3>
          <div class="space-y-3">
            <div v-for="urgent in interventionsUrgentes" :key="urgent.id"
                 class="alert alert-error">
              <i class="fas fa-exclamation-triangle"></i>
              <div class="flex-1">
                <div class="font-medium">{{ urgent.nom }}</div>
                <div class="text-sm opacity-75">{{ urgent.probleme }}</div>
              </div>
              <button class="btn btn-error btn-sm">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Intervenir' : 'Fitsaboana' }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Maintenance préventive -->
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4 text-warning">
            <i class="fas fa-calendar-check mr-2"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Maintenance Préventive' : 'Fikojakojana mialoha' }}</span>
          </h3>
          <div class="space-y-3">
            <div v-for="maintenance in maintenancePreventive" :key="maintenance.id"
                 class="alert alert-warning">
              <i class="fas fa-calendar-check"></i>
              <div class="flex-1">
                <div class="font-medium">{{ maintenance.nom }}</div>
                <div class="text-sm opacity-75">{{ maintenance.prochaine_visite }}</div>
              </div>
              <button class="btn btn-warning btn-sm">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Planifier' : 'Manomana' }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Tableau des ouvrages -->
      <div class="dashboard-card">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-semibold">
            <i class="fas fa-list mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Liste des Ouvrages' : 'Lisitr\'ireo asa' }}</span>
          </h3>
          <div class="badge badge-outline">{{ filteredOuvrages.length }} <span :key="langKey">{{ currentLang === 'fr' ? 'ouvrages' : 'asa' }}</span></div>
        </div>

        <div class="overflow-x-auto">
          <table class="table table-zebra w-full">
            <thead>
              <tr class="bg-base-200">
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Nom' : 'Anarana' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Type' : 'Karazana' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Localisation' : 'Toerana' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'État' : 'Toe-javatra' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Dernière Visite' : 'Fitsidihanana farany' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Actions' : 'Asa' }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ouvrage in filteredOuvrages" :key="ouvrage.id">
                <td>
                  <div class="flex items-center">
                    <i :class="getOuvrageIcon(ouvrage.type)" class="mr-2 text-primary"></i>
                    <div class="font-medium">{{ ouvrage.nom }}</div>
                  </div>
                </td>
                <td>
                  <span class="badge badge-outline">{{ getTypeName(ouvrage.type) }}</span>
                </td>
                <td>{{ ouvrage.localisation }}</td>
                <td>
                  <span :class="getEtatClass(ouvrage.etat)">
                    {{ getEtatName(ouvrage.etat) }}
                  </span>
                </td>
                <td>
                  <div class="text-sm">{{ formatDate(ouvrage.derniere_visite) }}</div>
                </td>
                <td>
                  <div class="dropdown dropdown-end">
                    <div tabindex="0" role="button" class="btn btn-ghost btn-xs">
                      <i class="fas fa-ellipsis-v"></i>
                    </div>
                    <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-48 p-2 shadow">
                      <li><a @click="viewDetails(ouvrage)"><i class="fas fa-eye mr-2"></i><span :key="langKey">{{ currentLang === 'fr' ? 'Voir détails' : 'Hijery antsipiriany' }}</span></a></li>
                      <li><a @click="planMaintenance(ouvrage)"><i class="fas fa-wrench mr-2"></i><span :key="langKey">{{ currentLang === 'fr' ? 'Maintenance' : 'Fikojakojana' }}</span></a></li>
                      <li><a @click="viewHistory(ouvrage)"><i class="fas fa-history mr-2"></i><span :key="langKey">{{ currentLang === 'fr' ? 'Historique' : 'Tantara' }}</span></a></li>
                    </ul>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Message si aucun résultat -->
          <div v-if="filteredOuvrages.length === 0" class="text-center text-base-content/60 py-8">
            <i class="fas fa-tools text-4xl mb-2"></i>
            <div><span :key="langKey">{{ currentLang === 'fr' ? 'Aucun ouvrage trouvé' : 'Tsy misy asa hita' }}</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Chart } from 'chart.js/auto'

// Composables
const { currentLang, langKey, getTranslation } = useLanguage()
const { mockApiCall } = useMockData()

// État réactif
const loading = ref(true)
const stats = ref({
  total_ouvrages: 0,
  bon_etat: 0,
  maintenance: 0,
  hors_service: 0
})

const filters = ref({
  type: '',
  etat: '',
  region: ''
})

const ouvrages = ref([
  { id: 1, nom: 'Forage Antananarivo Nord', type: 'forage', localisation: 'Antananarivo I', etat: 'bon', derniere_visite: '2024-09-10', region: 'analamanga' },
  { id: 2, nom: 'Borne Fontaine Centre', type: 'borne', localisation: 'Antananarivo II', etat: 'moyen', derniere_visite: '2024-09-05', region: 'analamanga' },
  { id: 3, nom: 'Réservoir Antsirabe', type: 'reservoir', localisation: 'Antsirabe I', etat: 'bon', derniere_visite: '2024-09-08', region: 'vakinankaratra' },
  { id: 4, nom: 'Station Pompage Sud', type: 'pompe', localisation: 'Fianarantsoa I', etat: 'hs', derniere_visite: '2024-08-28', region: 'matsiatra-ambony' },
  { id: 5, nom: 'Forage Ambatolampy', type: 'forage', localisation: 'Ambatolampy', etat: 'mauvais', derniere_visite: '2024-09-02', region: 'vakinankaratra' }
])

const interventionsUrgentes = ref([
  { id: 1, nom: 'Station Pompage Sud', probleme: 'Panne électrique majeure' },
  { id: 2, nom: 'Forage Ambatolampy', probleme: 'Niveau d\'eau critique' }
])

const maintenancePreventive = ref([
  { id: 1, nom: 'Borne Fontaine Centre', prochaine_visite: 'Prévue dans 5 jours' },
  { id: 2, nom: 'Réservoir Antsirabe', prochaine_visite: 'Prévue dans 10 jours' }
])

// Calculs
const filteredOuvrages = computed(() => {
  return ouvrages.value.filter(ouvrage => {
    if (filters.value.type && ouvrage.type !== filters.value.type) return false
    if (filters.value.etat && ouvrage.etat !== filters.value.etat) return false
    if (filters.value.region && ouvrage.region !== filters.value.region) return false
    return true
  })
})

// Références des graphiques
const etatChart = ref(null)
const typeChart = ref(null)
let etatChartInstance = null
let typeChartInstance = null

// Fonctions
const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleDateString('fr-FR')
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

const getEtatName = (etat) => {
  const names = {
    fr: {
      bon: 'Bon',
      moyen: 'Moyen',
      mauvais: 'Mauvais',
      hs: 'Hors service'
    },
    mg: {
      bon: 'Tsara',
      moyen: 'Antonony',
      mauvais: 'Ratsy',
      hs: 'Tsy miasa'
    }
  }
  return names[currentLang.value]?.[etat] || etat
}

const getEtatClass = (etat) => {
  const classes = {
    bon: 'badge badge-success badge-sm',
    moyen: 'badge badge-warning badge-sm',
    mauvais: 'badge badge-error badge-sm',
    hs: 'badge badge-ghost badge-sm'
  }
  return classes[etat] || 'badge badge-sm'
}

const getOuvrageIcon = (type) => {
  const icons = {
    forage: 'fas fa-tint',
    borne: 'fas fa-faucet',
    reservoir: 'fas fa-database',
    pompe: 'fas fa-cogs'
  }
  return icons[type] || 'fas fa-tools'
}

const refreshData = async () => {
  loading.value = true
  try {
    await mockApiCall(1000)
    calculateStats()
    updateCharts()
  } catch (error) {
    console.error('Erreur lors du rafraîchissement:', error)
  } finally {
    loading.value = false
  }
}

const calculateStats = () => {
  const total = ouvrages.value.length
  const bonEtat = ouvrages.value.filter(o => o.etat === 'bon').length
  const maintenance = ouvrages.value.filter(o => o.etat === 'moyen' || o.etat === 'mauvais').length
  const horsService = ouvrages.value.filter(o => o.etat === 'hs').length

  stats.value = {
    total_ouvrages: total,
    bon_etat: bonEtat,
    maintenance: maintenance,
    hors_service: horsService
  }
}

const applyFilters = () => {
  // Les filtres sont appliqués automatiquement via computed
}

const resetFilters = () => {
  filters.value.type = ''
  filters.value.etat = ''
  filters.value.region = ''
}

const exportData = () => {
  alert(currentLang.value === 'fr' ? 'Fonctionnalité d\'export à implémenter' : 'Fiasa avoaka mbola tsy vita')
}

const viewDetails = (ouvrage) => {
  alert(`${currentLang.value === 'fr' ? 'Voir détails pour' : 'Hijery antsipiriany ho an\'ny'}: ${ouvrage.nom}`)
}

const planMaintenance = (ouvrage) => {
  alert(`${currentLang.value === 'fr' ? 'Planifier maintenance pour' : 'Manomana fikojakojana ho an\'ny'}: ${ouvrage.nom}`)
}

const viewHistory = (ouvrage) => {
  alert(`${currentLang.value === 'fr' ? 'Historique de' : 'Tantaran\'ny'}: ${ouvrage.nom}`)
}

const initCharts = () => {
  nextTick(() => {
    if (etatChart.value) {
      const bonCount = ouvrages.value.filter(o => o.etat === 'bon').length
      const moyenCount = ouvrages.value.filter(o => o.etat === 'moyen').length
      const mauvaisCount = ouvrages.value.filter(o => o.etat === 'mauvais').length
      const hsCount = ouvrages.value.filter(o => o.etat === 'hs').length

      etatChartInstance = new Chart(etatChart.value, {
        type: 'doughnut',
        data: {
          labels: [
            currentLang.value === 'fr' ? 'Bon' : 'Tsara',
            currentLang.value === 'fr' ? 'Moyen' : 'Antonony',
            currentLang.value === 'fr' ? 'Mauvais' : 'Ratsy',
            currentLang.value === 'fr' ? 'Hors service' : 'Tsy miasa'
          ],
          datasets: [{
            data: [bonCount, moyenCount, mauvaisCount, hsCount],
            backgroundColor: ['#10b981', '#f59e0b', '#ef4444', '#6b7280'],
            borderWidth: 2,
            borderColor: '#ffffff'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom'
            }
          }
        }
      })
    }

    if (typeChart.value) {
      const forageCount = ouvrages.value.filter(o => o.type === 'forage').length
      const borneCount = ouvrages.value.filter(o => o.type === 'borne').length
      const reservoirCount = ouvrages.value.filter(o => o.type === 'reservoir').length
      const pompeCount = ouvrages.value.filter(o => o.type === 'pompe').length

      typeChartInstance = new Chart(typeChart.value, {
        type: 'bar',
        data: {
          labels: [
            currentLang.value === 'fr' ? 'Forage' : 'Lavaka',
            currentLang.value === 'fr' ? 'Borne fontaine' : 'Fantani-drano',
            currentLang.value === 'fr' ? 'Réservoir' : 'Fitoeran-drano',
            currentLang.value === 'fr' ? 'Station pompage' : 'Paompy'
          ],
          datasets: [{
            label: currentLang.value === 'fr' ? 'Nombre' : 'Isa',
            data: [forageCount, borneCount, reservoirCount, pompeCount],
            backgroundColor: ['#06b6d4', '#10b981', '#f59e0b', '#8b5cf6'],
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom'
            }
          },
          scales: {
            y: {
              beginAtZero: true
            }
          }
        }
      })
    }
  })
}

const updateCharts = () => {
  if (etatChartInstance) {
    const bonCount = ouvrages.value.filter(o => o.etat === 'bon').length
    const moyenCount = ouvrages.value.filter(o => o.etat === 'moyen').length
    const mauvaisCount = ouvrages.value.filter(o => o.etat === 'mauvais').length
    const hsCount = ouvrages.value.filter(o => o.etat === 'hs').length

    etatChartInstance.data.labels = [
      currentLang.value === 'fr' ? 'Bon' : 'Tsara',
      currentLang.value === 'fr' ? 'Moyen' : 'Antonony',
      currentLang.value === 'fr' ? 'Mauvais' : 'Ratsy',
      currentLang.value === 'fr' ? 'Hors service' : 'Tsy miasa'
    ]
    etatChartInstance.data.datasets[0].data = [bonCount, moyenCount, mauvaisCount, hsCount]
    etatChartInstance.update()
  }

  if (typeChartInstance) {
    const forageCount = ouvrages.value.filter(o => o.type === 'forage').length
    const borneCount = ouvrages.value.filter(o => o.type === 'borne').length
    const reservoirCount = ouvrages.value.filter(o => o.type === 'reservoir').length
    const pompeCount = ouvrages.value.filter(o => o.type === 'pompe').length

    typeChartInstance.data.labels = [
      currentLang.value === 'fr' ? 'Forage' : 'Lavaka',
      currentLang.value === 'fr' ? 'Borne fontaine' : 'Fantani-drano',
      currentLang.value === 'fr' ? 'Réservoir' : 'Fitoeran-drano',
      currentLang.value === 'fr' ? 'Station pompage' : 'Paompy'
    ]
    typeChartInstance.data.datasets[0].label = currentLang.value === 'fr' ? 'Nombre' : 'Isa'
    typeChartInstance.data.datasets[0].data = [forageCount, borneCount, reservoirCount, pompeCount]
    typeChartInstance.update()
  }
}

// Cycle de vie
onMounted(async () => {
  try {
    await mockApiCall(800)
    calculateStats()
    initCharts()
  } catch (error) {
    console.error('Erreur lors du chargement:', error)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (etatChartInstance) {
    etatChartInstance.destroy()
  }
  if (typeChartInstance) {
    typeChartInstance.destroy()
  }
})

// Watcher pour la langue
watch(() => currentLang.value, () => {
  updateCharts()
})

// Meta tags
useHead({
  title: 'État des Ouvrages - Hydria'
})
</script>

<style scoped>
.dashboard-card {
  @apply bg-base-100 rounded-lg shadow-md p-6 border border-base-300;
}

.stat-card {
  @apply bg-gradient-to-br from-primary to-primary text-primary-content rounded-lg p-4 shadow-lg;
}

.stat-card.warning {
  @apply from-warning to-warning text-warning-content;
}

.stat-card.error {
  @apply from-error to-error text-error-content;
}

.stat-card.success {
  @apply from-success to-success text-success-content;
}

.chart-container {
  position: relative;
  height: 300px;
  max-height: 300px;
  width: 100%;
}

@media (max-width: 768px) {
  .chart-container {
    height: 250px;
    max-height: 250px;
  }
}

.filter-panel {
  @apply bg-base-200 rounded-lg p-4 mb-6;
}
</style>
