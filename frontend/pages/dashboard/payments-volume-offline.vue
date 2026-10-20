<template>
  <div class="container mx-auto px-4 py-6 space-y-6">
    <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-base-content">Pilote Offline - Paiements au volume</h1>
        <p class="text-sm text-base-content/70">
          Lecture avec cache local + rafraichissement reseau
        </p>
      </div>

      <div class="flex items-center gap-2">
        <select v-model="annee" class="select select-bordered select-sm w-32">
          <option v-for="year in years" :key="year" :value="year">{{ year }}</option>
        </select>
        <button class="btn btn-sm btn-primary" :disabled="loading" @click="refresh(false)">
          <i class="fas fa-sync-alt mr-2" :class="{ 'animate-spin': loading }"></i>
          Actualiser
        </button>
        <button class="btn btn-sm btn-outline" :disabled="loading" @click="refresh(true)">
          Reseau force
        </button>
      </div>
    </div>

    <div class="flex items-center gap-2 text-sm">
      <span v-if="fromCache" class="badge badge-warning">Cache local</span>
      <span v-else class="badge badge-success">Reseau</span>
      <span class="text-base-content/70">
        Derniere sync:
        {{ lastSync ? new Date(lastSync).toLocaleString('fr-FR') : 'Jamais' }}
      </span>
      <span v-if="error" class="text-error">{{ error }}</span>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
      <div class="stat bg-base-200 rounded-lg">
        <div class="stat-title">Communes</div>
        <div class="stat-value text-primary">{{ totals.totalCommunes }}</div>
      </div>
      <div class="stat bg-base-200 rounded-lg">
        <div class="stat-title">Releves</div>
        <div class="stat-value text-info">{{ totals.totalNbReleves }}</div>
      </div>
      <div class="stat bg-base-200 rounded-lg">
        <div class="stat-title">Prevu</div>
        <div class="stat-value text-warning">{{ formatMGA(totals.totalReleves) }}</div>
      </div>
      <div class="stat bg-base-200 rounded-lg">
        <div class="stat-title">Realise</div>
        <div class="stat-value text-success">{{ formatMGA(totals.totalDiamex) }}</div>
      </div>
      <div class="stat bg-base-200 rounded-lg">
        <div class="stat-title">Taux global</div>
        <div class="stat-value">{{ totals.globalRate }}%</div>
      </div>
    </div>

    <div class="card bg-base-100 border border-base-300">
      <div class="card-body p-0">
        <div class="overflow-x-auto">
          <table class="table table-zebra">
            <thead>
              <tr>
                <th>Region</th>
                <th>District</th>
                <th>Commune</th>
                <th>Releves</th>
                <th>Prevu</th>
                <th>Realise</th>
                <th>Ecart</th>
                <th>Taux</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="`${row.region}-${row.district}-${row.commune}`">
                <td>{{ row.region }}</td>
                <td>{{ row.district }}</td>
                <td>{{ row.commune }}</td>
                <td>{{ row.nb_releves }}</td>
                <td>{{ formatMGA(row.total_releves) }}</td>
                <td>{{ formatMGA(row.total_diamex) }}</td>
                <td :class="row.ecart > 0 ? 'text-warning' : 'text-success'">
                  {{ formatMGA(row.ecart) }}
                </td>
                <td>
                  <span class="badge" :class="rateClass(row.taux)">{{ row.taux }}%</span>
                </td>
              </tr>
              <tr v-if="rows.length === 0 && !loading">
                <td colspan="8" class="text-center text-base-content/60 py-6">
                  Aucune donnee disponible
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const currentYear = new Date().getFullYear()
const years = [currentYear, currentYear - 1, currentYear - 2]
const annee = ref(currentYear)

const {
  loading,
  error,
  fromCache,
  lastSync,
  rows,
  totals,
  fetchCommuneSummary
} = useOfflineVolumePilot()

const refresh = async (forceNetwork: boolean) => {
  await fetchCommuneSummary(annee.value, forceNetwork)
}

const formatMGA = (value: number) => {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'MGA',
    maximumFractionDigits: 0
  }).format(value || 0)
}

const rateClass = (rate: number) => {
  if (rate >= 95) return 'badge-success'
  if (rate >= 80) return 'badge-warning'
  return 'badge-error'
}

watch(annee, async () => {
  await refresh(false)
})

onMounted(async () => {
  await refresh(false)
})

useHead({
  title: 'Pilote Offline - Paiements volume'
})
</script>

