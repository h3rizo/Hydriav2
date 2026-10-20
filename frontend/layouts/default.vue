<template>
  <div class="hydria-shell hydria-noise min-h-screen">
    <a href="#hydria-main" class="skip-link">{{ t('nav.main') }}</a>

    <template v-if="showShell">
      <aside class="desktop-rail" aria-label="Navigation principale">
        <NuxtLink to="/" class="brand-lockup">
          <span class="brand-mark"><i class="fas fa-droplet" aria-hidden="true"></i></span>
          <span><strong>Hydria</strong><small>Terrain</small></span>
        </NuxtLink>

        <nav class="mt-8 min-h-0 flex-1 overflow-y-auto" :aria-label="t('nav.main')">
          <section v-for="section in navigationSections" :key="section.labelKey" class="mb-7">
            <h2 class="rail-label">{{ t(section.labelKey) }}</h2>
            <ul class="space-y-1">
              <li v-for="item in section.items" :key="item.to">
                <NuxtLink :to="item.to" class="rail-link" :class="{ 'is-active': isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined">
                  <i :class="item.icon" aria-hidden="true"></i><span>{{ t(item.labelKey) }}</span>
                </NuxtLink>
              </li>
            </ul>
          </section>
        </nav>

        <div class="rail-status">
          <span class="status-dot" :class="isOnline ? 'is-online' : 'is-offline'"></span>
          <span><strong>{{ t(isOnline ? 'app.online' : 'app.offline') }}</strong><small>{{ isOnline ? t('app.synced') : t('app.offline_ready') }}</small></span>
        </div>
      </aside>

      <header class="topbar">
        <div class="flex min-w-0 items-center gap-3">
          <button type="button" class="icon-button lg:hidden" :aria-label="t('nav.open')" aria-controls="hydria-mobile-nav" :aria-expanded="isMobileMenuOpen" @click="isMobileMenuOpen = true">
            <i class="fas fa-bars" aria-hidden="true"></i>
          </button>
          <NuxtLink to="/" class="brand-lockup compact lg:hidden">
            <span class="brand-mark"><i class="fas fa-droplet" aria-hidden="true"></i></span>
            <span><strong>Hydria</strong><small>Terrain</small></span>
          </NuxtLink>
          <div class="hidden min-w-0 lg:block">
            <p class="text-sm font-semibold">{{ currentPageTitle }}</p>
            <p class="hydria-muted text-xs">{{ t('app.field_mode') }}</p>
          </div>
        </div>

        <div class="ml-auto flex items-center gap-1.5">
          <button v-if="canInstallPwa && !isStandalonePwa" type="button" class="icon-button" :aria-label="t('app.install')" @click="installPwa">
            <i class="fas fa-arrow-down-to-bracket" aria-hidden="true"></i>
          </button>

          <span class="connection-chip" :class="isOnline ? 'is-online' : 'is-offline'">
            <i :class="isOnline ? 'fas fa-cloud-arrow-up' : 'fas fa-cloud-slash'" aria-hidden="true"></i>
            <span class="hidden sm:inline">{{ t(isOnline ? 'app.synced_short' : 'app.offline') }}</span>
          </span>

          <div class="dropdown dropdown-end">
            <button type="button" tabindex="0" class="icon-button language-button" :aria-label="t('language')">
              <span>{{ currentLang }}</span>
            </button>
            <ul tabindex="0" class="dropdown-content menu z-50 mt-3 w-52 rounded-2xl border p-2 shadow-2xl" style="border-color:var(--hydria-line);background:var(--hydria-surface)">
              <li><button type="button" :class="{ active: currentLang === 'mg' }" @click="selectLanguage('mg')">Malagasy</button></li>
              <li><button type="button" :class="{ active: currentLang === 'fr' }" @click="selectLanguage('fr')">Français</button></li>
            </ul>
          </div>

          <button type="button" class="icon-button" :aria-label="t(isDarkTheme ? 'app.light_theme' : 'app.dark_theme')" @click="toggleTheme">
            <i :class="isDarkTheme ? 'fas fa-sun' : 'fas fa-moon'" aria-hidden="true"></i>
          </button>

          <button type="button" class="avatar-button" :aria-label="isAuthenticated ? t('auth.profile') : t('auth.login')" @click="isMobileMenuOpen = true">
            {{ userInitial }}
          </button>
        </div>
      </header>

      <div v-if="isMobileMenuOpen || isQuickSheetOpen" class="fixed inset-0 z-50 bg-[#010a10]/70 backdrop-blur-sm lg:hidden" aria-hidden="true" @click="closeOverlays"></div>

      <aside id="hydria-mobile-nav" class="mobile-drawer lg:hidden" :class="isMobileMenuOpen ? 'is-open' : ''" :aria-hidden="!isMobileMenuOpen" :inert="!isMobileMenuOpen">
        <div class="flex items-center justify-between border-b px-4 py-4" style="border-color:var(--hydria-line)">
          <div class="brand-lockup compact">
            <span class="brand-mark"><i class="fas fa-droplet" aria-hidden="true"></i></span>
            <span><strong>Hydria</strong><small>Terrain</small></span>
          </div>
          <button type="button" class="icon-button" :aria-label="t('nav.close')" @click="isMobileMenuOpen = false"><i class="fas fa-xmark" aria-hidden="true"></i></button>
        </div>

        <nav class="min-h-0 flex-1 overflow-y-auto px-3 py-5" :aria-label="t('nav.main')">
          <section v-for="section in navigationSections" :key="section.labelKey" class="mb-6">
            <h2 class="rail-label">{{ t(section.labelKey) }}</h2>
            <ul class="space-y-1">
              <li v-for="item in section.items" :key="item.to">
                <NuxtLink :to="item.to" class="rail-link" :class="{ 'is-active': isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined" @click="isMobileMenuOpen = false">
                  <i :class="item.icon" aria-hidden="true"></i><span>{{ t(item.labelKey) }}</span>
                </NuxtLink>
              </li>
            </ul>
          </section>
        </nav>

        <div class="border-t p-4" style="border-color:var(--hydria-line)">
          <div class="mb-3 flex items-center gap-3">
            <span class="avatar-button">{{ userInitial }}</span>
            <span class="min-w-0"><strong class="block truncate text-sm">{{ user?.username || 'Hydria' }}</strong><small class="hydria-muted">{{ t(isOnline ? 'app.online' : 'app.offline') }}</small></span>
          </div>
          <button v-if="isAuthenticated" type="button" class="flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-sm font-semibold transition hover:bg-white/5" @click="logout">
            <i class="fas fa-arrow-right-from-bracket" aria-hidden="true"></i>{{ t('auth.logout') }}
          </button>
        </div>
      </aside>

      <section class="quick-sheet lg:hidden" :class="isQuickSheetOpen ? 'is-open' : ''" role="dialog" aria-modal="true" :aria-label="t('dashboard.quick_actions')" :aria-hidden="!isQuickSheetOpen" :inert="!isQuickSheetOpen">
        <div class="mx-auto mb-4 h-1 w-12 rounded-full" style="background:var(--hydria-line)"></div>
        <div class="mb-4 flex items-center justify-between">
          <div><p class="hydria-kicker">Hydria Terrain</p><h2 class="mt-1 text-xl font-bold">{{ t('dashboard.quick_actions') }}</h2></div>
          <button type="button" class="icon-button" :aria-label="t('nav.close')" @click="isQuickSheetOpen = false"><i class="fas fa-xmark" aria-hidden="true"></i></button>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <NuxtLink v-for="action in quickActions" :key="action.to" :to="action.to" class="quick-action" @click="isQuickSheetOpen = false">
            <span class="hydria-icon"><i :class="action.icon" aria-hidden="true"></i></span><span>{{ t(action.labelKey) }}</span>
          </NuxtLink>
        </div>
      </section>

      <nav class="mobile-tabs lg:hidden" :aria-label="t('nav.main')">
        <NuxtLink v-for="item in bottomNavLeft" :key="item.to" :to="item.to" class="tab-link" :class="{ 'is-active': isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined">
          <i :class="item.icon" aria-hidden="true"></i><span>{{ t(item.labelKey) }}</span>
        </NuxtLink>
        <button type="button" class="add-tab" :aria-label="t('common.add')" @click="isQuickSheetOpen = true"><i class="fas fa-plus" aria-hidden="true"></i><span>{{ t('common.add') }}</span></button>
        <NuxtLink v-for="item in bottomNavRight" :key="item.to" :to="item.to" class="tab-link" :class="{ 'is-active': isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined">
          <i :class="item.icon" aria-hidden="true"></i><span>{{ t(item.labelKey) }}</span>
        </NuxtLink>
        <button type="button" class="tab-link" :aria-label="t('nav.more')" @click="isMobileMenuOpen = true"><i class="fas fa-ellipsis" aria-hidden="true"></i><span>{{ t('nav.more') }}</span></button>
      </nav>
    </template>

    <main id="hydria-main" :class="showShell ? 'main-area' : ''"><slot /></main>

    <footer v-if="showShell" class="desktop-footer hidden lg:block">
      <p>{{ t('footer.copyright', { year: new Date().getFullYear() }) }}</p>
      <p>{{ t('app.accessibility_note') }}</p>
    </footer>
  </div>
