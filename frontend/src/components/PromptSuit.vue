<script setup>
import { declareSuit } from "../store.js";

const SUITS = [
  { id: "hearts", symbol: "♥", red: true },
  { id: "diamonds", symbol: "♦", red: true },
  { id: "clubs", symbol: "♣", red: false },
  { id: "spades", symbol: "♠", red: false },
];
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal">
      <h3>Выберите масть</h3>
      <div class="suit-grid">
        <button
          v-for="s in SUITS"
          :key="s.id"
          class="suit-btn"
          :class="{ red: s.red }"
          @click="declareSuit(s.id)"
        >
          {{ s.symbol }}
        </button>
      </div>
    </div>
  </div>
</template>
