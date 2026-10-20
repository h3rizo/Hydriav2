<template>
  <div class="container mx-auto px-4 py-8">
    <!-- Header -->
    <div class="flex justify-between items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold">Fiches de poste</h1>
        <p class="text-base-content/70">Définir les tâches, descriptions et outils pour chaque poste</p>
      </div>
    </div>

    <!-- Sélection du poste -->
    <div class="card bg-base-100 shadow mb-6">
      <div class="card-body">
        <h2 class="card-title">Sélectionner un poste</h2>
        <select
          v-model="selectedPosteId"
          class="select select-bordered w-full"
          @change="handlePosteChange"
        >
          <option value="">-- Choisir un poste --</option>
          <option
            v-for="poste in postes"
            :key="poste.id"
            :value="poste.id"
          >
            {{ poste.nom_poste }}
          </option>
        </select>
      </div>
    </div>

    <!-- Zone d'affichage des fiches -->
    <div v-if="selectedPosteId" class="space-y-4">
      <!-- Bouton ajouter -->
      <div class="mb-4">
        <button
          class="btn btn-primary"
          @click="openCreateModal"
        >
          <i class="fas fa-plus mr-2"></i>Ajouter une tâche
        </button>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="flex justify-center py-8">
        <span class="loading loading-spinner loading-lg"></span>
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="alert alert-error">
        <i class="fas fa-exclamation-triangle mr-2"></i>
        <span>{{ error }}</span>
      </div>

      <!-- Empty state -->
      <div v-else-if="fiches.length === 0" class="alert alert-info">
        <i class="fas fa-info-circle mr-2"></i>
        <div>
          <p class="font-semibold">Aucune tâche définie pour ce poste</p>
          <p class="text-sm">Cliquez sur "Ajouter une tâche" pour commencer à définir les responsabilités de ce poste.</p>
        </div>
      </div>

      <!-- Liste des fiches -->
      <div v-else class="space-y-4">
        <div
          v-for="fiche in fiches"
          :key="fiche.id"
          class="card bg-base-200"
        >
          <div class="card-body">
            <div class="flex justify-between items-start">
              <div class="flex-1">
                <h3 class="card-title">{{ fiche.tache }}</h3>
                <p class="text-sm mt-2">{{ fiche.description }}</p>
                <p v-if="fiche.outils" class="text-sm text-info mt-2">
                  <i class="fas fa-tools mr-1"></i>{{ fiche.outils }}
                </p>
                <div class="badge badge-sm mt-2">Ordre: {{ fiche.ordre }}</div>
              </div>
              <div class="dropdown dropdown-end">
                <label tabindex="0" class="btn btn-ghost btn-sm">
                  <i class="fas fa-ellipsis-v"></i>
                </label>
                <ul tabindex="0" class="dropdown-content menu p-2 shadow bg-base-100 rounded-box w-52">
                  <li>
                    <a @click="openEditModal(fiche)">
                      <i class="fas fa-edit"></i>Modifier
                    </a>
                  </li>
                  <li>
                    <a class="text-error" @click="handleDelete(fiche)">
                      <i class="fas fa-trash"></i>Supprimer
                    </a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal création/édition -->
    <dialog ref="modalRef" class="modal">
      <div class="modal-box max-w-2xl">
        <h3 class="font-bold text-lg mb-4">{{ isEditing ? 'Modifier la tâche' : 'Nouvelle tâche' }}</h3>
        <form @submit.prevent="handleSubmit" class="space-y-4">
          <div class="form-control">
            <label class="label">
              <span class="label-text">Tâche *</span>
            </label>
            <input
              v-model="formData.tache"
              type="text"
              class="input input-bordered"
              required
            />
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">Description *</span>
            </label>
            <textarea
              v-model="formData.description"
              class="textarea textarea-bordered h-24"
              required
            ></textarea>
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">Outils nécessaires</span>
            </label>
            <textarea
              v-model="formData.outils"
              class="textarea textarea-bordered h-20"
            ></textarea>
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">Ordre</span>
            </label>
            <input
              v-model.number="formData.ordre"
              type="number"
              class="input input-bordered"
              min="0"
            />
          </div>

          <div class="modal-action">
            <button
              type="button"
              class="btn"
              @click="closeModal"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="loading"
            >
              <span v-if="loading" class="loading loading-spinner loading-sm"></span>
              <span v-else>Enregistrer</span>
            </button>
          </div>
        </form>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  </div>
</template>

<script setup lang="ts">
// Composables
const { fiches, postes, loading, error, loadPostes, loadFiches, createFiche, updateFiche, deleteFiche } = useFichesPoste()

// État local
const selectedPosteId = ref('')
const modalRef = ref<HTMLDialogElement | null>(null)
const isEditing = ref(false)
const editingFicheId = ref<string | null>(null)

const formData = ref({
  tache: '',
  description: '',
  outils: '',
  ordre: 0
})

// Lifecycle
onMounted(async () => {
  await loadPostes()
})

// Méthodes
const handlePosteChange = async () => {
  if (selectedPosteId.value) {
    await loadFiches(selectedPosteId.value)
  } else {
    fiches.value = []
  }
}

const openCreateModal = () => {
  isEditing.value = false
  editingFicheId.value = null
  formData.value = {
    tache: '',
    description: '',
    outils: '',
    ordre: 0
  }
  modalRef.value?.showModal()
}

const openEditModal = (fiche: any) => {
  isEditing.value = true
  editingFicheId.value = fiche.id
  formData.value = {
    tache: fiche.tache,
    description: fiche.description,
    outils: fiche.outils || '',
    ordre: fiche.ordre
  }
  modalRef.value?.showModal()
}

const closeModal = () => {
  modalRef.value?.close()
}

const handleSubmit = async () => {
  if (!selectedPosteId.value) {
    alert('Veuillez sélectionner un poste')
    return
  }

  const ficheData = {
    poste_id: selectedPosteId.value,
    ...formData.value
  }

  let result
  if (isEditing.value && editingFicheId.value) {
    result = await updateFiche(editingFicheId.value, ficheData)
  } else {
    result = await createFiche(ficheData)
  }

  if (result.success) {
    alert(result.message || 'Enregistrement réussi')
    closeModal()
  } else {
    alert('Erreur: ' + (result.error || 'Erreur inconnue'))
  }
}

const handleDelete = async (fiche: any) => {
  if (!confirm(`Supprimer la tâche "${fiche.tache}" ?`)) {
    return
  }

  const result = await deleteFiche(fiche.id, selectedPosteId.value)

  if (result.success) {
    alert(result.message || 'Suppression réussie')
  } else {
    alert('Erreur: ' + (result.error || 'Erreur inconnue'))
  }
}
</script>
