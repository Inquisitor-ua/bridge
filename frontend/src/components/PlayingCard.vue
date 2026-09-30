<script setup>
import { computed } from "vue";

const props = defineProps({
  card: { type: Object, default: null }, // { rank, suit } — null for a face-down deck card
  faceDown: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  playable: { type: Boolean, default: false },
});

const RANK_LABEL = { 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A" };
const SUIT_SYMBOL = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };

const label = computed(() => (props.card ? RANK_LABEL[props.card.rank] : ""));
const symbol = computed(() => (props.card ? SUIT_SYMBOL[props.card.suit] : ""));
const isRed = computed(() => props.card && (props.card.suit === "hearts" || props.card.suit === "diamonds"));
</script>

<template>
  <div
    class="card"
    :class="{ 'face-down': faceDown, red: isRed, selected, playable }"
  >
    <template v-if="!faceDown && card">
      <span class="corner top">
        <span class="corner-rank">{{ label }}</span>
        <span class="corner-suit">{{ symbol }}</span>
      </span>
      <span class="pip">{{ symbol }}</span>
      <span class="corner bottom">
        <span class="corner-rank">{{ label }}</span>
        <span class="corner-suit">{{ symbol }}</span>
      </span>
    </template>
    <span v-else-if="faceDown" class="card-back-emblem">♠</span>
  </div>
</template>
