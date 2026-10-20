export const useApi = () => {
  const config = useRuntimeConfig()
  const offlineStore = useOfflineStore()

  const resolveApiUrl = (endpoint: string): string => {
    if (/^https?:\/\//i.test(endpoint)) {
      return endpoint
    }

    const configuredBase = (config.public.apiBaseUrl || '').trim().replace(/\/$/, '')

    // For same-app routes, keep requests on the current origin so subdomain moves
    // do not break auth cookies or trigger CORS issues.
    if (endpoint.startsWith('/')) {
      if (process.client && typeof window !== 'undefined') {
        return `${window.location.origin}${endpoint}`
      }
      return `${configuredBase}${endpoint}`
    }

    return configuredBase ? `${configuredBase}/${endpoint}` : endpoint
  }

  /**
   * Récupère le token CSRF depuis les cookies Django
   */
  const getCSRFToken = (): string | null => {
    if (process.server) return null

    const name = 'csrftoken'
    const cookies = document.cookie.split(';')

    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim()
      if (cookie.startsWith(name + '=')) {
        return cookie.substring(name.length + 1)
      }
    }
    return null
  }

  // Fonction générique pour les appels API avec support hors ligne
  const apiCall = async (
    endpoint: string,
    options: {
      method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
      body?: any
      query?: Record<string, any>
      headers?: Record<string, string>
      offline?: boolean // Si true, sauvegarde hors ligne si pas de connexion
    } = {}
  ) => {
    const {
      method = 'GET',
      body,
      query,
      headers = {},
      offline = false
    } = options

    const url = resolveApiUrl(endpoint)
    const cacheKey = query
      ? `${endpoint}?${new URLSearchParams(
          Object.entries(query).reduce((acc, [key, value]) => {
            acc[key] = String(value ?? '')
            return acc
          }, {} as Record<string, string>)
        ).toString()}`
      : endpoint

    // Récupérer le token CSRF pour les requêtes modifiant les données
    const csrfToken = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) ? getCSRFToken() : null

    // Configuration de base pour la requête
    const requestConfig: any = {
      method,
      credentials: 'include', // Important pour Django sessions
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken && { 'X-CSRFToken': csrfToken }),
        ...headers
      }
    }

    if (body) {
      requestConfig.body = body
    }

    if (query) {
      requestConfig.query = query
    }

    try {
      // Tentative d'appel API
      const response = await $fetch(url, requestConfig)
      
      // Mettre en cache pour utilisation hors ligne (GET seulement)
      if (method === 'GET') {
        await offlineStore.cacheData(cacheKey, response)
      }
      
      return response

    } catch (error: any) {
      console.error(`Erreur API ${method} ${endpoint}:`, error)
      const isNetworkError = !error?.status && !error?.statusCode

      if (isNetworkError) {
        offlineStore.syncStatus.isOnline = false
      }

      // Si hors ligne et c'est une opération de modification, l'ajouter à la file d'attente
      if ((!offlineStore.isOnline || isNetworkError) && offline && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        await offlineStore.addPendingData(endpoint, method as any, body)
        
        // Retourner un objet indiquant que l'opération est en attente
        return {
          success: false,
          pending: true,
          message: 'Opération sauvegardée pour synchronisation ultérieure'
        }
      }

      // Si hors ligne et c'est un GET, essayer de récupérer depuis le cache
      if ((!offlineStore.isOnline || isNetworkError) && method === 'GET') {
        const cachedData = await offlineStore.getCachedData(cacheKey)
        if (cachedData) {
          console.log(`📱 Données récupérées du cache: ${endpoint}`)
          return cachedData
        }
      }

      // Propager l'erreur si aucune solution hors ligne
      throw error
    }
  }

  // Méthodes spécialisées
  const get = (endpoint: string, query?: Record<string, any>) => 
    apiCall(endpoint, { method: 'GET', query })

  const post = (endpoint: string, body: any, offline = true) => 
    apiCall(endpoint, { method: 'POST', body, offline })

  const put = (endpoint: string, body: any, offline = true) => 
    apiCall(endpoint, { method: 'PUT', body, offline })

  const patch = (endpoint: string, body: any, offline = true) => 
    apiCall(endpoint, { method: 'PATCH', body, offline })

  const del = (endpoint: string, offline = true) => 
    apiCall(endpoint, { method: 'DELETE', offline })

  return {
    apiCall,
    get,
    post,
    put,
    patch,
    delete: del
  }
}
