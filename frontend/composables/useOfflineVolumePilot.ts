export interface VolumeCommuneRow {
  commune_id: string | null
  commune: string
  district: string
  region: string
  nb_ouvrages: number
  nb_releves: number
  total_releves: number
  total_diamex: number
  ecart: number
  taux: number
}

interface VolumeApiResponse {
  success: boolean
  communes: VolumeCommuneRow[]
  total: number
}

export const useOfflineVolumePilot = () => {
  const api = useApi()
  const offlineStore = useOfflineStore()

  const loading = ref(false)
  const error = ref<string | null>(null)
  const fromCache = ref(false)
  const lastSync = ref<number | null>(null)
  const rows = ref<VolumeCommuneRow[]>([])

  const endpoint = '/accounting/dashboard-paiements-volume/api/communes/'

  const getCacheKey = (annee: number) => {
    const params = new URLSearchParams({ annee: String(annee) }).toString()
    return `${endpoint}?${params}`
  }

  const normalizeRows = (payload: VolumeApiResponse | null | undefined): VolumeCommuneRow[] => {
    if (!payload?.success || !Array.isArray(payload.communes)) return []
    return payload.communes
  }

  const fetchCommuneSummary = async (annee: number, forceNetwork = false) => {
    loading.value = true
    error.value = null
    const cacheKey = getCacheKey(annee)

    if (!forceNetwork) {
      const cached = await offlineStore.getCachedData(cacheKey) as VolumeApiResponse | null
      const cachedRows = normalizeRows(cached)
      if (cachedRows.length > 0) {
        rows.value = cachedRows
        fromCache.value = true
      }
    }

    try {
      const data = await api.get(endpoint, { annee }) as VolumeApiResponse
      const networkRows = normalizeRows(data)
      if (networkRows.length > 0 || data?.success) {
        rows.value = networkRows
        fromCache.value = false
        lastSync.value = Date.now()
      }
    } catch (e: any) {
      if (rows.value.length === 0) {
        error.value = e?.message || 'Erreur de chargement'
      }
    } finally {
      loading.value = false
    }
  }

  const totals = computed(() => {
    const totalReleves = rows.value.reduce((sum, row) => sum + (row.total_releves || 0), 0)
    const totalDiamex = rows.value.reduce((sum, row) => sum + (row.total_diamex || 0), 0)
    const totalNbReleves = rows.value.reduce((sum, row) => sum + (row.nb_releves || 0), 0)
    const globalRate = totalReleves > 0 ? Math.round((totalDiamex / totalReleves) * 100) : 0

    return {
      totalCommunes: rows.value.length,
      totalNbReleves,
      totalReleves,
      totalDiamex,
      globalRate,
      totalEcart: totalReleves - totalDiamex
    }
  })

  return {
    loading,
    error,
    fromCache,
    lastSync,
    rows,
    totals,
    fetchCommuneSummary
  }
}

