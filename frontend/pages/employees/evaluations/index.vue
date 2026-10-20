<template>
  <div class="container mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex justify-between items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold">Évaluations des employés</h1>
        <p class="text-base-content/70">Gestion des évaluations de performance</p>
      </div>
      <NuxtLink to="/employees/evaluations/creer" class="btn btn-primary">
        <i class="fas fa-plus mr-2"></i>Nouvelle Évaluation
      </NuxtLink>
    </div>

    <!-- Filtres -->
    <div class="card bg-base-100 shadow mb-6">
      <div class="card-body">
        <h2 class="card-title text-lg mb-4">Filtres</h2>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <!-- Filtre Employé -->
          <div class="form-control">
            <label class="label">
              <span class="label-text">Employé</span>
            </label>
            <select v-model="filters.employe_id" class="select select-bordered">
              <option value="">Tous les employés</option>
              <optgroup
                v-for="baseGroup in employeeFilterGroups"
                :key="baseGroup.name"
                :label="`Base : ${baseGroup.name}`"
              >
                <option
                  v-for="item in baseGroup.options"
                  :key="item.key"
                  :value="item.value"
                  :disabled="item.disabled"
                >{{ item.label }}</option>
              </optgroup>
            </select>
          </div>

          <!-- Filtre Statut -->
          <div class="form-control">
            <label class="label">
              <span class="label-text">Statut</span>
            </label>
            <select v-model="filters.statut" class="select select-bordered">
              <option value="">Tous les statuts</option>
              <option value="brouillon">Brouillon</option>
              <option value="terminee">Terminée</option>
              <option value="validee">Validée</option>
            </select>
          </div>

          <!-- Filtre Année -->
          <div class="form-control">
            <label class="label">
              <span class="label-text">Année</span>
            </label>
            <select v-model="filters.annee" class="select select-bordered">
              <option value="">Toutes les années</option>
              <option
                v-for="year in years"
                :key="year"
                :value="year"
              >
                {{ year }}
              </option>
            </select>
          </div>
        </div>

        <div class="flex gap-2 mt-4">
          <button class="btn btn-primary" @click="applyFilters">
            <i class="fas fa-filter mr-2"></i>Filtrer
          </button>
          <button class="btn btn-ghost" @click="resetFilters">
            <i class="fas fa-times mr-2"></i>Réinitialiser
          </button>
        </div>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="alert alert-error">
      <i class="fas fa-exclamation-triangle mr-2"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="evaluations.length === 0" class="alert alert-info">
      <i class="fas fa-info-circle mr-2"></i>
      <div>
        <p class="font-semibold">Aucune évaluation trouvée</p>
        <p class="text-sm">Créez une nouvelle évaluation en cliquant sur le bouton ci-dessus.</p>
      </div>
    </div>

    <!-- Liste des évaluations -->
    <div v-else class="card bg-base-100 shadow">
      <div class="card-body">
        <div class="overflow-x-auto">
          <table class="table table-zebra">
            <thead>
              <tr>
                <th>Employé</th>
                <th>Poste</th>
                <th>Évaluateur</th>
                <th>Période</th>
                <th>Score</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="evaluation in evaluations" :key="evaluation.id">
                <td>
                  <div class="font-semibold">{{ evaluation.employe_prenom }} {{ evaluation.employe_nom }}</div>
                </td>
                <td>{{ evaluation.employe_poste }}</td>
                <td>{{ evaluation.evaluateur_prenom }} {{ evaluation.evaluateur_nom }}</td>
                <td>
                  <div class="text-sm">
                    Du {{ formatDate(evaluation.periode_debut) }}<br />
                    au {{ formatDate(evaluation.periode_fin) }}
                  </div>
                </td>
                <td>
                  <div v-if="evaluation.statut !== 'brouillon'" class="flex items-center gap-2">
                    <div class="radial-progress text-sm" :style="`--value:${evaluation.score_pourcentage}; --size:3rem; --thickness:3px;`" :class="getScoreColor(evaluation.score_pourcentage)">
                      {{ evaluation.score_pourcentage }}%
                    </div>
                    <div class="text-xs">
                      {{ evaluation.score_obtenu }}/{{ evaluation.score_total }}
                    </div>
                  </div>
                  <span v-else class="text-base-content/50 text-sm">-</span>
                </td>
                <td>
                  <span
                    class="badge badge-sm"
                    :class="{
                      'badge-warning': evaluation.statut === 'brouillon',
                      'badge-info': evaluation.statut === 'terminee',
                      'badge-success': evaluation.statut === 'validee'
                    }"
                  >
                    {{ getStatutLabel(evaluation.statut) }}
                  </span>
                </td>
                <td>
                  <NuxtLink
                    :to="`/employees/evaluations/${evaluation.id}`"
                    class="btn btn-ghost btn-xs"
                  >
                    <i class="fas fa-eye mr-1"></i>Voir
                  </NuxtLink>
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
// Composables
const { evaluations, employes, loading, error, loadEvaluations, loadEmployes } = useEvaluations()
const { formatDate } = useTimezone()

