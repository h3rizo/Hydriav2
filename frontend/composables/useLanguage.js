import fr from '~/locales/fr.json'
import mg from '~/locales/mg.json'

const dictionaries = { fr, mg }

export const useLanguage = () => {
  const currentLang = useState('language', () => 'mg')
  const langKey = useState('langKey', () => 0)

  const getTranslation = (key, params = {}) => {
    const value = key.split('.').reduce((current, part) => current?.[part], dictionaries[currentLang.value])
    const fallback = key.split('.').reduce((current, part) => current?.[part], dictionaries.mg)
    const text = typeof value === 'string' ? value : typeof fallback === 'string' ? fallback : key

    return Object.entries(params).reduce(
      (translated, [name, replacement]) => translated.replaceAll(`{${name}}`, String(replacement)),
      text,
    )
  }

  const switchLanguage = (lang) => {
    if (!dictionaries[lang]) return
    currentLang.value = lang
    langKey.value += 1

    if (import.meta.client) {
      localStorage.setItem('hydria-locale', lang)
      document.documentElement.lang = lang === 'mg' ? 'mg' : 'fr'
    }
  }

  const initializeLanguage = () => {
    if (!import.meta.client) return
    const savedLang = localStorage.getItem('hydria-locale')
    switchLanguage(dictionaries[savedLang] ? savedLang : 'mg')
  }

  return {
    currentLang,
    langKey,
    translations: dictionaries,
    getTranslation,
    switchLanguage,
    initializeLanguage,
  }
}
