export default defineNuxtPlugin(() => {
  // Initialiser le thème avant que l'app soit montée
  if (process.client) {
    // Script d'initialisation immédiate (similaire à Django)
    const savedTheme = localStorage.getItem('hydria-theme') || 'hydriaDark'
    document.documentElement.setAttribute('data-theme', savedTheme)
    
    // Activer les transitions après le chargement initial
    setTimeout(() => {
      document.documentElement.classList.add('loaded')
    }, 100)
    
    // Prévenir le flash lors de la navigation
    window.addEventListener('beforeunload', () => {
      const currentTheme = localStorage.getItem('hydria-theme') || 'hydriaDark'
      document.documentElement.setAttribute('data-theme', currentTheme)
    })
  }
})