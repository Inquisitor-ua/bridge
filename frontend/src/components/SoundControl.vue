<script setup>
import { computed } from "vue";
import { sound, toggleMute, playTurnChime } from "../sound.js";

const silent = computed(() => sound.muted || sound.volume === 0);
const percent = computed(() => (silent.value ? 0 : Math.round(sound.volume * 100)));

function onInput(ev) {
  sound.volume = Number(ev.target.value) / 100;
  sound.muted = false;
}

function onToggle() {
  toggleMute();
  if (!silent.value) playTurnChime();
}
</script>

<template>
  <div class="sound-control" :class="{ silent }">
    <button
      class="ghost small sound-btn"
      :title="silent ? 'Включить звук' : 'Выключить звук'"
      :aria-label="silent ? 'Включить звук' : 'Выключить звук'"
      :aria-pressed="silent"
      @click="onToggle"
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4z" fill="currentColor" stroke-width="1.4" />
        <template v-if="silent">
          <path d="M16 9.5l5 5M21 9.5l-5 5" />
        </template>
        <template v-else>
          <path d="M15.5 9a4.2 4.2 0 0 1 0 6" />
          <path v-if="percent > 50" d="M18.3 6.5a8 8 0 0 1 0 11" />
        </template>
      </svg>
    </button>
    <input
      class="sound-slider"
      type="range"
      min="0"
      max="100"
      step="1"
      :value="percent"
      :style="{ '--fill': percent + '%' }"
      aria-label="Громкость"
      :title="`Громкость: ${percent}%`"
      @input="onInput"
      @change="playTurnChime"
    />
  </div>
</template>
