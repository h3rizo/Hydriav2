<template>
  <div class="container mx-auto px-4 py-6">
    <!-- En-tête -->
    <div class="flex justify-between items-center mb-6">
      <div>
        <h1 class="text-3xl font-bold text-base-content">
          <i class="fas fa-book-open text-primary mr-3"></i>Notes
        </h1>
        <p class="text-base-content/70 mt-1">Organisez vos informations et liez-les aux données Hydria</p>
      </div>
      <button class="btn btn-primary" @click="openCreateModal">
        <i class="fas fa-plus mr-2"></i>Nouvelle note
      </button>
    </div>

    <!-- Barre de recherche -->
    <div class="flex gap-3 mb-6">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Rechercher une note..."
        class="input input-bordered flex-1"
        @input="debouncedSearch"
      />
      <select v-model="selectedTag" class="select select-bordered" @change="filterNotes">
        <option value="">Tous les sujets</option>
        <option v-for="tag in tags" :key="tag.id" :value="tag.id">{{ tag.name }}</option>
      </select>
      <select v-model="selectedVisibility" class="select select-bordered" @change="filterNotes">
        <option value="">Toute visibilité</option>
        <option value="private">Privée</option>
        <option value="team">Équipe</option>
        <option value="all">Tous</option>
      </select>
    </div>

    <!-- Indicateur de chargement -->
    <div v-if="loading" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- Sidebar gauche : Navigation -->
      <div class="lg:col-span-1 space-y-4">
        <!-- Catégories -->
        <div class="card bg-base-100 shadow">
          <div class="card-body p-4">
            <h3 class="font-bold text-base-content text-sm uppercase tracking-wide mb-3">
              <i class="fas fa-folder text-primary mr-2"></i>Navigation
            </h3>
            <ul class="space-y-1">
              <li>
                <button
                  class="btn btn-ghost btn-sm w-full justify-start"
                  :class="{ 'btn-active': activeFilter === 'all' }"
                  @click="setFilter('all')"
                >
                  <i class="fas fa-file-alt mr-2"></i>Toutes les notes
                  <span class="badge badge-primary ml-auto">{{ notes.length }}</span>
                </button>
              </li>
              <li>
                <button
                  class="btn btn-ghost btn-sm w-full justify-start"
                  :class="{ 'btn-active': activeFilter === 'private' }"
                  @click="setFilter('private')"
                >
                  <i class="fas fa-lock mr-2"></i>Mes notes
                </button>
              </li>
              <li>
                <button
                  class="btn btn-ghost btn-sm w-full justify-start"
                  :class="{ 'btn-active': activeFilter === 'templates' }"
                  @click="setFilter('templates')"
                >
                  <i class="fas fa-copy mr-2"></i>Modèles
                </button>
              </li>
            </ul>

            <div class="divider my-2"></div>

            <!-- Sujets / Tags -->
            <h3 class="font-bold text-base-content text-sm uppercase tracking-wide mb-3">
              <i class="fas fa-tags text-secondary mr-2"></i>Sujets
            </h3>
            <ul class="space-y-1">
              <li v-for="tag in tags" :key="tag.id">
                <button
                  class="btn btn-ghost btn-sm w-full justify-start"
                  @click="selectedTag = tag.id; filterNotes()"
                >
                  <span
                    class="w-3 h-3 rounded-full mr-2"
                    :style="{ backgroundColor: tag.color }"
                  ></span>
                  {{ tag.name }}
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Liste des notes -->
      <div class="lg:col-span-3">
        <!-- État vide -->
        <div v-if="filteredNotes.length === 0" class="card bg-base-100 shadow">
          <div class="card-body items-center text-center py-16">
            <i class="fas fa-sticky-note text-6xl text-base-content/20 mb-4"></i>
            <h3 class="text-xl font-bold text-base-content/50">Aucune note trouvée</h3>
            <p class="text-base-content/40 mb-6">Commencez par créer votre première note</p>
            <button class="btn btn-primary" @click="openCreateModal">
              <i class="fas fa-plus mr-2"></i>Créer une note
            </button>
          </div>
        </div>

        <!-- Grille de notes -->
        <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <div
            v-for="note in filteredNotes"
            :key="note.id"
            class="card bg-base-100 shadow hover:shadow-md transition-all duration-200 cursor-pointer hover:-translate-y-1"
            @click="openNote(note)"
          >
            <div class="card-body p-4">
              <!-- Header note -->
              <div class="flex justify-between items-start mb-2">
                <h3 class="font-bold text-base-content line-clamp-2 flex-1">{{ note.title }}</h3>
                <div class="dropdown dropdown-end ml-2" @click.stop>
                  <button class="btn btn-ghost btn-xs">
                    <i class="fas fa-ellipsis-v"></i>
                  </button>
                  <ul class="dropdown-content menu bg-base-100 shadow rounded-box z-50 w-40">
                    <li><a @click="openNote(note)"><i class="fas fa-edit mr-2"></i>Modifier</a></li>
                    <li><a class="text-error" @click="deleteNote(note.id)"><i class="fas fa-trash mr-2"></i>Supprimer</a></li>
                  </ul>
                </div>
              </div>

              <!-- Aperçu du contenu -->
              <p class="text-base-content/60 text-sm line-clamp-3 mb-3">
                {{ note.content_text || 'Note sans contenu...' }}
              </p>

              <!-- Tags -->
              <div class="flex flex-wrap gap-1 mb-3" v-if="note.tags && note.tags.length">
                <span
                  v-for="tag in note.tags"
                  :key="tag.id"
                  class="badge badge-sm"
                  :style="{ backgroundColor: tag.color + '30', color: tag.color, border: '1px solid ' + tag.color }"
                >
                  {{ tag.name }}
                </span>
              </div>

              <!-- Liens Hydria -->
              <div v-if="note.links && note.links.length" class="mb-3">
                <div v-for="link in note.links.slice(0,2)" :key="link.id" class="flex items-center gap-1 text-xs text-info">
                  <i class="fas fa-link"></i>
                  <span>{{ link.label || link.entity_name }}</span>
                </div>
              </div>

              <!-- Footer -->
              <div class="flex items-center justify-between mt-auto pt-2 border-t border-base-200">
                <div class="flex items-center gap-2">
                  <span class="badge badge-xs" :class="visibilityBadge(note.visibility)">
                    <i :class="visibilityIcon(note.visibility)" class="mr-1"></i>
                    {{ visibilityLabel(note.visibility) }}
                  </span>
                  <span v-if="note.is_template" class="badge badge-xs badge-accent">Modèle</span>
                </div>
                <span class="text-xs text-base-content/40">{{ formatDate(note.updated_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal Créer/Modifier note -->
    <dialog id="noteModal" class="modal">
      <div class="modal-box w-11/12 max-w-3xl">
        <h3 class="font-bold text-lg mb-4">
          <i class="fas fa-edit text-primary mr-2"></i>
          {{ editingNote ? 'Modifier la note' : 'Nouvelle note' }}
        </h3>

        <div class="space-y-4">
          <div class="form-control">
            <label class="label"><span class="label-text font-medium">Titre *</span></label>
            <input v-model="noteForm.title" type="text" placeholder="Titre de la note" class="input input-bordered" />
          </div>

          <div class="form-control">
            <label class="label"><span class="label-text font-medium">Contenu</span></label>
            <textarea
              v-model="noteForm.content_text"
              class="textarea textarea-bordered h-40"
              placeholder="Rédigez votre note ici..."
            ></textarea>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div class="form-control">
              <label class="label"><span class="label-text font-medium">Visibilité</span></label>
              <select v-model="noteForm.visibility" class="select select-bordered">
                <option value="private">🔒 Privée</option>
                <option value="team">👥 Équipe</option>
                <option value="all">🌐 Tous</option>
              </select>
            </div>
            <div class="form-control">
              <label class="label"><span class="label-text font-medium">Sujets</span></label>
              <select v-model="noteForm.tag_ids" multiple class="select select-bordered">
                <option v-for="tag in tags" :key="tag.id" :value="tag.id">{{ tag.name }}</option>
              </select>
            </div>
          </div>

          <div class="form-control">
            <label class="cursor-pointer label justify-start gap-3">
              <input type="checkbox" v-model="noteForm.is_template" class="checkbox checkbox-accent" />
              <span class="label-text">Sauvegarder comme modèle réutilisable</span>
            </label>
          </div>
        </div>

        <div class="modal-action">
          <button class="btn btn-ghost" @click="closeModal">Annuler</button>
          <button class="btn btn-primary" :class="{ loading: saving }" @click="saveNote">
            <i class="fas fa-save mr-2" v-if="!saving"></i>
            {{ editingNote ? 'Mettre à jour' : 'Créer la note' }}
          </button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop"><button>close</button></form>
    </dialog>
  </div>
</template>

<script setup>
const config = useRuntimeConfig()
const API_BASE = config.public.apiBase || 'https://www.hydria.mg/api/notes'

// État réactif
const loading = ref(true)
const saving = ref(false)
const notes = ref([])
const tags = ref([])
const searchQuery = ref('')
const selectedTag = ref('')
const selectedVisibility = ref('')
const activeFilter = ref('all')
const editingNote = ref(null)

const noteForm = ref({
  title: '',
  content_text: '',
  visibility: 'private',
  tag_ids: [],
  is_template: false,
  parent: null
})

// Charger les notes et tags
const loadData = async () => {
  loading.value = true
  try {
    const [notesData, tagsData] = await Promise.all([
      $fetch(`${API_BASE}/notes/`),
      $fetch(`${API_BASE}/tags/`)
    ])
    notes.value = notesData.results || notesData
    tags.value = tagsData.results || tagsData
  } catch (e) {
    console.error('Erreur chargement notes:', e)
  } finally {
    loading.value = false
  }
}

// Notes filtrées
const filteredNotes = computed(() => {
  let result = notes.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(n => n.title.toLowerCase().includes(q) || (n.content_text || '').toLowerCase().includes(q))
  }
  if (selectedTag.value) {
    result = result.filter(n => n.tags?.some(t => t.id === selectedTag.value))
  }
  if (activeFilter.value === 'private') result = result.filter(n => n.visibility === 'private')
  if (activeFilter.value === 'templates') result = result.filter(n => n.is_template)
  return result
})

const setFilter = (filter) => { activeFilter.value = filter }
const filterNotes = () => { /* le computed se met à jour automatiquement */ }
let searchTimer = null
const debouncedSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(filterNotes, 300)
}

// Ouvrir / Fermer modals
const openCreateModal = () => {
  editingNote.value = null
  noteForm.value = { title: '', content_text: '', visibility: 'private', tag_ids: [], is_template: false, parent: null }
  document.getElementById('noteModal').showModal()
}

const openNote = (note) => {
  editingNote.value = note
  noteForm.value = {
    title: note.title,
    content_text: note.content_text,
    visibility: note.visibility,
    tag_ids: note.tags?.map(t => t.id) || [],
    is_template: note.is_template,
    parent: note.parent
  }
  document.getElementById('noteModal').showModal()
}

const closeModal = () => {
  document.getElementById('noteModal').close()
}

// Sauvegarder
const saveNote = async () => {
  if (!noteForm.value.title.trim()) return
  saving.value = true
  try {
    const payload = { ...noteForm.value, content_json: {} }
    if (editingNote.value) {
      await $fetch(`${API_BASE}/notes/${editingNote.value.id}/`, { method: 'PUT', body: payload })
    } else {
      await $fetch(`${API_BASE}/notes/`, { method: 'POST', body: payload })
    }
    closeModal()
    await loadData()
  } catch (e) {
    console.error('Erreur sauvegarde:', e)
  } finally {
    saving.value = false
  }
}

// Supprimer
const deleteNote = async (id) => {
  if (!confirm('Supprimer cette note ?')) return
  try {
    await $fetch(`${API_BASE}/notes/${id}/`, { method: 'DELETE' })
    await loadData()
  } catch (e) {
    console.error('Erreur suppression:', e)
  }
}

// Utilitaires
const formatDate = (date) => {
  if (!date) return ''
  return new Date(date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
}
const visibilityBadge = (v) => ({ 'badge-ghost': v === 'private', 'badge-info': v === 'team', 'badge-success': v === 'all' })
const visibilityIcon = (v) => ({ 'fas fa-lock': v === 'private', 'fas fa-users': v === 'team', 'fas fa-globe': v === 'all' }[v])
const visibilityLabel = (v) => ({ private: 'Privée', team: 'Équipe', all: 'Tous' }[v] || v)

// Init
onMounted(loadData)

definePageMeta({ title: 'Notes - Hydria' })
useHead({ title: 'Notes - Hydria' })
</script>

<style scoped>
.card { transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out; }
.line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
</style>
