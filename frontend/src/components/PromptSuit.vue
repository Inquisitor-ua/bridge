<script setup>
import { computed } from "vue";
import { state, declareSuit } from "../store.js";

const SUITS = [
  { id: "hearts", symbol: "♥", red: true, name: "Черви" },
  { id: "diamonds", symbol: "♦", red: true, name: "Бубны" },
  { id: "clubs", symbol: "♣", red: false, name: "Трефы" },
  { id: "spades", symbol: "♠", red: false, name: "Пики" },
];

// how many cards of each suit are left in hand (jacks are wild, so they
// don't count towards any suit) -- a hint for which suit to call
const counts = computed(() => {
  const out = { hearts: 0, diamonds: 0, clubs: 0, spades: 0 };
  for (const c of state.game?.your_hand || []) {
    if (c.rank !== 11) out[c.suit] += 1;
  }
  return out;
});
const best = computed(() => Math.max(...Object.values(counts.value)));
</script>

<template>
  <div class="modal-backdrop clear">
    <div class="modal">
      <p class="overline">Валет сыгран</p>
      <h3>Выберите масть</h3>
      <div class="suit-grid">
        <button
          v-for="s in SUITS"
          :key="s.id"
          class="suit-btn"
          :class="{ red: s.red, best: best > 0 && counts[s.id] === best }"
          :title="s.name"
          @click="declareSuit(s.id)"
        >
          <span class="suit-symbol">{{ s.symbol }}</span>
          <span class="suit-count">{{ counts[s.id] }} на руке</span>
        </button>
      </div>
      <p class="suit-hint">Отмечена масть, которой у вас больше всего</p>
    </div>
  </div>
</template>
