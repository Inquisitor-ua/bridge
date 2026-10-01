<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { state, leaveRoom } from "./store.js";
import Lobby from "./components/Lobby.vue";
import WaitingRoom from "./components/WaitingRoom.vue";
import GameTable from "./components/GameTable.vue";
import RulesModal from "./components/RulesModal.vue";
import SoundControl from "./components/SoundControl.vue";

const inRoom = computed(() => !!state.room && !!state.playerId);
const started = computed(() => inRoom.value && state.game && state.game.started);
const rulesOpen = ref(false);

// phone header: the burger dropdown
const menuOpen = ref(false);
const metaEl = ref(null);

function onOutsidePointer(ev) {
  if (menuOpen.value && metaEl.value && !metaEl.value.contains(ev.target)) menuOpen.value = false;
}
onMounted(() => document.addEventListener("pointerdown", onOutsidePointer));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onOutsidePointer));

function openRules() {
  menuOpen.value = false;
  rulesOpen.value = true;
}

function onLeave() {
  menuOpen.value = false;
  const inProgress = started.value && !state.game.game_over;
  if (inProgress && !confirm("Выйти из игры? Вы выбудете из текущей партии.")) return;
  leaveRoom();
}
</script>

<template>
  <div class="app-shell" :class="{ 'is-lobby': !inRoom }">
    <header class="app-header">
      <div class="brand">
        <span class="brand-mark">♠</span>
        <span class="brand-name">Бридж</span>
      </div>

      <div ref="metaEl" class="header-meta">
        <span class="conn" :class="{ ok: state.connected }" :title="state.connected ? 'подключено' : 'нет связи'">
          <span class="conn-dot"></span>
          <span class="conn-label">{{ state.connected ? "online" : "offline" }}</span>
        </span>
        <button
          class="ghost small burger-btn"
          aria-label="Меню"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <path v-if="menuOpen" d="M6 6l12 12M18 6L6 18" />
            <path v-else d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
        <!-- desktop: laid out inline in the header; phones: a dropdown under the burger -->
        <div class="header-menu" :class="{ open: menuOpen }">
          <span v-if="state.room" class="room-code">
            <span class="room-code-label">Комната</span>
            <span class="room-code-value">{{ state.room }}</span>
          </span>
          <SoundControl />
          <button class="ghost small rules-btn" title="Правила игры" @click="openRules">
            <span class="rules-btn-q">?</span><span class="rules-btn-label">Правила</span>
          </button>
          <button v-if="inRoom" class="ghost small" @click="onLeave">Выйти</button>
        </div>
      </div>
    </header>

    <Transition name="banner">
      <p v-if="state.error" class="error-banner">{{ state.error }}</p>
    </Transition>

    <Transition name="view" mode="out-in">
      <Lobby v-if="!inRoom" key="lobby" />
      <GameTable v-else-if="started" key="game" />
      <WaitingRoom v-else key="waiting" />
    </Transition>

    <RulesModal v-if="rulesOpen" @close="rulesOpen = false" />
  </div>
</template>
