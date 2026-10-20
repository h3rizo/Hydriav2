/**
 * Composable pour gérer les évaluations d'employés
 * Gère le CRUD des évaluations, la notation des tâches et l'historique
 */

export const useEvaluations = () => {
  const evaluations = ref<any[]>([])
  const currentEvaluation = ref<any | null>(null)
  const employes = ref<any[]>([])
  const postes = ref<any[]>([])
  const historiqueEvaluations = ref<any[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * Charge la liste des évaluations avec filtres optionnels
   * @param filters - Filtres (employe_id, statut, annee)
   */
  const loadEvaluations = async (filters: {
    employe_id?: string
    statut?: string
    annee?: number
  } = {}) => {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      if (filters.employe_id) params.append('employe_id', filters.employe_id)
      if (filters.statut) params.append('statut', filters.statut)
      if (filters.annee) params.append('annee', filters.annee.toString())

      const { data, error: apiError } = await useApi(`/api/evaluations/list/?${params}`, {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        evaluations.value = []
        return
      }

      if (data.evaluations) {
        evaluations.value = data.evaluations
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors du chargement des évaluations'
      evaluations.value = []
      console.error('Erreur loadEvaluations:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Charge les détails d'une évaluation
   * @param evaluationId - UUID de l'évaluation
   */
  const loadEvaluation = async (evaluationId: string) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/evaluations/${evaluationId}/`, {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        currentEvaluation.value = null
        return
      }

      if (data.evaluation) {
        currentEvaluation.value = data.evaluation
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors du chargement de l\'évaluation'
      currentEvaluation.value = null
      console.error('Erreur loadEvaluation:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Charge la liste des employés actifs
   */
  const loadEmployes = async () => {
    try {
      const { data, error: apiError } = await useApi('/api/employes/', {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        return
      }

      if (data.employes) {
        employes.value = data.employes
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors du chargement des employés'
      console.error('Erreur loadEmployes:', e)
    }
  }

  /**
   * Charge la liste des postes
   */
  const loadPostes = async () => {
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
    }
  }

  /**
   * Crée une nouvelle évaluation
   * @param evaluationData - Données de l'évaluation
   */
  const createEvaluation = async (evaluationData: {
    employe_id: string
    evaluateur_id: string
    periode_debut: string
    periode_fin: string
  }) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi('/api/evaluations/create/', {
        method: 'POST',
        body: evaluationData
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        return { success: true, evaluation_id: data.evaluation_id }
      } else {
        error.value = data.error || 'Erreur lors de la création'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la création'
      console.error('Erreur createEvaluation:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * Met à jour la note d'une tâche
   * @param evaluationId - UUID de l'évaluation
   * @param detailId - UUID du détail (ligne de notation)
   * @param note - Note (0, 1 ou 2)
   */
  const updateNote = async (evaluationId: string, detailId: string, note: number) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/evaluations/${evaluationId}/update-note/`, {
        method: 'POST',
        body: {
          detail_id: detailId,
          note: note
        }
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        // Recharger l'évaluation pour mettre à jour les scores
        await loadEvaluation(evaluationId)
        return { success: true }
      } else {
        error.value = data.error || 'Erreur lors de la mise à jour'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la mise à jour'
      console.error('Erreur updateNote:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * Met à jour les remarques d'une évaluation
   * @param evaluationId - UUID de l'évaluation
   * @param remarques - Texte des remarques
   */
  const updateRemarques = async (evaluationId: string, remarques: string) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/evaluations/${evaluationId}/update-remarques/`, {
        method: 'POST',
        body: { remarques }
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        // Mettre à jour les remarques localement
        if (currentEvaluation.value) {
          currentEvaluation.value.remarques = remarques
        }
        return { success: true }
      } else {
        error.value = data.error || 'Erreur lors de la mise à jour'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la mise à jour'
      console.error('Erreur updateRemarques:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * Termine une évaluation (changement statut brouillon → terminée)
   * @param evaluationId - UUID de l'évaluation
   */
  const terminerEvaluation = async (evaluationId: string) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/evaluations/${evaluationId}/terminer/`, {
        method: 'POST'
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError }
      }

      if (data.success) {
        // Recharger l'évaluation pour mettre à jour le statut
        await loadEvaluation(evaluationId)
        return { success: true }
      } else {
        error.value = data.error || 'Erreur lors de la finalisation'
        return { success: false, error: data.error }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la finalisation'
      console.error('Erreur terminerEvaluation:', e)
      return { success: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * Charge l'historique des évaluations d'un employé
   * @param employeId - UUID de l'employé
   */
  const loadHistorique = async (employeId: string) => {
    try {
      const { data, error: apiError } = await useApi(`/api/evaluations/historique/${employeId}/`, {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        historiqueEvaluations.value = []
        return
      }

      if (data.evaluations) {
        historiqueEvaluations.value = data.evaluations
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors du chargement de l\'historique'
      historiqueEvaluations.value = []
      console.error('Erreur loadHistorique:', e)
    }
  }

  /**
   * Charge les détails d'une ancienne évaluation depuis l'historique
   * @param evaluationId - UUID de l'évaluation
   */
  const loadHistoriqueEvaluation = async (evaluationId: string) => {
    loading.value = true
    error.value = null

    try {
      const { data, error: apiError } = await useApi(`/api/evaluations/${evaluationId}/historique/`, {
        method: 'GET'
      })

      if (apiError) {
        error.value = apiError
        return { success: false, error: apiError, evaluation: null }
      }

      if (data.success && data.evaluation) {
        return { success: true, evaluation: data.evaluation }
      } else {
        error.value = data.error || 'Erreur lors du chargement'
        return { success: false, error: data.error, evaluation: null }
      }
    } catch (e: any) {
      error.value = e.message || 'Erreur lors du chargement'
      console.error('Erreur loadHistoriqueEvaluation:', e)
      return { success: false, error: e.message, evaluation: null }
    } finally {
      loading.value = false
    }
  }

  return {
    // État
    evaluations,
    currentEvaluation,
    employes,
    postes,
    historiqueEvaluations,
    loading,
    error,

    // Méthodes
    loadEvaluations,
    loadEvaluation,
    loadEmployes,
    loadPostes,
    createEvaluation,
    updateNote,
    updateRemarques,
    terminerEvaluation,
    loadHistorique,
    loadHistoriqueEvaluation
  }
}
