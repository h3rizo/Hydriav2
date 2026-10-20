<template>
  <div class="container mx-auto px-4 py-6">
    <!-- En-tête avec titre et actions -->
    <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold text-base-content mb-2">
          <span :key="langKey">{{ getTranslation('dashboard.payments_flat') }}</span>
        </h1>
        <div class="breadcrumbs text-sm">
          <ul>
            <li><NuxtLink to="/dashboard"><span :key="langKey">{{ getTranslation('nav.dashboard') }}</span></NuxtLink></li>
            <li><span :key="langKey">{{ getTranslation('dashboard.payments_flat') }}</span></li>
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
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'Commune' : 'Kaominina' }}</span></span>
          </label>
          <select v-model="filters.commune" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="" :key="langKey + '-comm-all'">{{ currentLang === 'fr' ? 'Toutes les communes' : 'Kaominina rehetra' }}</option>
            <option v-for="commune in communes" :key="commune.id" :value="commune.id">
              {{ commune.name }}
            </option>
          </select>
        </div>

        <div class="form-control">
          <label class="label">
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'Statut' : 'Sata' }}</span></span>
          </label>
          <select v-model="filters.status" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="" :key="langKey + '-status-all'">{{ currentLang === 'fr' ? 'Tous les statuts' : 'Sata rehetra' }}</option>
            <option value="paye" :key="langKey + '-status-paid'">{{ currentLang === 'fr' ? 'Payé' : 'Voaloa' }}</option>
            <option value="impaye" :key="langKey + '-status-unpaid'">{{ currentLang === 'fr' ? 'Impayé' : 'Tsy voaloa' }}</option>
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
        <!-- Total points forfait -->
        <div class="stat-card">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-primary-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Total Points Forfait' : 'Toerana raikitra tanteraka' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.total_points_forfait }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-water"></i>
            </div>
          </div>
        </div>

        <!-- Montant total forfait -->
        <div class="stat-card success">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-success-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Montant Total' : 'Vola tanteraka' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ formatCurrency(stats.montant_total_forfait) }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-coins"></i>
            </div>
          </div>
        </div>

        <!-- Non payés mois courant -->
        <div class="stat-card warning">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-warning-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Non payés ce mois' : 'Tsy voaloa amin\'ity volana ity' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.non_payes_courant }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-exclamation-triangle"></i>
            </div>
          </div>
        </div>

        <!-- Non payés mois passés -->
        <div class="stat-card error">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-error-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Non payés passés' : 'Tsy voaloa taloha' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.non_payes_passes }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-times-circle"></i>
            </div>
          </div>
        </div>
      </div>

      <!-- Graphiques -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-chart-pie mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Répartition par Statut' : 'Fizarana araka ny sata' }}</span>
          </h3>
          <div class="chart-container">
            <canvas ref="statusChart"></canvas>
          </div>
        </div>

        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-chart-bar mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Évolution Mensuelle' : 'Fivoaran\'ny volana' }}</span>
          </h3>
          <div class="chart-container">
            <canvas ref="trendChart"></canvas>
          </div>
        </div>
      </div>

      <!-- Tableau des points d'eau -->
      <div class="dashboard-card">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-semibold">
            <i class="fas fa-list mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Points d\'Eau Forfaitaires' : 'Toerana rano raikitra' }}</span>
          </h3>
          <div class="badge badge-outline">{{ filteredPoints.length }} <span :key="langKey">{{ currentLang === 'fr' ? 'résultats' : 'valiny' }}</span></div>
        </div>

        <div class="overflow-x-auto">
          <table class="table table-zebra w-full">
            <thead>
              <tr class="bg-base-200">
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Nom Abonné' : 'Anaran\'ny mpanjifa' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Commune' : 'Kaominina' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Tarif Forfaitaire' : 'Vidim-pomby raikitra' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Statut' : 'Sata' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Actions' : 'Asa' }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="point in filteredPoints" :key="point.id">
                <td>
                  <div class="font-medium">{{ point.nom }}</div>
                </td>
                <td>{{ point.commune }}</td>
                <td>
                  <div class="font-bold text-success">{{ formatCurrency(point.tarif) }}</div>
                </td>
                <td>
                  <span v-if="point.status === 'Payé'" class="badge badge-success badge-sm">
                    <span :key="langKey">{{ currentLang === 'fr' ? 'Payé' : 'Voaloa' }}</span>
                  </span>
                  <span v-else class="badge badge-error badge-sm">
                    <span :key="langKey">{{ currentLang === 'fr' ? 'Impayé' : 'Tsy voaloa' }}</span>
                  </span>
                </td>
                <td>
                  <div class="dropdown dropdown-end">
                    <div tabindex="0" role="button" class="btn btn-ghost btn-xs">
                      <i class="fas fa-ellipsis-v"></i>
                    </div>
                    <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box z-[1] w-48 p-2 shadow">
                      <li><a @click="viewDetails(point)"><i class="fas fa-eye mr-2"></i><span :key="langKey">{{ currentLang === 'fr' ? 'Voir détails' : 'Hijery antsipiriany' }}</span></a></li>
                      <li><a @click="editPoint(point)"><i class="fas fa-edit mr-2"></i><span :key="langKey">{{ currentLang === 'fr' ? 'Modifier' : 'Ovaina' }}</span></a></li>
                      <li v-if="point.status === 'Impayé'"><a @click="markPaid(point)"><i class="fas fa-check mr-2 text-success"></i><span :key="langKey">{{ currentLang === 'fr' ? 'Marquer payé' : 'Marika voaloa' }}</span></a></li>
                    </ul>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Message si aucun résultat -->
          <div v-if="filteredPoints.length === 0" class="text-center text-base-content/60 py-8">
            <i class="fas fa-inbox text-4xl mb-2"></i>
            <div><span :key="langKey">{{ currentLang === 'fr' ? 'Aucun point d\'eau forfaitaire trouvé' : 'Tsy misy toerana rano raikitra hita' }}</span></div>
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
  total_points_forfait: 0,
  montant_total_forfait: 0,
  non_payes_courant: 0,
  non_payes_passes: 0
})

