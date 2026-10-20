<script setup>
// Redirection automatique vers la page de connexion
await navigateTo('/connexion')
</script>

<template>
  <div class="min-h-screen bg-base-200 flex items-center justify-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
</template>