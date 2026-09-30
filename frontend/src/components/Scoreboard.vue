<script setup>
import { computed } from "vue";
import { state } from "../store.js";

const players = computed(() => state.game?.players || []);
const turnId = computed(() => state.game?.turn_player_id);

function initial(name) {
  return (name || "?").trim().charAt(0).toUpperCase();
}
</script>

<template>
  <ul class="scoreboard">
    <li
      v-for="p in players"
      :key="p.id"
      class="player-chip"
      :class="{ turn: p.id === turnId, eliminated: p.eliminated, me: p.id === state.playerId }"
    >
      <span class="avatar" :class="{ off: !p.connected }">{{ initial(p.name) }}</span>
      <span class="player-info">
        <span class="name">
          {{ p.name }}
          <span v-if="p.id === state.playerId" class="you">вы</span>
        </span>
        <span class="meta">
          <span class="meta-cards">{{ p.hand_count }} карт</span>
          <span class="meta-sep">·</span>
          <span class="meta-score">{{ p.score }}</span>
        </span>
      </span>
      <span v-if="p.eliminated" class="tag danger">выбыл</span>
    </li>
  </ul>
</template>
