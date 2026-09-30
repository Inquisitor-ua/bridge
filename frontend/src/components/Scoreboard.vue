<script setup>
import { computed } from "vue";
import { state } from "../store.js";

const players = computed(() => state.game?.players || []);
const turnId = computed(() => state.game?.turn_player_id);
</script>

<template>
  <ul class="scoreboard">
    <li
      v-for="p in players"
      :key="p.id"
      :class="{ turn: p.id === turnId, eliminated: p.eliminated, me: p.id === state.playerId }"
    >
      <span class="dot" :class="{ off: !p.connected }"></span>
      <span class="name">{{ p.name }}</span>
      <span class="hand-count">{{ p.hand_count }} карт</span>
      <span class="score">{{ p.score }} оч.</span>
      <span v-if="p.eliminated" class="badge">выбыл</span>
    </li>
  </ul>
</template>
