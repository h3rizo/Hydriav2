<template>
  <div class="container mx-auto px-4 py-6">
    <!-- En-tête avec titre et actions -->
    <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold text-base-content mb-2">
          <span :key="langKey">{{ getTranslation('dashboard.payments_volume') }}</span>
        </h1>
        <div class="breadcrumbs text-sm">
          <ul>
            <li><NuxtLink to="/dashboard"><span :key="langKey">{{ getTranslation('nav.dashboard') }}</span></NuxtLink></li>
            <li><span :key="langKey">{{ getTranslation('dashboard.payments_volume') }}</span></li>
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
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'Période' : 'Fotoana' }}</span></span>
          </label>
          <select v-model="filters.periode" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="mois" :key="langKey + '-period-month'">{{ currentLang === 'fr' ? 'Ce mois' : 'Ity volana ity' }}</option>
            <option value="trimestre" :key="langKey + '-period-quarter'">{{ currentLang === 'fr' ? 'Ce trimestre' : 'Ity telovolana ity' }}</option>
            <option value="annee" :key="langKey + '-period-year'">{{ currentLang === 'fr' ? 'Cette année' : 'Ity taona ity' }}</option>
          </select>
        </div>

        <div class="form-control">
          <label class="label">
            <span class="label-text"><span :key="langKey">{{ currentLang === 'fr' ? 'Tranche' : 'Sokajy' }}</span></span>
          </label>
          <select v-model="filters.tranche" @change="applyFilters" class="select select-bordered select-sm w-full max-w-xs">
            <option value="" :key="langKey + '-tranche-all'">{{ currentLang === 'fr' ? 'Toutes les tranches' : 'Sokajy rehetra' }}</option>
            <option value="0-10">0-10 m³</option>
            <option value="11-20">11-20 m³</option>
            <option value="21+">21+ m³</option>
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
        <!-- Volume total consommé -->
        <div class="stat-card info">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-info-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Volume Total (m³)' : 'Volim tanteraka (m³)' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.volume_total.toLocaleString() }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-tint"></i>
            </div>
          </div>
        </div>

        <!-- Chiffre d'affaires volumétrique -->
        <div class="stat-card success">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-success-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Chiffre d\'Affaires' : 'Vola miditra' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ formatCurrency(stats.chiffre_affaires) }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-chart-line"></i>
            </div>
          </div>
        </div>

        <!-- Prix moyen par m³ -->
        <div class="stat-card warning">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-warning-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Prix Moyen/m³' : 'Vidin\'ny m³ antonony' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ formatCurrency(stats.prix_moyen) }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-calculator"></i>
            </div>
          </div>
        </div>

        <!-- Nombre de compteurs -->
        <div class="stat-card">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-primary-content/75 text-sm font-medium">
                <span :key="langKey">{{ currentLang === 'fr' ? 'Compteurs Actifs' : 'Metatra miasa' }}</span>
              </div>
              <div class="text-2xl font-bold">{{ stats.compteurs_actifs }}</div>
            </div>
            <div class="text-3xl opacity-75">
              <i class="fas fa-tachometer-alt"></i>
            </div>
          </div>
        </div>
      </div>

      <!-- Graphiques -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <!-- Répartition par tranche de consommation -->
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-chart-pie mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Répartition par Tranche' : 'Fizarana araka ny sokajy' }}</span>
          </h3>
          <div class="chart-container">
            <canvas ref="trancheChart"></canvas>
          </div>
        </div>

        <!-- Évolution de la consommation -->
        <div class="dashboard-card">
          <h3 class="text-lg font-semibold mb-4">
            <i class="fas fa-chart-area mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Évolution Consommation' : 'Fivoaran\'ny fampiasana' }}</span>
          </h3>
          <div class="chart-container">
            <canvas ref="evolutionChart"></canvas>
          </div>
        </div>
      </div>

      <!-- Tableau des consommations par compteur -->
      <div class="dashboard-card">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-semibold">
            <i class="fas fa-list mr-2 text-primary"></i>
            <span :key="langKey">{{ currentLang === 'fr' ? 'Consommations par Compteur' : 'Fampiasana isaky ny metatra' }}</span>
          </h3>
          <div class="badge badge-outline">{{ filteredCompteurs.length }} <span :key="langKey">{{ currentLang === 'fr' ? 'compteurs' : 'metatra' }}</span></div>
        </div>

        <div class="overflow-x-auto">
          <table class="table table-zebra w-full">
            <thead>
              <tr class="bg-base-200">
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'N° Compteur' : 'Laharan\'ny metatra' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Abonné' : 'Mpanjifa' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Consommation (m³)' : 'Fampiasana (m³)' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Tranche Tarifaire' : 'Sokajin-kevitra' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Montant' : 'Vola' }}</span></th>
                <th><span :key="langKey">{{ currentLang === 'fr' ? 'Statut' : 'Sata' }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="compteur in filteredCompteurs" :key="compteur.id">
                <td>
                  <div class="font-mono text-sm">{{ compteur.numero }}</div>
                </td>
                <td>
                  <div class="font-medium">{{ compteur.abonne }}</div>
                </td>
                <td>
                  <div class="font-bold text-info">{{ compteur.consommation }} m³</div>
                </td>
                <td>
                  <span class="badge badge-outline">{{ compteur.tranche }}</span>
                </td>
                <td>
                  <div class="font-bold text-success">{{ formatCurrency(compteur.montant) }}</div>
                </td>
                <td>
                  <span v-if="compteur.status === 'Payé'" class="badge badge-success badge-sm">
                    <span :key="langKey">{{ currentLang === 'fr' ? 'Payé' : 'Voaloa' }}</span>
                  </span>
                  <span v-else class="badge badge-error badge-sm">
                    <span :key="langKey">{{ currentLang === 'fr' ? 'Impayé' : 'Tsy voaloa' }}</span>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Message si aucun résultat -->
          <div v-if="filteredCompteurs.length === 0" class="text-center text-base-content/60 py-8">
            <i class="fas fa-tachometer-alt text-4xl mb-2"></i>
            <div><span :key="langKey">{{ currentLang === 'fr' ? 'Aucun compteur trouvé' : 'Tsy misy metatra hita' }}</span></div>
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
  volume_total: 0,
  chiffre_affaires: 0,
  prix_moyen: 0,
  compteurs_actifs: 0
})