// État local
const filters = ref({
  employe_id: '',
  statut: '',
  annee: null as number | null
})

const employeeFilterGroups = computed(() => {
  const bases = new Map<string, Map<string, any[]>>()
  const sortedEmployees = [...employes.value].sort((left, right) => {
    const leftKey = `${left.base_nom || 'Sans base'}|${left.poste_nom || 'Sans poste'}|${left.prenom || ''}|${left.nom || ''}`
    const rightKey = `${right.base_nom || 'Sans base'}|${right.poste_nom || 'Sans poste'}|${right.prenom || ''}|${right.nom || ''}`
    return leftKey.localeCompare(rightKey, 'fr', { sensitivity: 'base' })
  })

  sortedEmployees.forEach((employee) => {
    const baseName = employee.base_nom || 'Sans base'
    const posteName = employee.poste_nom || 'Sans poste'
    if (!bases.has(baseName)) bases.set(baseName, new Map())
    const postes = bases.get(baseName)!
    if (!postes.has(posteName)) postes.set(posteName, [])
    postes.get(posteName)!.push(employee)
  })

  return Array.from(bases, ([name, postes]) => ({
    name,
    options: Array.from(postes).flatMap(([posteName, posteEmployees]) => [
      { key: `poste-${name}-${posteName}`, value: '', label: `-- ${posteName} --`, disabled: true },
      ...posteEmployees.map(employee => ({
        key: employee.id,
        value: employee.id,
        label: `  ${employee.prenom || ''} ${employee.nom || ''}`.trim(),
        disabled: false
      }))
    ])
  }))
})

// Années disponibles (5 dernières années)
const currentYear = new Date().getFullYear()
const years = computed(() => {
  return Array.from({ length: 5 }, (_, i) => currentYear - i)
})

// Lifecycle
onMounted(async () => {
  await Promise.all([
    loadEmployes(),
    loadEvaluations()
  ])
})

// Méthodes
const applyFilters = async () => {
  const filterParams: any = {}
  if (filters.value.employe_id) filterParams.employe_id = filters.value.employe_id
  if (filters.value.statut) filterParams.statut = filters.value.statut
  if (filters.value.annee) filterParams.annee = filters.value.annee

  await loadEvaluations(filterParams)
}

const resetFilters = async () => {
  filters.value = {
    employe_id: '',
    statut: '',
    annee: null
  }
  await loadEvaluations()
}

const getStatutLabel = (statut: string) => {
  const labels: Record<string, string> = {
    brouillon: 'Brouillon',
    terminee: 'Terminée',
    validee: 'Validée'
  }
  return labels[statut] || statut
}

const getScoreColor = (pourcentage: number) => {
  if (pourcentage >= 80) return 'text-success'
  if (pourcentage >= 60) return 'text-warning'
  return 'text-error'
}
</script>
