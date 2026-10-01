<script setup>
import { computed } from "vue";
import { state } from "../store.js";

const props = defineProps({
  // cards still in flight towards a player's hand, keyed by player id --
  // they are left out of the mini hand until they land
  incoming: { type: Object, default: () => ({}) },
});

const MAX_BACKS = 12;

const players = computed(() => state.game?.players || []);
const turnId = computed(() => state.game?.turn_player_id);

function initial(name) {
  return (name || "?").trim().charAt(0).toUpperCase();
}

function shownBacks(p) {
  return Math.min(Math.max(p.hand_count - (props.incoming[p.id] || 0), 0), MAX_BACKS);
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
      <span
        v-if="p.id !== state.playerId && !p.eliminated"
        class="mini-hand"
        :data-hand-for="p.id"
        :style="{ '--n': shownBacks(p) }"
      >
        <span v-for="i in shownBacks(p)" :key="i" class="mini-back" :style="{ '--i': i - 1 }"></span>
      </span>
      <span v-if="p.eliminated" class="tag danger">выбыл</span>
    </li>
  </ul>
</template>