</template>

<script setup>
const route = useRoute()
const { currentLang, getTranslation: t, switchLanguage, initializeLanguage } = useLanguage()
const { isAuthenticated, user, initAuth, logout: authLogout } = useAuth()

const isMobileMenuOpen = ref(false)
const isQuickSheetOpen = ref(false)
const isDarkTheme = ref(true)
const isOnline = ref(true)
const canInstallPwa = ref(false)
const isStandalonePwa = ref(false)
const deferredInstallPrompt = ref(null)

const showShell = computed(() => !['/connexion', '/login'].includes(route.path))
const userInitial = computed(() => (user.value?.first_name || user.value?.username || 'H').charAt(0).toUpperCase())

const navigationSections = [
  { labelKey: 'nav.main', items: [
    { to: '/', labelKey: 'nav.home', icon: 'fas fa-house' },
    { to: '/dashboard', labelKey: 'nav.dashboard', icon: 'fas fa-chart-pie' },
    { to: '/search', labelKey: 'nav.search', icon: 'fas fa-magnifying-glass' },
    { to: '/plannings', labelKey: 'nav.planning', icon: 'fas fa-calendar-days' },
  ]},
  { labelKey: 'nav.operations', items: [
    { to: '/dashboard/infrastructure', labelKey: 'dashboard.infrastructure', icon: 'fas fa-water' },
    { to: '/dashboard/map', labelKey: 'dashboard.map', icon: 'fas fa-map-location-dot' },
    { to: '/stocks', labelKey: 'nav.inventory', icon: 'fas fa-boxes-stacked' },
    { to: '/notes', labelKey: 'nav.notes', icon: 'fas fa-note-sticky' },
  ]},
  { labelKey: 'nav.management', items: [
    { to: '/facturation', labelKey: 'nav.billing', icon: 'fas fa-file-invoice' },
    { to: '/dashboard/payments-volume-offline', labelKey: 'dashboard.payments_offline', icon: 'fas fa-cloud-arrow-down' },
    { to: '/employees/fiches-poste', labelKey: 'employees.job_descriptions', icon: 'fas fa-briefcase' },
    { to: '/employees/evaluations', labelKey: 'employees.evaluations', icon: 'fas fa-user-check' },
  ]},
]

