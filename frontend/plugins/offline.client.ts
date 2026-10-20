export default defineNuxtPlugin(async () => {
  // Initialiser le store hors ligne seulement côté client
  if (typeof window !== 'undefined') {
    const offlineStore = useOfflineStore()
    await offlineStore.initialize()

    // Notification de statut de connexion
    const toast = useNuxtApp().$toast
    
    let wasOffline = false

    // Surveiller les changements d'état de connexion
    const updateConnectionStatus = () => {
      const isOnline = navigator.onLine
      
      if (isOnline && wasOffline) {
        // Retour en ligne
        toast?.success('🌐 Connexion rétablie - Synchronisation en cours...', {
          timeout: 3000
        })
        wasOffline = false
      } else if (!isOnline && !wasOffline) {
        // Passage hors ligne
        toast?.warning('📵 Mode hors ligne - Vos modifications seront synchronisées lors du retour en ligne', {
          timeout: 5000
        })
        wasOffline = true
      }
    }

    // Écouter les changements de connexion
    window.addEventListener('online', updateConnectionStatus)
    window.addEventListener('offline', updateConnectionStatus)

    // Vérifier l'état initial
    if (!navigator.onLine) {
      wasOffline = true
    }

    // Affichage du statut de synchronisation
    const showSyncStatus = () => {
      if (offlineStore.pendingCount > 0) {
        const message = offlineStore.isSyncing 
          ? `🔄 Synchronisation en cours... (${offlineStore.pendingCount} éléments)`
          : `📝 ${offlineStore.pendingCount} modification${offlineStore.pendingCount > 1 ? 's' : ''} en attente de synchronisation`
        
        toast?.info(message, {
          timeout: 2000
        })
      }
    }

    // Afficher le statut périodiquement
    setInterval(showSyncStatus, 30000) // Toutes les 30 secondes

    // Affichage des erreurs de synchronisation
    watch(() => offlineStore.syncErrors, (errors) => {
      if (errors.length > 0) {
        const latestError = errors[errors.length - 1]
        toast?.error(`❌ Erreur de synchronisation: ${latestError}`, {
          timeout: 5000
        })
      }
    })

    // Installation automatique de la PWA
    const installPrompt = ref<any>(null)

    window.addEventListener('beforeinstallprompt', (e) => {
      // Empêcher l'affichage automatique du prompt
      e.preventDefault()
      installPrompt.value = e

      // Afficher une notification personnalisée
      setTimeout(() => {
        toast?.info('📱 Cette application peut être installée sur votre appareil pour un accès rapide', {
          timeout: 10000,
          onClick: () => {
            if (installPrompt.value) {
              installPrompt.value.prompt()
              installPrompt.value.userChoice.then((choiceResult: any) => {
                if (choiceResult.outcome === 'accepted') {
                  toast?.success('✅ Application installée avec succès!')
                }
                installPrompt.value = null
              })
            }
          }
        })
      }, 3000)
    })

    // Notification de mise à jour PWA disponible
    window.addEventListener('sw-update-found', () => {
      toast?.info('🔄 Mise à jour disponible - Rechargez la page pour l\'appliquer', {
        timeout: 10000,
        onClick: () => {
          window.location.reload()
        }
      })
    })

    // Gestionnaire pour le mode plein écran sur mobile
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                         (window.navigator as any).standalone ||
                         document.referrer.includes('android-app://')

    if (isStandalone) {
      // Ajouter une classe CSS pour le mode standalone
      document.body.classList.add('pwa-standalone')
    }

    // Prévention du défilement élastique sur iOS
    document.addEventListener('touchmove', (e) => {
      if (isStandalone) {
        e.preventDefault()
      }
    }, { passive: false })

    // Gestion de la barre de statut sur mobile
    const setStatusBarColor = (color: string) => {
      const metaThemeColor = document.querySelector('meta[name="theme-color"]')
      if (metaThemeColor) {
        metaThemeColor.setAttribute('content', color)
      }
    }

    // Adapter la couleur selon le thème
    const updateStatusBar = () => {
      const isDark = document.documentElement.classList.contains('dark')
      setStatusBarColor(isDark ? '#1e293b' : '#1e40af')
    }

    // Observer les changements de thème
    const observer = new MutationObserver(updateStatusBar)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class']
    })

    // Configuration initiale
    updateStatusBar()

    console.log('🚀 Plugin hors ligne initialisé')
  }
})