/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class', // CRITICAL: Nécessaire pour le système de thèmes DaisyUI
  content: [
    "../backend/templates/**/*.{html,js}",
    "../backend/static/**/*.js",
    "./src/**/*.{html,js}",
    "./components/**/*.{js,vue,ts}",
    "./layouts/**/*.vue",
    "./pages/**/*.vue",
    "./plugins/**/*.{js,ts}",
    "./nuxt.config.{js,ts}",
    "./app.vue"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'Segoe UI Variable', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        hydria: '0 18px 55px rgba(1, 13, 22, 0.22)',
      },
    },
  },
  plugins: [
    require('daisyui'),
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
  daisyui: {
    themes: [
      {
        // Thème sombre personnalisé Hydria
        "hydriaDark": {
          "primary": "#3b82f6",        // Bleu
          "primary-content": "#ffffff",
          "secondary": "#64748b",      // Slate
          "secondary-content": "#ffffff",
          "accent": "#10b981",         // Emerald
          "accent-content": "#ffffff",
          "neutral": "#374151",        // Gray-700
          "neutral-content": "#f3f4f6",
          "base-100": "#1f2937",       // Gray-800 - Fond principal
          "base-200": "#111827",       // Gray-900 - Fond secondaire
          "base-300": "#374151",       // Gray-700 - Bordures
          "base-content": "#f9fafb",   // Gray-50 - Texte principal
          "info": "#0ea5e9",           // Sky-500
          "info-content": "#ffffff",
          "success": "#10b981",        // Emerald-500
          "success-content": "#ffffff",
          "warning": "#f59e0b",        // Amber-500
          "warning-content": "#ffffff",
          "error": "#ef4444",          // Red-500
          "error-content": "#ffffff",
        },
      },
      {
        "hydriaLight": {
          "primary": "#087f78",
          "primary-content": "#ffffff",
          "secondary": "#3b6578",
          "secondary-content": "#ffffff",
          "accent": "#d88a16",
          "accent-content": "#14212a",
          "neutral": "#173242",
          "neutral-content": "#f5fbff",
          "base-100": "#f7faf9",
          "base-200": "#edf4f2",
          "base-300": "#d5e2df",
          "base-content": "#102630",
          "info": "#1686a0",
          "info-content": "#ffffff",
          "success": "#21885e",
          "success-content": "#ffffff",
          "warning": "#d88a16",
          "warning-content": "#17242c",
          "error": "#d74f54",
          "error-content": "#ffffff"
        }
      },
      "winter", // Thème clair de DaisyUI
      "dark",   // Thème sombre standard
    ],
    darkTheme: "hydriaDark",
    base: true,
    styled: true,
    utils: true,
    prefix: "",
    logs: false,
    themeRoot: ":root",
  },
}