const quickActions = [
  { to: '/plannings', labelKey: 'actions.new_planning', icon: 'fas fa-calendar-plus' },
  { to: '/search', labelKey: 'actions.view_ouvrages', icon: 'fas fa-magnifying-glass-location' },
  { to: '/facturation', labelKey: 'billing.readings', icon: 'fas fa-gauge-high' },
  { to: '/notes', labelKey: 'nav.notes', icon: 'fas fa-note-sticky' },
]

const bottomNavLeft = [
  { to: '/', labelKey: 'nav.home', icon: 'fas fa-house' },
  { to: '/search', labelKey: 'nav.search', icon: 'fas fa-magnifying-glass' },
]
const bottomNavRight = [
  { to: '/dashboard', labelKey: 'nav.dashboard_short', icon: 'fas fa-chart-pie' },
  { to: '/plannings', labelKey: 'nav.planning', icon: 'fas fa-calendar-days' },
]

const currentPageTitle = computed(() => {
  const item = navigationSections.flatMap(section => section.items).find(entry => isActive(entry.to))
  return item ? t(item.labelKey) : 'Hydria Terrain'
})

const isActive = (to) => to === '/' ? route.path === '/' : route.path === to || route.path.startsWith(`${to}/`)
const selectLanguage = lang => switchLanguage(lang)
const closeOverlays = () => { isMobileMenuOpen.value = false; isQuickSheetOpen.value = false }
const updateOnlineStatus = () => { isOnline.value = navigator.onLine }

