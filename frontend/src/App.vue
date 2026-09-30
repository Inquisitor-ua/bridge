<script setup>
import { computed } from "vue";
import { state, leaveRoom } from "./store.js";
import Lobby from "./components/Lobby.vue";
import WaitingRoom from "./components/WaitingRoom.vue";
import GameTable from "./components/GameTable.vue";

const inRoom = computed(() => !!state.room && !!state.playerId);
const started = computed(() => inRoom.value && state.game && state.game.started);

function onLeave() {
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

      <div class="header-meta">
        <span v-if="state.room" class="room-code">
          <span class="room-code-label">Комната</span>
          <span class="room-code-value">{{ state.room }}</span>
        </span>
        <span class="conn" :class="{ ok: state.connected }" :title="state.connected ? 'подключено' : 'нет связи'">
          <span class="conn-dot"></span>
          <span class="conn-label">{{ state.connected ? "online" : "offline" }}</span>
        </span>
        <button v-if="inRoom" class="ghost small" @click="onLeave">Выйти</button>
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
  </div>
</template>
