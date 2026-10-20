<template>
  <div class="container mx-auto px-4 py-8">
    <!-- Header -->
    <div class="mb-6">
      <div class="flex items-center gap-4 mb-2">
        <NuxtLink to="/employees/evaluations" class="btn btn-ghost btn-sm">
          <i class="fas fa-arrow-left mr-2"></i>Retour
        </NuxtLink>
        <h1 class="text-3xl font-bold">Nouvelle Évaluation</h1>
      </div>
      <p class="text-base-content/70">Créer une nouvelle évaluation de performance</p>
    </div>

    <!-- Loading state (employés/postes) -->
    <div v-if="loadingData" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>

    <!-- Formulaire -->
    <div v-else class="card bg-base-100 shadow max-w-3xl">
      <div class="card-body">
        <form @submit.prevent="handleSubmit" class="space-y-6">
          <!-- Sélection employé -->
          <div class="form-control">
            <label class="label">
              <span class="label-text">Employé à évaluer *</span>
            </label>
            <select
              v-model="formData.employe_id"
              class="select select-bordered"
              required
              @change="handleEmployeChange"
            >
              <option value="">-- Sélectionner un employé --</option>
              <option
                v-for="employe in employes"
                :key="employe.id"
                :value="employe.id"
              >
                {{ employe.prenom }} {{ employe.nom }} - {{ employe.poste_nom }}
              </option>
            </select>
          </div>

          <!-- Info poste (affiché automatiquement) -->
          <div v-if="selectedEmploye" class="alert alert-info">
            <i class="fas fa-info-circle"></i>
            <div>
              <p class="font-semibold">Poste: {{ selectedEmploye.poste_nom }}</p>
              <p class="text-sm">Les tâches de ce poste seront automatiquement chargées pour l'évaluation.</p>
            </div>
          </div>

          <!-- Sélection évaluateur -->
          <div class="form-control">
            <label class="label">
              <span class="label-text">Évaluateur *</span>
            </label>
            <select
              v-model="formData.evaluateur_id"
              class="select select-bordered"
              required
            >
              <option value="">-- Sélectionner un évaluateur --</option>
              <option
                v-for="employe in employes"
                :key="employe.id"
                :value="employe.id"
              >
                {{ employe.prenom }} {{ employe.nom }}
              </option>
            </select>
          </div>

          <!-- Période d'évaluation -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="form-control">
              <label class="label">
                <span class="label-text">Période début *</span>
              </label>
              <input
                v-model="formData.periode_debut"
                type="date"
                class="input input-bordered"
                required
              />
            </div>

            <div class="form-control">
              <label class="label">
                <span class="label-text">Période fin *</span>
              </label>
              <input
                v-model="formData.periode_fin"
                type="date"
                class="input input-bordered"
                required
              />
            </div>
          </div>

          <!-- Note d'information -->
          <div class="alert">
            <i class="fas fa-lightbulb"></i>
            <div>
              <p class="text-sm">
                <strong>Note :</strong> Une fois l'évaluation créée, vous pourrez noter chaque tâche de 0 à 2 :
              </p>
              <ul class="text-xs mt-2 ml-4 list-disc">
                <li><strong>0</strong> : Tâche non maîtrisée</li>
                <li><strong>1</strong> : Tâche partiellement maîtrisée</li>
                <li><strong>2</strong> : Tâche maîtrisée</li>
              </ul>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-2">
            <NuxtLink to="/employees/evaluations" class="btn btn-ghost">
              Annuler
            </NuxtLink>
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="loading"
            >
              <span v-if="loading" class="loading loading-spinner loading-sm"></span>
              <span v-else>
                <i class="fas fa-check mr-2"></i>Créer l'évaluation
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Error state -->
    <div v-if="error" class="alert alert-error mt-4 max-w-3xl">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// Composables
const { employes, loading, error, loadEmployes, createEvaluation } = useEvaluations()
const router = useRouter()

// État local
const loadingData = ref(true)
const formData = ref({
  employe_id: '',
  evaluateur_id: '',
  periode_debut: '',
  periode_fin: ''
})

// Employé sélectionné
const selectedEmploye = computed(() => {
  if (!formData.value.employe_id) return null
  return employes.value.find(e => e.id === formData.value.employe_id)
})

// Lifecycle
onMounted(async () => {
  loadingData.value = true
  await loadEmployes()
  loadingData.value = false

  // Définir les dates par défaut (6 derniers mois)
  const today = new Date()
  const sixMonthsAgo = new Date()
  sixMonthsAgo.setMonth(today.getMonth() - 6)

  formData.value.periode_fin = today.toISOString().split('T')[0]
  formData.value.periode_debut = sixMonthsAgo.toISOString().split('T')[0]
})

// Méthodes
const handleEmployeChange = () => {
  // Réinitialiser l'évaluateur si c'est le même que l'employé
  if (formData.value.evaluateur_id === formData.value.employe_id) {
    formData.value.evaluateur_id = ''
  }
}

const handleSubmit = async () => {
  // Validation
  if (formData.value.employe_id === formData.value.evaluateur_id) {
    alert('L\'employé et l\'évaluateur doivent être différents')
    return
  }

  const dateDebut = new Date(formData.value.periode_debut)
  const dateFin = new Date(formData.value.periode_fin)

  if (dateDebut >= dateFin) {
    alert('La date de début doit être antérieure à la date de fin')
    return
  }

  // Création
  const result = await createEvaluation({
    employe_id: formData.value.employe_id,
    evaluateur_id: formData.value.evaluateur_id,
    periode_debut: formData.value.periode_debut,
    periode_fin: formData.value.periode_fin
  })

  if (result.success && result.evaluation_id) {
    // Redirection vers la page de détail pour commencer la notation
    router.push(`/employees/evaluations/${result.evaluation_id}`)
  } else {
    alert('Erreur: ' + (result.error || 'Erreur inconnue'))
  }
}
</script>
