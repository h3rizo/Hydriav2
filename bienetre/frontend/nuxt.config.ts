export default defineNuxtConfig({
  modules: ["@nuxtjs/tailwindcss"],
  css: ["~/assets/css/main.css"],
  ssr: false,
  devtools: { enabled: false },
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || "http://localhost:8000/api",
    },
  },
  nitro: {
    experimental: {
      tasks: false,
    },
  },
  app: {
    buildAssetsDir: "/_assets/",
    head: {
      title: "Bien-etre Hydria",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1" },
      ],
      link: [
        {
          rel: "icon",
          type: "image/svg+xml",
          href: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' font-size='52'%3E%F0%9F%92%AA%3C/text%3E%3C/svg%3E",
        },
      ],
    },
  },
  routeRules: {
    "/dashboard": { ssr: true },
    "/meal-plans": { ssr: true },
  },
  compatibilityDate: "2024-11-01",
})