const applyTheme = (theme) => {
  const normalized = theme === 'hydriaLight' ? 'hydriaLight' : 'hydriaDark'
  document.documentElement.setAttribute('data-theme', normalized)
  isDarkTheme.value = normalized === 'hydriaDark'
  localStorage.setItem('hydria-theme', normalized)
}
const toggleTheme = () => applyTheme(isDarkTheme.value ? 'hydriaLight' : 'hydriaDark')
const detectStandalonePwa = () => { isStandalonePwa.value = Boolean(window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone) }
const handleBeforeInstallPrompt = event => { event.preventDefault(); deferredInstallPrompt.value = event; canInstallPwa.value = true }
const handleAppInstalled = () => { canInstallPwa.value = false; deferredInstallPrompt.value = null; isStandalonePwa.value = true }
const installPwa = async () => { if (!deferredInstallPrompt.value) return; await deferredInstallPrompt.value.prompt(); await deferredInstallPrompt.value.userChoice; deferredInstallPrompt.value = null; canInstallPwa.value = false }
const logout = async () => { closeOverlays(); await authLogout() }
const handleEscape = event => { if (event.key === 'Escape') closeOverlays() }

watch(() => route.fullPath, closeOverlays)
watch([isMobileMenuOpen, isQuickSheetOpen], ([menu, sheet]) => { if (import.meta.client) document.body.style.overflow = menu || sheet ? 'hidden' : '' })

onMounted(() => {
  initAuth(); initializeLanguage(); applyTheme(localStorage.getItem('hydria-theme') || 'hydriaDark'); updateOnlineStatus(); detectStandalonePwa()
  window.addEventListener('online', updateOnlineStatus); window.addEventListener('offline', updateOnlineStatus)
  window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt); window.addEventListener('appinstalled', handleAppInstalled); window.addEventListener('keydown', handleEscape)
})

onUnmounted(() => {
  document.body.style.overflow = ''
  window.removeEventListener('online', updateOnlineStatus); window.removeEventListener('offline', updateOnlineStatus)
  window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt); window.removeEventListener('appinstalled', handleAppInstalled); window.removeEventListener('keydown', handleEscape)
})

useHead(() => ({ htmlAttrs: { lang: currentLang.value === 'mg' ? 'mg' : 'fr' } }))
</script>

