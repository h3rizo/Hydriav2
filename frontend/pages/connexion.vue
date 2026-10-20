<template>
  <div class="relative grid min-h-screen place-items-center overflow-hidden bg-base-200 px-4 py-8 sm:px-6">
    <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,hsl(var(--p)/0.14),transparent_32rem),radial-gradient(circle_at_85%_80%,hsl(var(--a)/0.1),transparent_28rem)]"></div>

    <div class="relative grid w-full max-w-5xl overflow-hidden rounded-[1.75rem] border border-base-300 bg-base-100 shadow-2xl lg:grid-cols-[0.9fr_1.1fr]">
      <aside class="hidden flex-col justify-between bg-neutral p-10 text-neutral-content lg:flex">
        <div>
          <span class="grid h-12 w-12 place-items-center rounded-2xl bg-neutral-content/10 text-2xl" aria-hidden="true">🏺</span>
          <p class="mt-6 text-sm font-bold uppercase tracking-[0.18em] text-neutral-content/55">Hydria</p>
          <h1 class="mt-3 max-w-md text-balance text-4xl font-bold leading-tight tracking-[-0.04em]">{{ t('app.subtitle') }}</h1>
          <p class="mt-4 max-w-sm leading-7 text-neutral-content/65">{{ t('auth.subtitle') }}</p>
        </div>
        <p class="text-sm text-neutral-content/50">{{ t('footer.copyright', { year: new Date().getFullYear() }) }}</p>
      </aside>

      <main class="p-6 sm:p-10 lg:p-12">
        <div class="mx-auto max-w-md">
          <div class="mb-8 flex items-center justify-between lg:justify-end">
            <NuxtLink to="/" class="flex items-center gap-2 font-bold text-primary lg:hidden"><span aria-hidden="true">🏺</span>Hydria</NuxtLink>
            <div class="join">
              <button type="button" class="btn btn-sm join-item" :class="currentLang === 'mg' ? 'btn-primary' : 'btn-ghost bg-base-200'" @click="switchLanguage('mg')">MG</button>
              <button type="button" class="btn btn-sm join-item" :class="currentLang === 'fr' ? 'btn-primary' : 'btn-ghost bg-base-200'" @click="switchLanguage('fr')">FR</button>
            </div>
          </div>

          <p class="text-xs font-bold uppercase tracking-[0.16em] text-primary">Hydria</p>
          <h2 class="mt-2 text-3xl font-bold tracking-[-0.035em]">{{ t('auth.welcome') }}</h2>
          <p class="mt-2 text-sm leading-6 text-base-content/60">{{ t('auth.subtitle') }}</p>

          <form class="mt-8 space-y-5" @submit.prevent="handleLogin">
            <div>
              <label for="username" class="mb-2 block text-sm font-semibold">{{ t('auth.username') }}</label>
              <div class="relative">
                <i class="fas fa-user pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-base-content/40" aria-hidden="true"></i>
                <input id="username" v-model="form.username" type="text" autocomplete="username" :placeholder="t('auth.username_placeholder')" class="input input-bordered min-h-12 w-full pl-11 focus:outline-primary" required />
              </div>
            </div>

            <div>
              <label for="password" class="mb-2 block text-sm font-semibold">{{ t('auth.password') }}</label>
              <div class="relative">
                <i class="fas fa-lock pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-base-content/40" aria-hidden="true"></i>
                <input id="password" v-model="form.password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" :placeholder="t('auth.password_placeholder')" class="input input-bordered min-h-12 w-full px-11 focus:outline-primary" required />
                <button type="button" class="btn btn-ghost btn-sm btn-circle absolute right-2 top-1/2 -translate-y-1/2" :aria-label="t(showPassword ? 'auth.hide_password' : 'auth.show_password')" @click="showPassword = !showPassword">
                  <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'" aria-hidden="true"></i>
                </button>
              </div>
            </div>

            <label class="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-1 text-sm">
              <input v-model="form.rememberMe" type="checkbox" class="checkbox checkbox-primary checkbox-sm" />
              <span>{{ t('auth.remember') }}</span>
            </label>

            <div v-if="loginError" class="alert alert-error items-start text-sm" role="alert">
              <i class="fas fa-circle-exclamation mt-0.5" aria-hidden="true"></i>
              <span>{{ loginError }}</span>
            </div>

            <div v-if="loginSuccess" class="alert alert-success items-start text-sm" role="status">
              <i class="fas fa-circle-check mt-0.5" aria-hidden="true"></i>
              <span>{{ t('auth.success') }}</span>
            </div>

            <button type="submit" class="btn btn-primary min-h-12 w-full" :disabled="isLoading || loginSuccess">
              <span v-if="isLoading" class="loading loading-spinner loading-sm" aria-hidden="true"></span>
              <i v-else class="fas fa-arrow-right-to-bracket" aria-hidden="true"></i>
              {{ t(isLoading ? 'auth.logging_in' : 'auth.login') }}
            </button>
          </form>

          <div class="mt-7 border-t border-base-300 pt-5 text-center text-sm text-base-content/60">
            <p>{{ t('auth.help') }}</p>
            <a href="mailto:admin@hydria.mg" class="mt-2 inline-flex min-h-11 items-center gap-2 font-semibold text-primary hover:underline">
              <i class="fas fa-envelope" aria-hidden="true"></i>{{ t('auth.contact') }}
            </a>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
const { currentLang, getTranslation: t, switchLanguage } = useLanguage()
const { login } = useAuth()

const form = ref({ username: '', password: '', rememberMe: false })
const isLoading = ref(false)
const showPassword = ref(false)
const loginError = ref('')
const loginSuccess = ref(false)

const handleLogin = async () => {
  loginError.value = ''
  loginSuccess.value = false

  if (!form.value.username.trim() || !form.value.password) {
    loginError.value = t('auth.required')
    return
  }

  isLoading.value = true
  const result = await login(form.value)
  isLoading.value = false

  if (!result.success) {
    loginError.value = t('auth.invalid')
    return
  }

  loginSuccess.value = true
  setTimeout(() => navigateTo('/dashboard'), 450)
}

useHead({ title: () => `${t('auth.welcome')} · Hydria` })
</script>
