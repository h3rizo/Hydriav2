export const useTheme = () => {
  // État global pour le thème
  const theme = useState<string>('theme', () => 'hydriaDark')
  
  // Fonction pour appliquer le thème au DOM
  const applyTheme = (themeName: string) => {
    if (process.client) {
      document.documentElement.setAttribute('data-theme', themeName)
    }
  }
  
  // Fonction pour initialiser le thème depuis localStorage
  const initTheme = () => {
    if (process.client) {
      const savedTheme = localStorage.getItem('hydria-theme') || 'hydriaDark'
      theme.value = savedTheme
      applyTheme(savedTheme)
    }
  }
  
  // Fonction pour basculer entre les thèmes
  const toggleTheme = () => {
    const newTheme = theme.value === 'hydriaDark' ? 'winter' : 'hydriaDark'
    theme.value = newTheme
    
    if (process.client) {
      localStorage.setItem('hydria-theme', newTheme)
      applyTheme(newTheme)
    }
  }
  
  // Fonction pour définir un thème spécifique
  const setTheme = (themeName: string) => {
    theme.value = themeName
    
    if (process.client) {
      localStorage.setItem('hydria-theme', themeName)
      applyTheme(themeName)
    }
  }
  
  // Computed pour vérifier si c'est le thème sombre
  const isDark = computed(() => theme.value === 'hydriaDark')
  
  // Computed pour vérifier si c'est le thème clair
  const isLight = computed(() => theme.value === 'winter')
  
  // Computed pour le nom du thème actuel affiché
  const themeDisplayName = computed(() => {
    return theme.value === 'hydriaDark' ? 'Sombre' : 'Clair'
  })
  
  // Initialiser le thème au montage côté client
  onMounted(() => {
    initTheme()
  })
  
  // Watcher pour maintenir la synchronisation
  watchEffect(() => {
    if (process.client) {
      applyTheme(theme.value)
    }
  })
  
  return {
    theme: readonly(theme),
    toggleTheme,
    setTheme,
    initTheme,
    isDark,
    isLight,
    themeDisplayName
  }
}