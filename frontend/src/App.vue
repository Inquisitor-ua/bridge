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
  <div class="app-shell">
    <header class="app-header">
      <h1>Бридж</h1>
      <span v-if="state.room" class="room-code">Комната: {{ state.room }}</span>
      <span class="conn-dot" :class="{ ok: state.connected }" :title="state.connected ? 'подключено' : 'нет связи'"></span>
      <button v-if="inRoom" class="ghost leave-btn" @click="onLeave">Выйти</button>
    </header>

    <p v-if="state.error" class="error-banner">{{ state.error }}</p>

    <Lobby v-if="!inRoom" />
    <GameTable v-else-if="started" />
    <WaitingRoom v-else />
  </div>
</template>
