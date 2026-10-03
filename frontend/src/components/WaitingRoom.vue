<script setup>
import { ref, computed } from "vue";
import { state, startGame, leaveRoom } from "../store.js";
import UserAvatar from "./UserAvatar.vue";
import InviteFriends from "./InviteFriends.vue";
import { auth } from "../auth.js";

const MAX_PLAYERS = 6;

const players = computed(() => state.game?.lobby_players || []);
const isHost = computed(() => state.playerId === state.hostId);
const canStart = computed(() => players.value.length >= 2 && players.value.length <= MAX_PLAYERS);
const emptySeats = computed(() => Math.max(0, MAX_PLAYERS - players.value.length));

const copied = ref(false);
function copyCode() {
  navigator.clipboard?.writeText(state.room).then(() => {
    copied.value = true;
    setTimeout(() => (copied.value = false), 1400);
  });
}
</script>

<template>
  <div class="waiting">
    <div class="waiting-card">
      <p class="overline">Код комнаты</p>
      <button class="room-big" :title="'Скопировать код'" @click="copyCode">
        <span v-for="(ch, i) in state.room" :key="i" class="room-big-char">{{ ch }}</span>
      </button>
      <p class="waiting-hint">{{ copied ? "Код скопирован" : "Поделитесь кодом с друзьями — нажмите, чтобы скопировать" }}</p>

      <div class="seat-header">
        <span>Игроки</span>
        <span class="seat-count">{{ players.length }} / {{ MAX_PLAYERS }}</span>
      </div>

      <TransitionGroup tag="ul" name="seat" class="seat-list">
        <li v-for="p in players" :key="p.id" class="seat" :class="{ me: p.id === state.playerId }">
          <UserAvatar :name="p.name" :src="p.avatar_url" :bot="!!p.bot_level" />
          <span class="seat-name">{{ p.name }}</span>
          <span v-if="p.id === state.hostId" class="tag gold">хост</span>
          <span v-if="p.id === state.playerId" class="tag">вы</span>
        </li>
        <li v-for="n in emptySeats" :key="'empty-' + n" class="seat empty">
          <span class="avatar"></span>
          <span class="seat-name">Свободное место</span>
        </li>
      </TransitionGroup>

      <InviteFriends v-if="auth.user" />

      <div class="waiting-actions">
        <button v-if="isHost" class="primary block" :disabled="!canStart" @click="startGame">
          {{ canStart ? "Начать игру" : "Нужно минимум 2 игрока" }}
        </button>
        <p v-else class="waiting-note">
          <span class="pulse-dot"></span>
          Ожидаем, пока хост начнёт игру
        </p>
        <button class="ghost block" @click="leaveRoom">Покинуть комнату</button>
      </div>
    </div>
  </div>
</template>
