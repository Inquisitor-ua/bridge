<script setup>
import { computed } from "vue";

// a profile picture, or the first letter of the name when there is none
// (a robot for a computer player); sizing comes from the classes the parent
// puts on it. The slot is for overlays that sit on the avatar (emote bubbles
// at the table).
const props = defineProps({
  name: { type: String, default: "" },
  src: { type: String, default: null },
  bot: { type: Boolean, default: false },
});

const initial = computed(() => (props.name || "?").trim().charAt(0).toUpperCase());
</script>

<template>
  <span class="avatar" :class="{ 'has-image': !!src }">
    <img v-if="src" :src="src" alt="" class="avatar-img" draggable="false" />
    <svg
      v-else-if="bot"
      class="avatar-bot"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <rect x="4.5" y="8" width="15" height="11" rx="3" />
      <path d="M12 8V5M9.5 13v.5M14.5 13v.5M9.5 16.5h5" />
      <circle cx="12" cy="4" r="1" />
    </svg>
    <template v-else>{{ initial }}</template>
    <slot />
  </span>
</template>
