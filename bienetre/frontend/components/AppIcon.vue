<template>
  <span class="icon-shell" :class="[`icon-shell-${tone}`, shellSizeClass]">
    <svg :class="svgSizeClass" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <linearGradient :id="gradientId" x1="4" y1="4" x2="20" y2="20" gradientUnits="userSpaceOnUse">
          <stop :stop-color="gradientColors[0]" />
          <stop offset="1" :stop-color="gradientColors[1]" />
        </linearGradient>
      </defs>
      <g :stroke="`url(#${gradientId})`" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.9">
        <path v-if="name === 'dashboard'" d="M4 13h7V4H4zm9 7h7v-9h-7zM4 20h7v-5H4zm9-9h7V4h-7z" />
        <path v-else-if="name === 'profile'" d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm-7 8a7 7 0 0 1 14 0" />
        <path v-else-if="name === 'meal'" d="M4 11h16M8 6v10m8-10v10M6 18h12" />
        <path v-else-if="name === 'shopping'" d="M6 7h15l-1.5 8h-11ZM6 7 5 4H2m7 16a1 1 0 1 0 0 .01M18 20a1 1 0 1 0 0 .01" />
        <path v-else-if="name === 'fitness'" d="M7 9v6m10-6v6M4 10h3v4H4zm13 0h3v4h-3zM9 7h2v10H9zm4 0h2v10h-2z" />
        <path v-else-if="name === 'energy'" d="m13 2-7 11h5l-1 9 8-12h-5l0-8Z" />
        <path v-else-if="name === 'heart'" d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" />
        <path v-else-if="name === 'target'" d="M12 19a7 7 0 1 1 7-7M12 15a3 3 0 1 1 3-3m5-5-5 5" />
        <path v-else-if="name === 'lock'" d="M7 11V8a5 5 0 0 1 10 0v3m-11 0h12v9H6zm4 4a2 2 0 1 0 4 0 2 2 0 0 0-4 0Z" />
        <path v-else-if="name === 'logout'" d="M10 17v2a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v2m4 5H4m3-3-3 3 3 3" />
        <path v-else d="M12 3v18M3 12h18" />
      </g>
    </svg>
  </span>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  name: string
  tone?: "amber" | "sky" | "emerald" | "rose" | "violet"
  size?: "sm" | "md" | "lg"
}>(), {
  tone: "amber",
  size: "md",
})

const gradientMap = {
  amber: ["#fde68a", "#f97316"],
  sky: ["#7dd3fc", "#2563eb"],
  emerald: ["#86efac", "#059669"],
  rose: ["#fda4af", "#db2777"],
  violet: ["#c4b5fd", "#7c3aed"],
} as const

const gradientColors = computed(() => gradientMap[props.tone])
const gradientId = `icon-gradient-${props.name}-${props.tone}`
const shellSizeClass = computed(() => {
  if (props.size === "lg") return "icon-shell-lg"
  if (props.size === "sm") return "icon-shell-sm"
  return "icon-shell-md"
})
const svgSizeClass = computed(() => {
  if (props.size === "lg") return "h-6 w-6"
  if (props.size === "sm") return "h-[18px] w-[18px]"
  return "h-5 w-5"
})
</script>
