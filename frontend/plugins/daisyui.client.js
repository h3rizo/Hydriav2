export default defineNuxtPlugin((nuxtApp) => {
  const closeDropdowns = (except = null) => {
    document.querySelectorAll('.dropdown.dropdown-open').forEach((dropdown) => {
      if (dropdown !== except) dropdown.classList.remove('dropdown-open')
    })
  }

  const handleDocumentClick = (event) => {
    const target = event.target instanceof Element ? event.target : null
    if (!target) return

    const dropdown = target.closest('.dropdown')
    const trigger = target.closest('.dropdown [tabindex="0"]')

    if (trigger && dropdown) {
      closeDropdowns(dropdown)
      dropdown.classList.toggle('dropdown-open')
      return
    }

    if (target.closest('.dropdown-content a, .dropdown-content button') || !dropdown) {
      closeDropdowns()
    }
  }

  nuxtApp.hook('app:mounted', () => {
    document.addEventListener('click', handleDocumentClick)
  })

  nuxtApp.hook('app:beforeUnmount', () => {
    document.removeEventListener('click', handleDocumentClick)
  })
})
