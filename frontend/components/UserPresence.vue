<template>
  <div v-if="activeUsers.length > 0" class="flex items-center gap-1 mx-2">
    <div class="flex -space-x-2 overflow-hidden">
      <div
        v-for="user in displayedUsers"
        :key="user.id"
        class="tooltip tooltip-bottom"
        :data-tip="
          user.full_name + (user.surnom ? ' (' + user.surnom + ')' : '')
        "
      >
        <div
          class="inline-block h-8 w-8 rounded-full ring-2 ring-base-100 bg-primary text-primary-content flex items-center justify-center text-xs font-medium uppercase border border-base-300 shadow-sm"
        >
          {{ user.full_name[0] }}
        </div>
      </div>
      <div
        v-if="remainingCount > 0"
        class="inline-block h-8 w-8 rounded-full ring-2 ring-base-100 bg-base-300 text-base-content flex items-center justify-center text-xs font-medium border border-base-300 shadow-sm"
      >
        +{{ remainingCount }}
      </div>
    </div>
    <span
      class="text-[10px] text-base-content/70 hidden xl:inline ml-1 font-medium italic leading-tight"
    >
      {{ activeUsers.length }}
      {{ activeUsers.length > 1 ? "utilisateurs" : "utilisateur" }} actif(s)
    </span>
  </div>
</template>

<script setup>
const props = defineProps({
  maxDisplay: {
    type: Number,
    default: 3,
  },
});

const route = useRoute();
const config = useRuntimeConfig();
const activeUsers = ref([]);

const displayedUsers = computed(() =>
  activeUsers.value.slice(0, props.maxDisplay),
);
const remainingCount = computed(() =>
  Math.max(0, activeUsers.value.length - props.maxDisplay),
);

let timer = null;

const updatePresence = async () => {
  // On ne veut pas flooder si on n'est pas sur une page traçable (login, etc)
  if (route.path === "/login") return;

  try {
    const response = await $fetch(
      `${config.public.apiBaseUrl}/systeme/api/presence/update/`,
      {
        method: "POST",
        body: { path: route.fullPath },
        headers: useRequestHeaders(["cookie"]),
      },
    );

    if (response.success) {
      activeUsers.value = response.active_users;
    }
  } catch (error) {
    // Silently fail to not disturb user
    // console.error('Error updating presence:', error)
  }
};

onMounted(() => {
  // Petit délai pour laisser l'auth s'initialiser
  setTimeout(() => {
    updatePresence();
    // Ping toutes les 20 secondes
    timer = setInterval(updatePresence, 20000);
  }, 1000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});

// Mettre à jour quand le chemin change
watch(
  () => route.fullPath,
  () => {
    updatePresence();
  },
);
</script>
