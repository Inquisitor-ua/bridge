<script setup>
import { computed } from "vue";

// a profile picture, or the first letter of the name when there is none;
// sizing comes from the classes the parent puts on it
const props = defineProps({
  user: { type: Object, required: true },
});

const initial = computed(() => (props.user.display_name || "?").charAt(0).toUpperCase());
</script>

<template>
  <span class="avatar" :class="{ 'has-image': !!user.avatar_url }">
    <img v-if="user.avatar_url" :src="user.avatar_url" alt="" class="avatar-img" />
    <template v-else>{{ initial }}</template>
  </span>
</template>
