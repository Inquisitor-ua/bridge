<script setup>
import { computed } from "vue";
import { state, startGame, leaveRoom } from "../store.js";

const players = computed(() => state.game?.lobby_players || []);
const isHost = computed(() => state.playerId === state.hostId);
const canStart = computed(() => players.value.length >= 2 && players.value.length <= 6);
</script>

<template>
  <div class="waiting">
    <h2>Комната {{ state.room }}</h2>
    <p>Ждём игроков (от 2 до 6)…</p>
    <ul class="player-list">
      <li v-for="p in players" :key="p.id">
        {{ p.name }}
        <span v-if="p.id === state.hostId" class="badge">хост</span>
        <span v-if="p.id === state.playerId" class="badge me">вы</span>
      </li>
    </ul>

    <button v-if="isHost" class="primary" :disabled="!canStart" @click="startGame">
      Начать игру ({{ players.length }}/6)
    </button>
    <p v-else>Ждите, пока хост начнёт игру.</p>

    <button class="ghost" @click="leaveRoom">Выйти</button>
  </div>
</template>
