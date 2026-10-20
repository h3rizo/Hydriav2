<template>
  <div class="container mx-auto px-4 py-8">
    <!-- Header -->
    <div class="mb-6">
      <div class="flex items-center gap-4 mb-2">
        <NuxtLink to="/employees/evaluations" class="btn btn-ghost btn-sm">
          <i class="fas fa-arrow-left mr-2"></i>Retour
        </NuxtLink>
        <h1 class="text-3xl font-bold">Évaluation</h1>
        <span
          v-if="currentEvaluation"
          class="badge badge-lg"
          :class="{
            'badge-warning': currentEvaluation.statut === 'brouillon',
            'badge-info': currentEvaluation.statut === 'terminee',
            'badge-success': currentEvaluation.statut === 'validee'
          }"
        >
          {{ getStatutLabel(currentEvaluation.statut) }}
        </span>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading && !currentEvaluation" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>

    <!-- Error state -->
    <div v-else-if="error && !currentEvaluation" class="alert alert-error">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Contenu -->
    <div v-else-if="currentEvaluation" class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- Colonne principale (3/4) -->
      <div class="lg:col-span-3 space-y-6">
        <!-- Informations générales -->
        <div class="card bg-base-100 shadow">
          <div class="card-body">
            <h2 class="card-title">Informations</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p class="text-sm text-base-content/70">Employé</p>
                <p class="font-semibold">{{ currentEvaluation.employe_prenom }} {{ currentEvaluation.employe_nom }}</p>
                <p class="text-sm text-base-content/70">{{ currentEvaluation.employe_poste }}</p>
              </div>
              <div>
                <p class="text-sm text-base-content/70">Évaluateur</p>
                <p class="font-semibold">{{ currentEvaluation.evaluateur_prenom }} {{ currentEvaluation.evaluateur_nom }}</p>
              </div>
              <div>
                <p class="text-sm text-base-content/70">Période d'évaluation</p>
                <p class="font-semibold">
                  Du {{ formatDate(currentEvaluation.periode_debut) }}<br />
                  au {{ formatDate(currentEvaluation.periode_fin) }}
                </p>
              </div>
              <div>
                <p class="text-sm text-base-content/70">Score global</p>
                <div class="flex items-center gap-3 mt-1">
                  <div
                    class="radial-progress"
                    :style="`--value:${currentEvaluation.score_pourcentage}; --size:4rem; --thickness:4px;`"
                    :class="getScoreColor(currentEvaluation.score_pourcentage)"
                  >
                    {{ currentEvaluation.score_pourcentage }}%
                  </div>
                  <div>
                    <p class="font-bold text-xl">{{ currentEvaluation.score_obtenu }}/{{ currentEvaluation.score_total }}</p>
                    <p class="text-xs text-base-content/70">points</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Notation des tâches -->
        <div class="card bg-base-100 shadow">
          <div class="card-body">
            <h2 class="card-title">Notation par tâche</h2>
            <p class="text-sm text-base-content/70 mb-4">
              Évaluez chaque tâche de 0 à 2 : 0 = Non maîtrisée, 1 = Partiellement maîtrisée, 2 = Maîtrisée
            </p>

            <div class="space-y-4">
              <div
                v-for="detail in currentEvaluation.details"
                :key="detail.id"
                class="card bg-base-200"
              >
                <div class="card-body p-4">
                  <div class="flex justify-between items-start">
                    <div class="flex-1">
                      <h3 class="font-semibold">{{ detail.tache }}</h3>
                      <p class="text-sm text-base-content/70 mt-1">{{ detail.description }}</p>
                      <p v-if="detail.outils" class="text-xs text-info mt-2">
                        <i class="fas fa-tools mr-1"></i>{{ detail.outils }}
                      </p>
                    </div>

                    <!-- Boutons de notation -->
                    <div v-if="currentEvaluation.statut === 'brouillon'" class="flex gap-2 ml-4">
                      <button
                        v-for="note in [0, 1, 2]"
                        :key="note"
                        class="btn btn-sm"
                        :class="{
                          'btn-error': note === 0 && detail.note === 0,
                          'btn-warning': note === 1 && detail.note === 1,
                          'btn-success': note === 2 && detail.note === 2,
                          'btn-ghost': detail.note !== note
                        }"
                        @click="handleNoteChange(detail.id, note)"
                        :disabled="savingNote"
                      >
                        {{ note }}
                      </button>
                    </div>

                    <!-- Affichage note (mode lecture seule) -->
                    <div v-else class="ml-4">
                      <span
                        class="badge badge-lg"
                        :class="{
                          'badge-error': detail.note === 0,
                          'badge-warning': detail.note === 1,
                          'badge-success': detail.note === 2
                        }"
                      >
                        {{ detail.note }}/2
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Remarques -->
        <div class="card bg-base-100 shadow">
          <div class="card-body">
            <h2 class="card-title">Remarques</h2>
            <div v-if="currentEvaluation.statut === 'brouillon'" class="space-y-4">
              <textarea
                v-model="remarquesLocal"
                class="textarea textarea-bordered w-full h-32"
                placeholder="Saisir vos remarques générales..."
              ></textarea>
              <button
                class="btn btn-sm btn-primary"
                @click="handleSaveRemarques"
                :disabled="loading"
              >
                <span v-if="loading" class="loading loading-spinner loading-xs"></span>
                <span v-else><i class="fas fa-save mr-2"></i>Enregistrer</span>
              </button>
            </div>
            <div v-else>
              <p v-if="currentEvaluation.remarques" class="whitespace-pre-wrap">{{ currentEvaluation.remarques }}</p>
              <p v-else class="text-base-content/50 italic">Aucune remarque</p>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div v-if="currentEvaluation.statut === 'brouillon'" class="card bg-base-100 shadow">
          <div class="card-body">
            <h2 class="card-title">Actions</h2>
            <button
              class="btn btn-success"
              @click="handleTerminer"
              :disabled="loading"
            >
              <i class="fas fa-check mr-2"></i>Terminer l'évaluation
            </button>
            <p class="text-sm text-base-content/70 mt-2">
              Une fois terminée, l'évaluation ne pourra plus être modifiée et devra être validée par la direction.
            </p>
          </div>
        </div>
      </div>

      <!-- Sidebar historique (1/4) -->
      <div class="space-y-6">
        <div class="card bg-base-100 shadow">
          <div class="card-body">
            <h2 class="card-title text-lg">Historique</h2>
            <p class="text-sm text-base-content/70 mb-4">Évaluations précédentes de cet employé</p>

            <!-- Loading historique -->
            <div v-if="loadingHistorique" class="flex justify-center py-4">
              <span class="loading loading-spinner loading-sm"></span>
            </div>

            <!-- Liste historique -->
            <div v-else-if="historiqueEvaluations.length > 0" class="space-y-2">
              <div
                v-for="evaluation in historiqueEvaluations"
                :key="evaluation.id"
                class="card bg-base-200 cursor-pointer hover:bg-base-300"
                @click="openHistoriqueModal(evaluation.id)"
              >
                <div class="card-body p-3">
                  <p class="text-xs text-base-content/70">
                    {{ formatDate(evaluation.periode_debut) }} - {{ formatDate(evaluation.periode_fin) }}
                  </p>
                  <div class="flex items-center justify-between">
                    <span
                      class="badge badge-sm"
                      :class="{
                        'badge-info': evaluation.statut === 'terminee',
                        'badge-success': evaluation.statut === 'validee'
                      }"
                    >
                      {{ getStatutLabel(evaluation.statut) }}
                    </span>
                    <span class="text-sm font-semibold">{{ evaluation.score_pourcentage }}%</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Empty state -->
            <p v-else class="text-sm text-base-content/50 italic">Aucune évaluation précédente</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal historique -->
    <dialog ref="historiqueModalRef" class="modal">
      <div class="modal-box max-w-4xl">
        <h3 class="font-bold text-lg mb-4">Évaluation précédente</h3>

        <div v-if="historiqueEvaluationDetail" class="space-y-4">
          <!-- Info -->
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p class="text-base-content/70">Période</p>
              <p class="font-semibold">
                {{ formatDate(historiqueEvaluationDetail.periode_debut) }} - {{ formatDate(historiqueEvaluationDetail.periode_fin) }}
              </p>
            </div>
            <div>
              <p class="text-base-content/70">Score</p>
              <p class="font-semibold">{{ historiqueEvaluationDetail.score_obtenu }}/{{ historiqueEvaluationDetail.score_total }} ({{ historiqueEvaluationDetail.score_pourcentage }}%)</p>
            </div>
          </div>

          <!-- Détails -->
          <div class="overflow-x-auto">
            <table class="table table-zebra table-sm">
              <thead>
                <tr>
                  <th>Tâche</th>
                  <th class="text-center">Note</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="detail in historiqueEvaluationDetail.details" :key="detail.id">
                  <td>{{ detail.tache }}</td>
                  <td class="text-center">
                    <span
                      class="badge badge-sm"
                      :class="{
                        'badge-error': detail.note === 0,
                        'badge-warning': detail.note === 1,
                        'badge-success': detail.note === 2
                      }"
                    >
                      {{ detail.note }}/2
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Remarques -->
          <div v-if="historiqueEvaluationDetail.remarques">
            <p class="text-sm text-base-content/70 mb-2">Remarques</p>
            <p class="text-sm bg-base-200 p-3 rounded whitespace-pre-wrap">{{ historiqueEvaluationDetail.remarques }}</p>
          </div>
        </div>

        <div class="modal-action">
          <button class="btn" @click="closeHistoriqueModal">Fermer</button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  </div>
