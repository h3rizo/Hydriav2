// Composable pour l'authentification (mode offline)
export const useAuth = () => {
  const { mockUser, fetchUser } = useMockData()

  // État réactif de l'authentification
  const isAuthenticated = useState('auth.isAuthenticated', () => true) // Mode offline : toujours connecté
  const user = useState('auth.user', () => mockUser)
  const isLoading = useState('auth.isLoading', () => false)

  // Simulation de connexion
  const login = async (credentials) => {
    isLoading.value = true

    try {
      await new Promise(resolve => setTimeout(resolve, 1000)) // Simulation délai réseau

      // En mode offline, accepter admin/admin
      if (credentials.username === 'admin' && credentials.password === 'admin') {
        isAuthenticated.value = true
        user.value = mockUser

        // Sauvegarder en localStorage
        if (process.client) {
          localStorage.setItem('hydria-auth', JSON.stringify({
            isAuthenticated: true,
            user: mockUser
          }))
        }

        return { success: true }
      } else {
        throw new Error('Identifiants incorrects')
      }
    } catch (error) {
      return {
        success: false,
        error: error.message || 'Erreur de connexion'
      }
    } finally {
      isLoading.value = false
    }
  }

  // Simulation de déconnexion
  const logout = async () => {
    isLoading.value = true

    try {
      await new Promise(resolve => setTimeout(resolve, 500))

      isAuthenticated.value = false
      user.value = null

      // Nettoyer localStorage
      if (process.client) {
        localStorage.removeItem('hydria-auth')
      }

      // Rediriger vers login
      await navigateTo('/login')

    } catch (error) {
      console.error('Erreur lors de la déconnexion:', error)
    } finally {
      isLoading.value = false
    }
  }

  // Initialiser l'authentification depuis localStorage
  const initAuth = () => {
    if (process.client) {
      try {
        const saved = localStorage.getItem('hydria-auth')
        if (saved) {
          const authData = JSON.parse(saved)
          isAuthenticated.value = authData.isAuthenticated || false
          user.value = authData.user || null
        } else {
          // Mode offline : connecter automatiquement
          isAuthenticated.value = true
          user.value = mockUser
        }
      } catch (error) {
        console.error('Erreur initialisation auth:', error)
        // En cas d'erreur, connecter automatiquement en mode offline
        isAuthenticated.value = true
        user.value = mockUser
      }
    }
  }

  // Vérifier les permissions
  const hasPermission = (permission) => {
    if (!isAuthenticated.value || !user.value) return false

    // En mode offline, l'utilisateur admin a toutes les permissions
    if (user.value.is_staff) return true

    // Ajouter ici la logique de permissions spécifiques
    return false
  }

  // Rafraîchir les données utilisateur
  const refreshUser = async () => {
    if (!isAuthenticated.value) return

    try {
      isLoading.value = true
      const userData = await fetchUser()
      user.value = userData
    } catch (error) {
      console.error('Erreur rafraîchissement utilisateur:', error)
    } finally {
      isLoading.value = false
    }
  }

  return {
    isAuthenticated: readonly(isAuthenticated),
    user: readonly(user),
    isLoading: readonly(isLoading),
    login,
    logout,
    initAuth,
    hasPermission,
    refreshUser
  }
}