const filters = ref({
  periode: 'mois',
  tranche: ''
})

const compteurs = ref([
  { id: 1, numero: 'CPT001', abonne: 'Rakoto Jean', consommation: 15, tranche: '11-20 m³', montant: 52500, status: 'Payé' },
  { id: 2, numero: 'CPT002', abonne: 'Rasoa Marie', consommation: 8, tranche: '0-10 m³', montant: 24000, status: 'Impayé' },
  { id: 3, numero: 'CPT003', abonne: 'Randria Paul', consommation: 25, tranche: '21+ m³', montant: 87500, status: 'Payé' },
  { id: 4, numero: 'CPT004', abonne: 'Rabe Hery', consommation: 12, tranche: '11-20 m³', montant: 42000, status: 'Impayé' },
  { id: 5, numero: 'CPT005', abonne: 'Rasoanaivo Nivo', consommation: 7, tranche: '0-10 m³', montant: 21000, status: 'Payé' }
])

// Calculs
const filteredCompteurs = computed(() => {
  return compteurs.value.filter(compteur => {
    if (filters.value.tranche) {
      if (filters.value.tranche === '0-10' && compteur.consommation > 10) return false
      if (filters.value.tranche === '11-20' && (compteur.consommation <= 10 || compteur.consommation > 20)) return false
      if (filters.value.tranche === '21+' && compteur.consommation <= 20) return false
    }
    return true
  })
})

// Références des graphiques
const trancheChart = ref(null)
const evolutionChart = ref(null)
let trancheChartInstance = null
let evolutionChartInstance = null

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
    calculateStats()
    updateCharts()
  } catch (error) {
    console.error('Erreur lors du rafraîchissement:', error)
  } finally {
    loading.value = false
  }
}

const calculateStats = () => {
  const volumeTotal = compteurs.value.reduce((sum, c) => sum + c.consommation, 0)
  const chiffreAffaires = compteurs.value.reduce((sum, c) => sum + c.montant, 0)
  const prixMoyen = volumeTotal > 0 ? chiffreAffaires / volumeTotal : 0

  stats.value = {
    volume_total: volumeTotal,
    chiffre_affaires: chiffreAffaires,
    prix_moyen: prixMoyen,
    compteurs_actifs: compteurs.value.length
  }
}

const applyFilters = () => {
  // Les filtres sont appliqués automatiquement via computed
}

const resetFilters = () => {
  filters.value.periode = 'mois'
  filters.value.tranche = ''
}

const exportData = () => {
  alert(currentLang.value === 'fr' ? 'Fonctionnalité d\'export à implémenter' : 'Fiasa avoaka mbola tsy vita')
}

const initCharts = () => {
  nextTick(() => {
    if (trancheChart.value) {
      const tranche0_10 = compteurs.value.filter(c => c.consommation <= 10).length
      const tranche11_20 = compteurs.value.filter(c => c.consommation > 10 && c.consommation <= 20).length
      const tranche21plus = compteurs.value.filter(c => c.consommation > 20).length

      trancheChartInstance = new Chart(trancheChart.value, {
        type: 'doughnut',
        data: {
          labels: ['0-10 m³', '11-20 m³', '21+ m³'],
          datasets: [{
            data: [tranche0_10, tranche11_20, tranche21plus],
            backgroundColor: ['#06b6d4', '#10b981', '#f59e0b'],
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

    if (evolutionChart.value) {
      evolutionChartInstance = new Chart(evolutionChart.value, {
        type: 'line',
        data: {
          labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin'],
          datasets: [{
            label: currentLang.value === 'fr' ? 'Volume (m³)' : 'Volim (m³)',
            data: [420, 380, 450, 520, 480, 550],
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.1)',
            fill: true,
            tension: 0.4
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
  if (trancheChartInstance) {
    const tranche0_10 = compteurs.value.filter(c => c.consommation <= 10).length
    const tranche11_20 = compteurs.value.filter(c => c.consommation > 10 && c.consommation <= 20).length
    const tranche21plus = compteurs.value.filter(c => c.consommation > 20).length
    trancheChartInstance.data.datasets[0].data = [tranche0_10, tranche11_20, tranche21plus]
    trancheChartInstance.update()
  }

  if (evolutionChartInstance) {
    evolutionChartInstance.data.datasets[0].label = currentLang.value === 'fr' ? 'Volume (m³)' : 'Volim (m³)'
    evolutionChartInstance.update()
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
  if (trancheChartInstance) {
    trancheChartInstance.destroy()
  }
  if (evolutionChartInstance) {
    evolutionChartInstance.destroy()
  }
})

// Watcher pour la langue
watch(() => currentLang.value, () => {
  updateCharts()
})

// Meta tags
useHead({
  title: 'Paiements au Volume - Hydria'
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

.stat-card.info {
  @apply bg-info text-info-content;
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