</template>

<script setup lang="ts">
// Composables
const route = useRoute()
const {
  currentEvaluation,
  historiqueEvaluations,
  loading,
  error,
  loadEvaluation,
  updateNote,
  updateRemarques,
  terminerEvaluation,
  loadHistorique,
  loadHistoriqueEvaluation
} = useEvaluations()
const { formatDate } = useTimezone()

// État local
const evaluationId = computed(() => route.params.id as string)
const remarquesLocal = ref('')
const savingNote = ref(false)
const loadingHistorique = ref(false)
const historiqueModalRef = ref<HTMLDialogElement | null>(null)
const historiqueEvaluationDetail = ref<any | null>(null)

// Lifecycle
onMounted(async () => {
  await loadEvaluation(evaluationId.value)

  if (currentEvaluation.value) {
    remarquesLocal.value = currentEvaluation.value.remarques || ''

    // Charger l'historique
    loadingHistorique.value = true
    await loadHistorique(currentEvaluation.value.employe_id)
    loadingHistorique.value = false
  }
})

// Méthodes
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

const handleNoteChange = async (detailId: string, note: number) => {
  savingNote.value = true
  const result = await updateNote(evaluationId.value, detailId, note)
  savingNote.value = false

  if (!result.success) {
    alert('Erreur lors de la mise à jour de la note')
  }
}

const handleSaveRemarques = async () => {
  const result = await updateRemarques(evaluationId.value, remarquesLocal.value)

  if (result.success) {
    alert('Remarques enregistrées')
  } else {
    alert('Erreur: ' + (result.error || 'Erreur inconnue'))
  }
}

const handleTerminer = async () => {
  if (!confirm('Terminer cette évaluation ? Elle ne pourra plus être modifiée.')) {
    return
  }

  const result = await terminerEvaluation(evaluationId.value)

  if (result.success) {
    alert('Évaluation terminée avec succès')
  } else {
    alert('Erreur: ' + (result.error || 'Erreur inconnue'))
  }
}

const openHistoriqueModal = async (evalId: string) => {
  const result = await loadHistoriqueEvaluation(evalId)

  if (result.success && result.evaluation) {
    historiqueEvaluationDetail.value = result.evaluation
    historiqueModalRef.value?.showModal()
  } else {
    alert('Erreur lors du chargement de l\'évaluation')
  }
}

const closeHistoriqueModal = () => {
  historiqueModalRef.value?.close()
  historiqueEvaluationDetail.value = null
}
</script>
