export default defineNuxtConfig({
  devtools: { enabled: true },
  
  // Configuration PWA (temporarily disabled)
  modules: [
    '@vite-pwa/nuxt',
    '@nuxtjs/supabase',
    '@pinia/nuxt',
    '@nuxtjs/tailwindcss'
    // '@nuxtjs/i18n' // Temporarily disabled for troubleshooting
  ],

  // Configuration CSS et Tailwind
  css: ['~/assets/css/main.css'],

  // Configuration PostCSS
  postcss: {
    plugins: {
      tailwindcss: {},
      autoprefixer: {},
    },
  },
  
  // Configuration du thème par défaut
  app: {
    head: {
      htmlAttrs: {
        'data-theme': 'hydriaDark'
      },
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap'
        },
        // Font Awesome
        {
          rel: 'stylesheet',
          href: 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
        }
      ]
    }
  },
  
  // Configuration PWA pour mode hors ligne
  pwa: {
    registerType: 'autoUpdate',
    workbox: {
      navigateFallback: '/',
      globPatterns: ['**/*.{js,css,html,png,svg,ico}'],
      runtimeCaching: [
        {
          urlPattern: /^https:\/\/api\.hydria\.mg\/.*$/i,
          handler: 'NetworkFirst',
          options: {
            cacheName: 'hydria-api-cache',
            networkTimeoutSeconds: 10,
            expiration: {
              maxEntries: 50,
              maxAgeSeconds: 60 * 60 * 24, // 24 heures
            },
          },
        },
        {
          urlPattern: /^https:\/\/.*\.supabase\.co\/.*$/i,
          handler: 'NetworkFirst',
          options: {
            cacheName: 'supabase-cache',
            networkTimeoutSeconds: 10,
            expiration: {
              maxEntries: 100,
              maxAgeSeconds: 60 * 60 * 24 * 7, // 7 jours
            },
          },
        },
      ],
    },
    client: {
      installPrompt: true,
    },
    devOptions: {
      enabled: true,
      suppressWarnings: true,
      navigateFallback: '/',
      navigateFallbackAllowlist: [/^\/$/],
      type: 'module',
    },
    manifest: {
      name: 'Hydria - Gestion Eau Madagascar',
      short_name: 'Hydria',
      description: 'Application de gestion opérationnelle pour l\'approvisionnement en eau à Madagascar',
      theme_color: '#07151f',
      background_color: '#07151f',
      display: 'standalone',
      orientation: 'portrait',
      scope: '/',
      start_url: '/',
      icons: [
        {
          src: '/icons/pwa-64x64.png',
          sizes: '64x64',
          type: 'image/png'
        },
        {
          src: '/icons/pwa-192x192.png',
          sizes: '192x192',
          type: 'image/png'
        },
        {
          src: '/icons/pwa-512x512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'any'
        },
        {
          src: '/icons/maskable-icon-512x512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable'
        }
      ],
      categories: ['productivity', 'utilities'],
      screenshots: [
        {
          src: '/screenshots/desktop.png',
          sizes: '1280x720',
          type: 'image/png',
          form_factor: 'wide',
          label: 'Interface bureau Hydria'
        },
        {
          src: '/screenshots/mobile.png',
          sizes: '390x844',
          type: 'image/png',
          form_factor: 'narrow',
          label: 'Interface mobile Hydria'
        }
      ]
    }
  },

  // Configuration Supabase
  supabase: {
    url: process.env.NUXT_PUBLIC_SUPABASE_URL || 'https://ytqvyihgztdnwkgvozqn.supabase.co',
    key: process.env.NUXT_PUBLIC_SUPABASE_ANON_KEY,
    redirectOptions: {
      login: '/login',
      callback: '/login',
      exclude: ['/*'],
    }
  },

  // Variables d'environnement
  runtimeConfig: {
    // Variables côté serveur seulement
    private: {
      supabaseServiceKey: process.env.SUPABASE_SERVICE_KEY,
    },
    // Variables accessibles côté client
    public: {
      supabaseUrl: process.env.SUPABASE_URL || 'https://ytqvyihgztdnwkgvozqn.supabase.co',
      supabaseAnonKey: process.env.SUPABASE_ANON_KEY,
      apiBaseUrl: process.env.API_BASE_URL || 'http://localhost:8000',
      apiBase: process.env.API_BASE || 'http://localhost:8000',
      appVersion: '1.0.0',
      environment: process.env.NODE_ENV || 'development'
    }
  },

  // Configuration de build
  nitro: {
    preset: 'node-server',
    prerender: {
      crawlLinks: false,
      failOnError: false
    }
  },

  // Configuration TypeScript
  typescript: {
    strict: true
  },

  // Configuration de sécurité
  ssr: true,
  
  // Configuration des headers de sécurité
  routeRules: {
    '/admin/**': { 
      headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' },
      prerender: false 
    },
    '/api/**': { 
      cors: true,
      headers: { 'Access-Control-Allow-Methods': 'GET,HEAD,PUT,PATCH,POST,DELETE' }
    },
    '/**': {
      headers: {
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'strict-origin-when-cross-origin'
      }
    }
  },

  // Configuration i18n
  i18n: {
    locales: [
      {
        code: 'mg',
        language: 'mg-MG',
        name: 'Malagasy',
        file: 'mg.json'
      },
      {
        code: 'fr',
        language: 'fr-FR',
        name: 'Français',
        file: 'fr.json'
      }
    ],
    defaultLocale: 'mg',
    strategy: 'prefix_except_default',
    langDir: 'locales/',
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: 'i18n_redirected',
      redirectOn: 'root',
      alwaysRedirect: false,
      fallbackLocale: 'mg'
    }
  },

  // Configuration de compatibilité
  compatibilityDate: '2024-11-01',
  
  // Configuration de développement
  devServer: {
    port: 3000,
    host: '0.0.0.0'
  }
})
