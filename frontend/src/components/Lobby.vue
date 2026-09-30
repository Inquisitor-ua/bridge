<script setup>
import { ref } from "vue";
import { createRoom, joinRoom } from "../store.js";

const name = ref(localStorage.getItem("bridge_name") || "");
const roomCode = ref("");
const mode = ref("create"); // "create" | "join"

function persistName() {
  localStorage.setItem("bridge_name", name.value);
}

function submit() {
  if (!name.value.trim()) return;
  persistName();
  if (mode.value === "create") {
    createRoom(name.value.trim());
  } else {
    if (!roomCode.value.trim()) return;
    joinRoom(roomCode.value.trim().toUpperCase(), name.value.trim());
  }
}
</script>

<template>
  <div class="lobby">
    <div class="lobby-card">
      <div class="tabs">
        <button :class="{ active: mode === 'create' }" @click="mode = 'create'">Создать комнату</button>
        <button :class="{ active: mode === 'join' }" @click="mode = 'join'">Войти в комнату</button>
      </div>

      <label class="field">
        <span>Ваше имя</span>
        <input v-model="name" maxlength="24" placeholder="Имя игрока" @keyup.enter="submit" />
      </label>

      <label v-if="mode === 'join'" class="field">
        <span>Код комнаты</span>
        <input v-model="roomCode" maxlength="4" placeholder="ABCD" style="text-transform: uppercase" @keyup.enter="submit" />
      </label>

      <button class="primary" @click="submit">
        {{ mode === "create" ? "Создать" : "Войти" }}
      </button>
    </div>
  </div>
</template>
