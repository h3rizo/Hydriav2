/**
 * Composable pour gérer les fiches de poste
 * Gère le chargement, la création, la modification et la suppression des tâches par poste
 */

export const useFichesPoste = () => {
  const fiches = ref<any[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const postes = ref<any[]>([])

  /**
   * Charge la liste des postes disponibles
   */
  const loadPostes = async () => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi('/api/postes/', {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        return
      }

      if (data.postes) {
        postes.value = data.postes
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors du chargement des postes'
      console.error('Erreur loadPostes:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Charge les fiches de poste pour un poste donné
   * @param posteId - UUID du poste
   */
  const loadFiches = async (posteId: string) => {
    if (!posteId) {
      fiches.value = []
      return
    }

    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/fiches-poste/${posteId}/`, {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        fiches.value = []
        return
      }

      if (data.success && data.fiches) {
        fiches.value = data.fiches
      } else {
        error.value = data.error || 'Erreur inconnue'
        fiches.value = []
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur de communication avec le serveur'
      fiches.value = []
      console.error('Erreur loadFiches:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Crée une nouvelle fiche de poste
   * @param ficheData - Données de la fiche (poste_id, tache, description, outils, ordre)
   */
  const createFiche = async (ficheData: {
    poste_id: string
    tache: string
    description: string
    outils?: string
    ordre?: number
  }) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi('/api/fiches-poste/create/', {
        method: 'POST',
        body: ficheData
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        // Recharger les fiches pour ce poste
        await loadFiches(ficheData.poste_id)
        return { success: true, message: data.message }
      } else {
        error.value = data.error || 'Erreur lors de la création'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la création'
      console.error('Erreur createFiche:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * Modifie une fiche de poste existante
   * @param ficheId - UUID de la fiche
   * @param ficheData - Données à modifier
   */
  const updateFiche = async (
    ficheId: string,
    ficheData: {
      poste_id: string
      tache: string
      description: string
      outils?: string
      ordre?: number
    }
  ) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/fiches-poste/${ficheId}/update/`, {
        method: 'POST',
        body: ficheData
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        // Recharger les fiches pour ce poste
        await loadFiches(ficheData.poste_id)
        return { success: true, message: data.message }
      } else {
        error.value = data.error || 'Erreur lors de la modification'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la modification'
      console.error('Erreur updateFiche:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * Supprime une fiche de poste
   * @param ficheId - UUID de la fiche
   * @param posteId - UUID du poste (pour recharger la liste après)
   */
  const deleteFiche = async (ficheId: string, posteId: string) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/fiches-poste/${ficheId}/delete/`, {
        method: 'POST'
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        // Recharger les fiches pour ce poste
        await loadFiches(posteId)
        return { success: true, message: data.message }
      } else {
        error.value = data.error || 'Erreur lors de la suppression'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la suppression'
      console.error('Erreur deleteFiche:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  return {
    // État
    fiches,
    postes,
    loading,
    error,

    // Méthodes
    loadPostes,
    loadFiches,
    createFiche,
    updateFiche,
    deleteFiche
  }
}
