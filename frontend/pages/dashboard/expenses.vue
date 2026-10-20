<template>
  <div class="container mx-auto px-4 py-6 space-y-6">
    <div class="flex flex-col lg:flex-row justify-between gap-3 lg:items-center">
      <div>
        <h1 class="text-3xl font-bold text-base-content">
          <span :key="langKey">{{ getTranslation('dashboard.expenses') }}</span>
        </h1>
        <p class="text-base-content/70">
          <span :key="langKey">{{ currentLang === 'fr' ? 'Depenses de service (hors planningdetails)' : "Depenses de service ivelan'ny planningdetails" }}</span>
        </p>
      </div>
      <div class="flex gap-2">
        <button @click="loadData" class="btn btn-primary btn-sm" :disabled="loading">
          <i class="fas fa-sync-alt mr-2" :class="{ 'animate-spin': loading }"></i>
          <span>{{ currentLang === 'fr' ? 'Actualiser' : 'Havaozina' }}</span>
        </button>
        <button v-if="permissions.can_manage" @click="resetForm" type="button" class="btn btn-outline btn-sm" :disabled="saving">
          <i class="fas fa-plus mr-2"></i>
          <span>{{ currentLang === 'fr' ? 'Nouvelle depense' : 'Depense vaovao' }}</span>
        </button>
      </div>
    </div>

    <div v-if="permissions.can_manage" class="dashboard-card">
      <h2 class="text-xl font-semibold mb-4">
        <span :key="langKey">{{ currentLang === 'fr' ? 'Saisie d une facture' : 'Fampidirana faktiora' }}</span>
      </h2>

      <form @submit.prevent="saveExpense" class="grid gap-4">
        <div class="grid gap-4 md:grid-cols-2">
          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Date *' : 'Daty *' }}</span>
            </label>
            <input v-model="form.date_facture" type="date" class="input input-bordered" required />
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Fournisseur *' : 'Mpanome *' }}</span>
            </label>
            <select v-model="form.fournisseur_id" class="select select-bordered" required>
              <option value="">{{ currentLang === 'fr' ? 'Selectionner' : 'Safidio' }}</option>
              <option v-for="f in fournisseurs" :key="f.id" :value="f.id">
                {{ f.nom_fournisseur }}
              </option>
            </select>
          </div>

          <div class="form-control md:col-span-2">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Designation ou motif *' : 'Fanoritra / antony *' }}</span>
            </label>
            <textarea v-model="form.designation" class="textarea textarea-bordered h-24" required></textarea>
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Unite *' : 'Unite *' }}</span>
            </label>
            <input v-model="form.unite" class="input input-bordered" required />
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Prix unitaire (Ar) *' : 'Vidiny isaky ny unite (Ar) *' }}</span>
            </label>
            <input v-model.number="form.prix_unitaire" type="number" min="0.01" step="0.01" class="input input-bordered" required />
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Montant *' : 'Habetsahana *' }}</span>
            </label>
            <input v-model.number="form.montant" type="number" min="0.01" step="0.01" class="input input-bordered" required />
          </div>

          <div class="form-control">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Total' : 'Total' }}</span>
            </label>
            <input :value="formatCurrency(calculatedTotal)" class="input input-bordered" readonly />
          </div>

          <div class="form-control md:col-span-2">
            <label class="label">
              <span class="label-text">{{ currentLang === 'fr' ? 'Total en toute lettre' : 'Total amin ny litera' }}</span>
            </label>
            <textarea v-model="form.total_lettres" class="textarea textarea-bordered h-20" readonly></textarea>
          </div>
        </div>

        <div class="flex justify-end gap-3">
          <button type="button" class="btn btn-ghost" @click="resetForm" :disabled="saving">
            {{ currentLang === 'fr' ? 'Annuler' : 'Foanana' }}
          </button>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            <i class="fas fa-save mr-2" :class="{ 'animate-pulse': saving }"></i>
            <span>{{ form.id ? (currentLang === 'fr' ? 'Modifier' : 'Hanova') : (currentLang === 'fr' ? 'Enregistrer' : 'Hametraka') }}</span>
          </button>
        </div>
      </form>
    </div>
    <div v-else class="dashboard-card">
      <h2 class="text-xl font-semibold mb-2">
        <span :key="langKey">{{ currentLang === 'fr' ? 'Saisie d une facture' : 'Fampidirana faktiora' }}</span>
      </h2>
      <p class="text-base-content/70">
        {{ currentLang === 'fr' ? 'Mode lecture seule: creation et modification non autorisees.' : 'Famakiana fotsiny: tsy mahazo mamorona na manova.' }}
      </p>
    </div>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <div class="stat-card">
        <div class="text-xs text-base-content/75">{{ currentLang === 'fr' ? 'Nombre' : 'Isany' }}</div>
        <div class="text-2xl font-bold">{{ stats.total_records || 0 }}</div>
      </div>
      <div class="stat-card success">
        <div class="text-xs text-success-content/75">{{ currentLang === 'fr' ? 'Total' : 'Total' }}</div>
        <div class="text-2xl font-bold">{{ formatCurrency(stats.total_montant || 0) }}</div>
      </div>
      <div class="stat-card warning">
        <div class="text-xs text-warning-content/75">{{ currentLang === 'fr' ? 'Brouillon' : 'Tabilao' }}</div>
        <div class="text-2xl font-bold">{{ formatCurrency(stats.total_brouillons || 0) }}</div>
      </div>
      <div class="stat-card error">
        <div class="text-xs text-error-content/75">{{ currentLang === 'fr' ? 'Attente 2e signature' : 'Miandry fanamafisana' }}</div>
        <div class="text-2xl font-bold">{{ formatCurrency(stats.total_en_attente || 0) }}</div>
      </div>
    </div>

    <div class="dashboard-card">
      <h3 class="text-lg font-semibold mb-4">
        <span :key="langKey">{{ currentLang === 'fr' ? 'Filtres' : 'Sivanana' }}</span>
      </h3>
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div class="form-control xl:col-span-2">
          <label class="label">
            <span class="label-text">{{ currentLang === 'fr' ? 'Recherche' : 'Karazany' }}</span>
          </label>
          <input v-model="filters.search" type="text" class="input input-bordered" :placeholder="currentLang === 'fr' ? 'Designation ou fournisseur' : 'Fanoritra na mpanome'" />
        </div>
        <div class="form-control">
          <label class="label">
            <span class="label-text">{{ currentLang === 'fr' ? 'Statut' : 'Sata' }}</span>
          </label>
          <select v-model="filters.statut" class="select select-bordered">
            <option value="">{{ currentLang === 'fr' ? 'Tous' : 'Izy rehetra' }}</option>
            <option value="brouillon">{{ currentLang === 'fr' ? 'Brouillon' : 'Tabilao' }}</option>
            <option value="attente_signature">{{ currentLang === 'fr' ? 'Attente 2e signature' : 'Miandry fanindroany' }}</option>
            <option value="valide">{{ currentLang === 'fr' ? 'Valide' : 'Efa voamarina' }}</option>
          </select>
        </div>
        <div class="form-control">
          <label class="label">
            <span class="label-text">{{ currentLang === 'fr' ? 'Fournisseur' : 'Mpanome' }}</span>
          </label>
          <select v-model="filters.fournisseur_id" class="select select-bordered">
            <option value="">{{ currentLang === 'fr' ? 'Tous' : 'Izy rehetra' }}</option>
            <option v-for="f in fournisseurs" :key="f.id" :value="f.id">{{ f.nom_fournisseur }}</option>
          </select>
        </div>
        <div class="form-control">
          <label class="label">
            <span class="label-text">{{ currentLang === 'fr' ? 'Du' : 'Avy amin' }}</span>
          </label>
          <input v-model="filters.from_date" type="date" class="input input-bordered" />
        </div>
        <div class="form-control">
          <label class="label">
            <span class="label-text">{{ currentLang === 'fr' ? 'Au' : 'Hatramin' }}</span>
          </label>
          <input v-model="filters.to_date" type="date" class="input input-bordered" />
        </div>
        <div class="form-control xl:col-span-5 flex items-end gap-2">
          <button class="btn btn-primary" @click="applyFilters">
            <i class="fas fa-filter mr-2"></i>
            <span>{{ currentLang === 'fr' ? 'Filtrer' : 'Hanisy' }}</span>
          </button>
          <button type="button" class="btn btn-ghost" @click="resetFilters">
            <i class="fas fa-times mr-2"></i>
            <span>{{ currentLang === 'fr' ? 'RAZ' : 'Hamafa' }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="dashboard-card">
      <div class="overflow-x-auto">
        <table class="table w-full">
          <thead>
            <tr class="bg-base-200">
              <th>{{ currentLang === 'fr' ? 'Date' : 'Daty' }}</th>
              <th>{{ currentLang === 'fr' ? 'Fournisseur' : 'Mpanome' }}</th>
              <th>{{ currentLang === 'fr' ? 'Designation' : 'Fanoritra' }}</th>
              <th>{{ currentLang === 'fr' ? 'Unite' : 'Unite' }}</th>
              <th>{{ currentLang === 'fr' ? 'Prix unitaire' : 'Vidiny isaky ny unite' }}</th>
              <th>{{ currentLang === 'fr' ? 'Montant' : 'Habetsahana' }}</th>
              <th>{{ currentLang === 'fr' ? 'Total' : 'Total' }}</th>
              <th>{{ currentLang === 'fr' ? 'Total en toutes lettres' : 'Total litera' }}</th>
              <th>{{ currentLang === 'fr' ? 'Statut' : 'Sata' }}</th>
              <th>{{ currentLang === 'fr' ? 'Signatures' : 'Sonia' }}</th>
              <th>{{ currentLang === 'fr' ? 'Actions' : 'Asa' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="expense in depenses" :key="expense.id">
              <td>{{ formatDate(expense.date_facture) }}</td>
              <td>{{ expense.fournisseur_nom }}</td>
              <td>{{ expense.designation }}</td>
              <td>{{ expense.unite }}</td>
              <td>{{ formatCurrency(expense.prix_unitaire) }}</td>
              <td>{{ formatCurrency(expense.montant) }}</td>
              <td>{{ formatCurrency(expense.total) }}</td>
              <td class="max-w-56 truncate">{{ expense.total_lettres || '-' }}</td>
              <td>
                <span :class="statusClass(expense.statut)">{{ statusLabel(expense.statut) }}</span>
              </td>
              <td>
                <div class="text-xs">{{ expense.signataire_1 || '-' }} <template v-if="expense.date_signature_1">({{ expense.date_signature_1 }})</template></div>
                <div class="text-xs">{{ expense.signataire_2 || '-' }} <template v-if="expense.date_signature_2">({{ expense.date_signature_2 }})</template></div>
              </td>
              <td>
                <div v-if="hasActions(expense)" class="dropdown dropdown-end">
                  <button tabindex="0" class="btn btn-ghost btn-xs">
                    <i class="fas fa-ellipsis-v"></i>
                  </button>
                  <ul tabindex="0" class="dropdown-content menu bg-base-100 rounded-box w-52 p-2 shadow">
                    <li v-if="expense.can_manage">
                      <a @click.prevent="editExpense(expense)">
                        <i class="fas fa-pen mr-2"></i>
                        <span>{{ currentLang === 'fr' ? 'Modifier' : 'Ovay' }}</span>
                      </a>
                    </li>
                    <li v-if="expense.can_manage">
                      <a class="text-error" @click.prevent="deleteExpense(expense)">
                        <i class="fas fa-trash mr-2"></i>
                        <span>{{ currentLang === 'fr' ? 'Supprimer' : 'Fafana' }}</span>
                      </a>
                    </li>
                    <li v-if="expense.statut === 'brouillon' && expense.can_sign_1">
                      <a @click.prevent="signExpense(expense, 1)">
                        <i class="fas fa-signature mr-2"></i>
                        <span>{{ currentLang === 'fr' ? 'Signature 1' : 'Sonia 1' }}</span>
                      </a>
                    </li>
                    <li v-if="expense.statut === 'attente_signature' && expense.can_sign_2">
                      <a @click.prevent="signExpense(expense, 2)">
                        <i class="fas fa-signature mr-2"></i>
                        <span>{{ currentLang === 'fr' ? 'Signature 2' : 'Sonia 2' }}</span>
                      </a>
                    </li>
                  </ul>
                </div>
                <span v-else>-</span>
              </td>
            </tr>
            <tr v-if="depenses.length === 0">
              <td colspan="11" class="text-center py-8 text-base-content/60">
                {{ currentLang === 'fr' ? 'Aucune depense trouvee' : 'Tsy misy lafiny hita' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex justify-center gap-2 pt-4" v-if="pagination.total_pages > 1">
        <button class="btn btn-sm" :disabled="!pagination.has_previous" @click="loadPage(pagination.previous_page)">
          {{ currentLang === 'fr' ? 'Precedent' : 'Aloha' }}
        </button>
        <span class="badge">{{ pagination.page }} / {{ pagination.total_pages }}</span>
        <button class="btn btn-sm" :disabled="!pagination.has_next" @click="loadPage(pagination.next_page)">
          {{ currentLang === 'fr' ? 'Suivant' : 'Manaraka' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="fixed inset-0 bg-black/20 z-50 flex items-center justify-center">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>
  </div>
</template>

<script setup>
const { currentLang, langKey, getTranslation } = useLanguage()
const { get, post, delete: apiDelete } = useApi()

const loading = ref(false)
const saving = ref(false)

const fournisseurs = ref([])
const depenses = ref([])
const totalLettresTimeout = ref(null)
const defaultPermissions = () => ({
  can_manage: false,
  can_sign_1: false,
  can_sign_2: false
})
const permissions = ref(defaultPermissions())

const pagination = ref({
  page: 1,
  per_page: 50,
  total_items: 0,
  total_pages: 0,
  has_previous: false,
  has_next: false,
  previous_page: null,
  next_page: null
})

const stats = ref({
  total_records: 0,
  total_montant: 0,
  total_brouillons: 0,
  total_en_attente: 0,
  total_valides: 0
})

const filters = reactive({
  search: '',
  statut: '',
  fournisseur_id: '',
  from_date: '',
  to_date: ''
})

const form = reactive({
  id: '',
  date_facture: new Date().toISOString().slice(0, 10),
  fournisseur_id: '',
  designation: '',
  unite: '',
  prix_unitaire: null,
  montant: null,
  total_lettres: ''
})

const statusMap = {
  brouillon: { fr: 'Brouillon', mg: 'Tabilao', className: 'badge-warning' },
  attente_signature: { fr: 'Attente 2e signature', mg: 'Miandry fanamafisana', className: 'badge-info' },
  valide: { fr: 'Valide', mg: 'Efa voamarina', className: 'badge-success' }
}

const cleanQuery = (params) => {
  const q = {}
  Object.entries(params).forEach(([key, value]) => {
    if (value === '' || value === null || value === undefined) {
      return
    }
    q[key] = value
  })
  return q
}

const calculatedTotal = computed(() => {
  const unit = Number(form.prix_unitaire || 0)
  const qty = Number(form.montant || 0)
  if (!Number.isFinite(unit) || !Number.isFinite(qty)) {
    return 0
  }
  return Math.round(unit * qty * 100) / 100
})

const formatCurrency = (amount) => {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'MGA',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number(amount || 0))
}

const formatDate = (value) => {
  if (!value) {
    return '-'
  }
  return new Intl.DateTimeFormat('fr-FR').format(new Date(value))
}

const statusLabel = (statut) => {
  const statusConfig = statusMap[statut] || statusMap.brouillon
  return currentLang.value === 'fr' ? statusConfig.fr : statusConfig.mg
}

const statusClass = (statut) => {
  const statusConfig = statusMap[statut] || statusMap.brouillon
  return `badge ${statusConfig.className} badge-sm`
}

const updateTotalLettres = async () => {
  const total = calculatedTotal.value
  if (total <= 0) {
    form.total_lettres = ''
    return
  }

  try {
    const response = await post('/facturation/depenses-services/total-lettres/', { total })
    form.total_lettres = response?.success ? response.total_lettres : ''
  } catch (error) {
    console.error('Impossible de calculer le total en lettres', error)
    form.total_lettres = ''
  }
}

watch(() => [form.prix_unitaire, form.montant], () => {
  if (totalLettresTimeout.value) {
    clearTimeout(totalLettresTimeout.value)
  }
  totalLettresTimeout.value = setTimeout(updateTotalLettres, 350)
}, { flush: 'post' })

const loadFournisseurs = async () => {
  try {
    const response = await get('/facturation/fournisseurs/', cleanQuery({
      format: 'json',
      per_page: 300,
      sort: 'nom_asc'
    }))
    fournisseurs.value = response?.fournisseurs || []
  } catch (error) {
    console.error('Erreur fournisseurs', error)
    fournisseurs.value = []
  }
}

const loadDepenses = async (page = 1) => {
  const query = cleanQuery({
    page,
    per_page: pagination.value.per_page,
    search: filters.search,
    statut: filters.statut,
    fournisseur_id: filters.fournisseur_id,
    from_date: filters.from_date,
    to_date: filters.to_date
  })

  const response = await get('/facturation/depenses-services/list/', query)
  if (response?.success) {
    depenses.value = response.depenses || []
    permissions.value = response.permissions || defaultPermissions()
    pagination.value = response.pagination || pagination.value
    stats.value = response.stats || stats.value
  } else {
    depenses.value = []
    permissions.value = defaultPermissions()
    stats.value = {
      total_records: 0,
      total_montant: 0,
      total_brouillons: 0,
      total_en_attente: 0,
      total_valides: 0
    }
    pagination.value = {
      page: 1,
      per_page: pagination.value.per_page,
      total_items: 0,
      total_pages: 0,
      has_previous: false,
      has_next: false,
      previous_page: null,
      next_page: null
    }
  }
}

const loadData = async () => {
  loading.value = true
  try {
    await Promise.all([loadFournisseurs(), loadDepenses(1)])
  } finally {
    loading.value = false
  }
}

const loadPage = async (page) => {
  if (!page) return
  loading.value = true
  try {
    await loadDepenses(page)
  } finally {
    loading.value = false
  }
}

const applyFilters = () => {
  loadDepenses(1)
}

const resetFilters = () => {
  filters.search = ''
  filters.statut = ''
  filters.fournisseur_id = ''
  filters.from_date = ''
  filters.to_date = ''
  loadDepenses(1)
}

const resetForm = () => {
  form.id = ''
  form.date_facture = new Date().toISOString().slice(0, 10)
  form.fournisseur_id = ''
  form.designation = ''
  form.unite = ''
  form.prix_unitaire = null
  form.montant = null
  form.total_lettres = ''
}

const saveExpense = async () => {
  if (saving.value) return

  if (!form.date_facture || !form.fournisseur_id || !form.designation || !form.unite || !(form.prix_unitaire > 0) || !(form.montant > 0)) {
    alert(currentLang.value === 'fr' ? 'Veuillez renseigner tous les champs obligatoires' : 'Fenoy ireo saha rehetra')
    return
  }

  saving.value = true
  try {
    const payload = {
      date_facture: form.date_facture,
      fournisseur_id: form.fournisseur_id,
      designation: form.designation.trim(),
      unite: form.unite.trim(),
      prix_unitaire: form.prix_unitaire,
      montant: form.montant
    }

    const endpoint = form.id
      ? `/facturation/depenses-services/${form.id}/update/`
      : '/facturation/depenses-services/create/'

    const response = await post(endpoint, payload)
    if (!response?.success) {
      alert(response?.error || (currentLang.value === 'fr' ? 'Enregistrement impossible' : 'Tsy afaka voatahiry'))
      return
    }

    resetForm()
    await loadData()
  } catch (error) {
    console.error('Erreur save', error)
    alert(currentLang.value === 'fr' ? 'Erreur de sauvegarde' : 'Nisy tsy fetezana tamin ny fitahirizana')
  } finally {
    saving.value = false
  }
}

const editExpense = (expense) => {
  if (expense.statut === 'valide') {
    alert(currentLang.value === 'fr' ? 'La depense valide ne peut pas etre modifiee' : 'Ny fandani voamarina tsy azo ovaina')
    return
  }

  form.id = expense.id
  form.date_facture = expense.date_facture
  form.fournisseur_id = expense.fournisseur_id
  form.designation = expense.designation
  form.unite = expense.unite
  form.prix_unitaire = Number(expense.prix_unitaire || 0)
  form.montant = Number(expense.montant || 0)
  form.total_lettres = expense.total_lettres || ''
}

const deleteExpense = async (expense) => {
  if (!confirm(currentLang.value === 'fr' ? 'Supprimer cette depense ?' : 'Hamafa ity fandani ity ?')) {
    return
  }
  const response = await apiDelete(`/facturation/depenses-services/${expense.id}/delete/`)
  if (response?.success) {
    await loadDepenses(pagination.value.page)
  } else {
    alert(response?.error || (currentLang.value === 'fr' ? 'Suppression impossible' : 'Tsy afaka fafana'))
  }
}

const hasActions = (expense) => {
  return Boolean(
    expense.can_manage
    || (expense.statut === 'brouillon' && expense.can_sign_1)
    || (expense.statut === 'attente_signature' && expense.can_sign_2)
  )
}

const signExpense = async (expense, signatureIndex) => {
  const defaultName = currentLang.value === 'fr' ? 'Nom du signataire' : 'Anaran\'ny sonia'
  const name = window.prompt(`${currentLang.value === 'fr' ? 'Nom du signataire' : 'Anaran\'ny sonia'} ${signatureIndex}`, defaultName)
  if (!name) return

  const response = await post(`/facturation/depenses-services/${expense.id}/signer/`, {
    signature_index: signatureIndex,
    signataire: name.trim(),
    date_signature: new Date().toISOString().slice(0, 10)
  })

  if (response?.success) {
    await loadDepenses(pagination.value.page)
  } else {
    alert(response?.error || (currentLang.value === 'fr' ? 'Signature impossible' : 'Tsy afaka nosoniavina'))
  }
}

onMounted(() => {
  loading.value = true
  loadData().finally(() => {
    loading.value = false
  })
})

useHead({
  title: 'Workflow depenses services - Hydria'
})
</script>

<style scoped>
.dashboard-card {
  @apply bg-base-100 rounded-lg shadow-md p-6 border border-base-300;
}

.stat-card {
  @apply bg-primary text-primary-content rounded-lg p-4 shadow;
}

.stat-card.success {
  @apply bg-success text-success-content;
}

.stat-card.warning {
  @apply bg-warning text-warning-content;
}

.stat-card.error {
  @apply bg-error text-error-content;
}
</style>
