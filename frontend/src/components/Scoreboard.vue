<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { state, EMOTES, sendEmote } from "../store.js";
import UserAvatar from "./UserAvatar.vue";
import PlayerCard from "./PlayerCard.vue";

const props = defineProps({
  // cards still in flight towards a player's hand, keyed by player id --
  // they are left out of the mini hand until they land
  incoming: { type: Object, default: () => ({}) },
});

const MAX_BACKS = 12;

const players = computed(() => state.game?.players || []);
const turnId = computed(() => state.game?.turn_player_id);

function shownBacks(p) {
  return Math.min(Math.max(p.hand_count - (props.incoming[p.id] || 0), 0), MAX_BACKS);
}

// ---- another player's chip opens their mini profile (accounts only: a
// guest has no profile to show) ----
const cardPlayer = ref(null);

function canOpenCard(p) {
  return p.id !== state.playerId && !!p.username;
}

function openCard(p) {
  if (canOpenCard(p)) cardPlayer.value = p;
}

// ---- emotes: the button sits in my own chip, the picker drops under the board ----
const pickerOpen = ref(false);

function pickEmote(emoji) {
  sendEmote(emoji);
  pickerOpen.value = false;
}

function onOutsidePointer(ev) {
  if (pickerOpen.value && !ev.target.closest?.(".emote-btn, .emote-picker")) pickerOpen.value = false;
}
onMounted(() => document.addEventListener("pointerdown", onOutsidePointer));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onOutsidePointer));
</script>

<template>
  <div class="scoreboard-wrap">
    <ul class="scoreboard">
      <li
        v-for="p in players"
        :key="p.id"
        class="player-chip"
        :class="{ turn: p.id === turnId, eliminated: p.eliminated, me: p.id === state.playerId, clickable: canOpenCard(p) }"
        :role="canOpenCard(p) ? 'button' : undefined"
        :tabindex="canOpenCard(p) ? 0 : undefined"
        :title="canOpenCard(p) ? 'Открыть профиль' : undefined"
        @click="openCard(p)"
        @keydown.enter.space.prevent="openCard(p)"
      >
        <UserAvatar :name="p.name" :src="p.avatar_url" :bot="!!p.bot_level" :class="{ off: !p.connected }">
          <!-- the emote covers the sender's own avatar, so nothing on the table is hidden -->
          <Transition name="emote">
            <span v-if="state.emotes[p.id]" :key="state.emotes[p.id].id" class="emote-bubble">{{ state.emotes[p.id].emoji }}</span>
          </Transition>
        </UserAvatar>
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
        <button
          v-if="p.id === state.playerId"
          class="ghost small emote-btn"
          title="Смайлы"
          aria-label="Смайлы"
          :aria-expanded="pickerOpen"
          @click="pickerOpen = !pickerOpen"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M8.5 14.5a4.5 4.5 0 0 0 7 0M9 9.5v.5M15 9.5v.5" />
          </svg>
        </button>
      </li>
    </ul>

    <PlayerCard v-if="cardPlayer" :player="cardPlayer" @close="cardPlayer = null" />

    <Transition name="picker">
      <div v-if="pickerOpen" class="emote-picker">
        <button v-for="e in EMOTES" :key="e" class="emote-option" @click="pickEmote(e)">{{ e }}</button>
      </div>
    </Transition>
  </div>
</template>
