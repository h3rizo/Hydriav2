<template>
  <div style="background: lightblue; padding: 20px; color: black;">
    <h1 style="color: red; font-size: 24px;">SIMPLE TEST PAGE</h1>
    <p>Si vous voyez cette page, Nuxt fonctionne !</p>
    <p>Port: 3002</p>
    <p>URL: /simple</p>
  </div>
</template>

<script setup>
definePageMeta({
  layout: false,
  title: 'Simple Test'
})
</script>