const filters = ref({
  commune: '',
  status: ''
})

const communes = ref([
  { id: 1, name: 'Antananarivo I' },
  { id: 2, name: 'Antananarivo II' },
  { id: 3, name: 'Antsirabe I' },
  { id: 4, name: 'Fianarantsoa I' }
])

const pointsEau = ref([
  { id: 1, nom: 'Rakoto Jean', commune: 'Antananarivo I', tarif: 25000, status: 'Payé' },
  { id: 2, nom: 'Rasoa Marie', commune: 'Antananarivo II', tarif: 25000, status: 'Impayé' },
  { id: 3, nom: 'Randria Paul', commune: 'Antsirabe I', tarif: 20000, status: 'Payé' },
  { id: 4, nom: 'Rabe Hery', commune: 'Fianarantsoa I', tarif: 18000, status: 'Impayé' },
  { id: 5, nom: 'Rasoanaivo Nivo', commune: 'Antananarivo I', tarif: 25000, status: 'Impayé' }
])

// Calculs
const filteredPoints = computed(() => {
  return pointsEau.value.filter(point => {
    if (filters.value.commune && point.commune !== communes.value.find(c => c.id == filters.value.commune)?.name) {
      return false
    }
    if (filters.value.status && point.status !== (filters.value.status === 'paye' ? 'Payé' : 'Impayé')) {
      return false
    }
    return true
  })
})

// Références des graphiques
const statusChart = ref(null)
const trendChart = ref(null)
let statusChartInstance = null
let trendChartInstance = null

// Fonctions
const formatCurrency = (amount) => {
  return new Intl.NumberFormat('mg-MG', {
    style: 'currency',
    currency: 'MGA',
    minimumFractionDigits: 0
  }).format(amount)
}

