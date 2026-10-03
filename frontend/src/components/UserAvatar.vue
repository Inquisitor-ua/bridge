<script setup>
import { computed } from "vue";

// a profile picture, or the first letter of the name when there is none;
// sizing comes from the classes the parent puts on it. The slot is for
// overlays that sit on the avatar (emote bubbles at the table).
const props = defineProps({
  name: { type: String, default: "" },
  src: { type: String, default: null },
});

const initial = computed(() => (props.name || "?").trim().charAt(0).toUpperCase());
</script>

<template>
  <span class="avatar" :class="{ 'has-image': !!src }">
    <img v-if="src" :src="src" alt="" class="avatar-img" draggable="false" />
    <template v-else>{{ initial }}</template>
    <slot />
  </span>
</template>