<style scoped>
.hydria-shell { overflow-x: clip; background-color: var(--hydria-bg); color: var(--hydria-text); }
.skip-link { position: fixed; left: 1rem; top: 1rem; z-index: 100; transform: translateY(-200%); border-radius: .85rem; background: var(--hydria-cyan); color: #041a20; padding: .8rem 1rem; font-weight: 700; }
.skip-link:focus { transform: translateY(0); }
.brand-lockup { display: inline-flex; align-items: center; gap: .8rem; border-radius: .8rem; }
.brand-lockup strong { display: block; font-size: 1.2rem; line-height: 1; letter-spacing: -.02em; }
.brand-lockup small { display: block; margin-top: .25rem; color: var(--hydria-cyan); font-size: .67rem; font-weight: 700; letter-spacing: .2em; text-transform: uppercase; }
.brand-lockup.compact .brand-mark { width: 2.4rem; height: 2.4rem; border-radius: .8rem; }
.brand-lockup.compact strong { font-size: 1rem; }
.brand-mark { display: grid; width: 3rem; height: 3rem; place-items: center; border-radius: 1rem 1rem 1rem .35rem; background: var(--hydria-cyan); color: #052027; font-size: 1.15rem; box-shadow: 0 12px 28px color-mix(in srgb, var(--hydria-cyan) 22%, transparent); }
.desktop-rail { position: fixed; inset: 0 auto 0 0; z-index: 30; display: none; width: 17rem; flex-direction: column; border-right: 1px solid var(--hydria-line); background: color-mix(in srgb, var(--hydria-surface) 94%, transparent); padding: 1.5rem 1.2rem; backdrop-filter: blur(18px); }
.rail-label { margin: 0 0 .55rem .75rem; color: var(--hydria-muted); font-size: .66rem; font-weight: 700; letter-spacing: .15em; text-transform: uppercase; }
.rail-link { display: flex; min-height: 2.85rem; align-items: center; gap: .85rem; border-radius: .85rem; padding: .55rem .75rem; color: var(--hydria-muted); font-size: .9rem; font-weight: 600; transition: background 180ms ease, color 180ms ease, transform 180ms ease; }
.rail-link i { width: 1.1rem; text-align: center; }
.rail-link:hover { background: color-mix(in srgb, var(--hydria-cyan) 8%, transparent); color: var(--hydria-text); }
.rail-link.is-active { background: color-mix(in srgb, var(--hydria-cyan) 14%, transparent); color: var(--hydria-cyan); }
.rail-link:active { transform: translateY(1px); }
.rail-status { display: flex; align-items: center; gap: .8rem; border: 1px solid var(--hydria-line); border-radius: 1rem; background: var(--hydria-surface-soft); padding: .85rem; }
.rail-status strong, .rail-status small { display: block; }
.rail-status strong { font-size: .8rem; }.rail-status small { margin-top: .15rem; color: var(--hydria-muted); font-size: .7rem; }
.status-dot { width: .65rem; height: .65rem; flex: 0 0 auto; border-radius: 999px; box-shadow: 0 0 0 5px color-mix(in srgb, currentColor 12%, transparent); }
.status-dot.is-online { background: var(--hydria-success); color: var(--hydria-success); }.status-dot.is-offline { background: var(--hydria-amber); color: var(--hydria-amber); }
.topbar { position: sticky; top: 0; z-index: 40; display: flex; min-height: 4.25rem; align-items: center; border-bottom: 1px solid var(--hydria-line); background: color-mix(in srgb, var(--hydria-bg) 87%, transparent); padding: max(.55rem, env(safe-area-inset-top)) 1rem .55rem; backdrop-filter: blur(18px); }
.icon-button, .avatar-button { display: inline-grid; min-width: 2.75rem; height: 2.75rem; place-items: center; border-radius: .85rem; color: var(--hydria-muted); transition: background 180ms ease, color 180ms ease, transform 180ms ease; }
.icon-button:hover { background: var(--hydria-surface-soft); color: var(--hydria-text); }.icon-button:active, .avatar-button:active { transform: scale(.96); }
.language-button span { font-size: .68rem; font-weight: 800; text-transform: uppercase; }
.avatar-button { background: var(--hydria-cyan); color: #041a20; font-size: .8rem; font-weight: 800; }
.connection-chip { display: inline-flex; min-height: 2.75rem; align-items: center; gap: .45rem; border-radius: .85rem; padding: 0 .75rem; font-size: .75rem; font-weight: 700; }
.connection-chip.is-online { background: color-mix(in srgb, var(--hydria-success) 12%, transparent); color: var(--hydria-success); }.connection-chip.is-offline { background: color-mix(in srgb, var(--hydria-amber) 13%, transparent); color: var(--hydria-amber); }
.mobile-drawer { position: fixed; inset: 0 auto 0 0; z-index: 60; display: flex; width: min(88vw, 23rem); transform: translateX(-102%); flex-direction: column; border-right: 1px solid var(--hydria-line); background: var(--hydria-surface); box-shadow: 22px 0 70px rgba(0,0,0,.35); transition: transform 280ms cubic-bezier(.2,.8,.2,1); }.mobile-drawer.is-open { transform: translateX(0); }
.quick-sheet { position: fixed; inset: auto 0 0 0; z-index: 65; transform: translateY(105%); border: 1px solid var(--hydria-line); border-bottom: 0; border-radius: 1.5rem 1.5rem 0 0; background: var(--hydria-surface); padding: 1rem 1rem calc(6.5rem + env(safe-area-inset-bottom)); box-shadow: 0 -22px 70px rgba(0,0,0,.38); transition: transform 280ms cubic-bezier(.2,.8,.2,1); }.quick-sheet.is-open { transform: translateY(0); }
.quick-action { display: flex; min-height: 6.5rem; flex-direction: column; align-items: flex-start; justify-content: space-between; border: 1px solid var(--hydria-line); border-radius: 1rem; background: var(--hydria-surface-soft); padding: 1rem; font-size: .9rem; font-weight: 700; }
.mobile-tabs { position: fixed; inset: auto 0 0 0; z-index: 45; display: grid; grid-template-columns: repeat(6,minmax(0,1fr)); align-items: end; border-top: 1px solid var(--hydria-line); background: color-mix(in srgb, var(--hydria-surface) 94%, transparent); padding: .45rem .25rem max(.45rem, env(safe-area-inset-bottom)); backdrop-filter: blur(22px); }
.tab-link, .add-tab { display: flex; min-height: 3.6rem; flex-direction: column; align-items: center; justify-content: center; gap: .3rem; border-radius: .8rem; color: var(--hydria-muted); font-size: .62rem; font-weight: 600; }.tab-link i { font-size: 1.08rem; }.tab-link.is-active { color: var(--hydria-cyan); }
.add-tab { position: relative; color: var(--hydria-muted); }.add-tab i { display: grid; width: 3.15rem; height: 3.15rem; margin-top: -1.25rem; place-items: center; border-radius: 1.1rem; background: var(--hydria-cyan); color: #041a20; font-size: 1.15rem; box-shadow: 0 12px 28px color-mix(in srgb, var(--hydria-cyan) 28%, transparent); }.add-tab span { margin-top: -.1rem; }
.main-area { min-height: calc(100dvh - 4.25rem); width: 100%; padding: 1.15rem 1rem 6.8rem; }
.desktop-footer { margin-left: 17rem; border-top: 1px solid var(--hydria-line); padding: 1rem 2rem; color: var(--hydria-muted); font-size: .75rem; }
.desktop-footer p:last-child { margin-top: .25rem; }
@media (min-width: 1024px) { .desktop-rail { display: flex; }.topbar { margin-left: 17rem; padding-left: 2rem; padding-right: 2rem; }.main-area { margin-left: 17rem; width: calc(100% - 17rem); padding: 2rem; }.main-area > :deep(*) { max-width: 82rem; margin-left: auto; margin-right: auto; }.desktop-footer { display: flex !important; justify-content: space-between; } }
@media (max-width: 370px) { .tab-link, .add-tab { font-size: .56rem; }.brand-lockup.compact small { display: none; }.connection-chip { padding: 0 .6rem; } }
</style>