const refreshData = async () => {
  loading.value = true
  try {
    await mockApiCall(1000)
    // Recalculer les stats
    calculateStats()
    updateCharts()
  } catch (error) {
    console.error('Erreur lors du rafraîchissement:', error)
  } finally {
    loading.value = false
  }
}

const calculateStats = () => {
  const total = pointsEau.value.length
  const payes = pointsEau.value.filter(p => p.status === 'Payé').length
  const impayes = total - payes
  const montantTotal = pointsEau.value.reduce((sum, p) => sum + p.tarif, 0)

  stats.value = {
    total_points_forfait: total,
    montant_total_forfait: montantTotal,
    non_payes_courant: Math.floor(impayes * 0.7),
    non_payes_passes: Math.floor(impayes * 0.3)
  }
}

const applyFilters = () => {
  // Les filtres sont appliqués automatiquement via computed
}

const resetFilters = () => {
  filters.value.commune = ''
  filters.value.status = ''
}

const exportData = () => {
  // TODO: Implémenter l'export
  alert(currentLang.value === 'fr' ? 'Fonctionnalité d\'export à implémenter' : 'Fiasa avoaka mbola tsy vita')
}

const viewDetails = (point) => {
  alert(`${currentLang.value === 'fr' ? 'Voir détails pour' : 'Hijery antsipiriany ho an\'ny'}: ${point.nom}`)
}

const editPoint = (point) => {
  alert(`${currentLang.value === 'fr' ? 'Modifier' : 'Ovaina'}: ${point.nom}`)
}

const markPaid = (point) => {
  point.status = 'Payé'
  calculateStats()
  updateCharts()
}

const initCharts = () => {
  nextTick(() => {
    if (statusChart.value) {
      const payes = pointsEau.value.filter(p => p.status === 'Payé').length
      const impayes = pointsEau.value.length - payes

      statusChartInstance = new Chart(statusChart.value, {
        type: 'doughnut',
        data: {
          labels: [
            currentLang.value === 'fr' ? 'Payés' : 'Voaloa',
            currentLang.value === 'fr' ? 'Impayés' : 'Tsy voaloa'
          ],
          datasets: [{
            data: [payes, impayes],
            backgroundColor: ['#10b981', '#ef4444'],
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

    if (trendChart.value) {
      trendChartInstance = new Chart(trendChart.value, {
        type: 'bar',
        data: {
          labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin'],
          datasets: [{
            label: currentLang.value === 'fr' ? 'Payés' : 'Voaloa',
            data: [45, 52, 38, 61, 47, 55],
            backgroundColor: '#10b981',
            borderRadius: 4
          }, {
            label: currentLang.value === 'fr' ? 'Impayés' : 'Tsy voaloa',
            data: [12, 8, 15, 7, 11, 9],
            backgroundColor: '#ef4444',
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
            x: {
              stacked: true
            },
            y: {
              stacked: true,
              beginAtZero: true
            }
          }
        }
      })
    }
  })
}

const updateCharts = () => {
  if (statusChartInstance) {
    const payes = pointsEau.value.filter(p => p.status === 'Payé').length
    const impayes = pointsEau.value.length - payes
    statusChartInstance.data.datasets[0].data = [payes, impayes]
    statusChartInstance.data.labels = [
      currentLang.value === 'fr' ? 'Payés' : 'Voaloa',
      currentLang.value === 'fr' ? 'Impayés' : 'Tsy voaloa'
    ]
    statusChartInstance.update()
  }

  if (trendChartInstance) {
    trendChartInstance.data.datasets[0].label = currentLang.value === 'fr' ? 'Payés' : 'Voaloa'
    trendChartInstance.data.datasets[1].label = currentLang.value === 'fr' ? 'Impayés' : 'Tsy voaloa'
    trendChartInstance.update()
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
  if (statusChartInstance) {
    statusChartInstance.destroy()
  }
  if (trendChartInstance) {
    trendChartInstance.destroy()
  }
})

// Watcher pour la langue
watch(() => currentLang.value, () => {
  updateCharts()
})

// Meta tags
useHead({
  title: 'Paiements Forfaitaires - Hydria'
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