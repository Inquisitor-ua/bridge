<script setup>
import { ref, computed } from "vue";
import { createRoom, joinRoom } from "../store.js";
import { auth } from "../auth.js";
import PlayingCard from "./PlayingCard.vue";

const name = ref(localStorage.getItem("bridge_name") || "");
const roomCode = ref("");
const mode = ref("create"); // "create" | "join"

const HERO_CARDS = [
  { rank: 14, suit: "spades" },
  { rank: 13, suit: "hearts" },
  { rank: 12, suit: "clubs" },
  { rank: 11, suit: "diamonds" },
];

// a logged-in player always plays under their profile name (the server
// substitutes it too); a guest types one
const playerName = computed(() => (auth.user ? auth.user.display_name : name.value.trim()));

function persistName() {
  if (!auth.user) localStorage.setItem("bridge_name", name.value);
}

function submit() {
  if (!playerName.value) return;
  persistName();
  if (mode.value === "create") {
    createRoom(playerName.value);
  } else {
    if (!roomCode.value.trim()) return;
    joinRoom(roomCode.value.trim().toUpperCase(), playerName.value);
  }
}
</script>

<template>
  <div class="lobby">
    <section class="lobby-hero">
      <div class="hero-fan" aria-hidden="true">
        <div v-for="(c, i) in HERO_CARDS" :key="i" class="hero-fan-card" :style="{ '--i': i - 1.5 }">
          <PlayingCard :card="c" />
        </div>
      </div>
      <p class="overline">Карточная игра · 2–6 игроков</p>
      <h1 class="hero-title">Бридж</h1>
      <p class="hero-sub">Избавьтесь от карт первым — и не перешагните 125 очков.</p>
    </section>

    <section class="lobby-card">
      <div class="segmented">
        <button :class="{ active: mode === 'create' }" @click="mode = 'create'">Создать</button>
        <button :class="{ active: mode === 'join' }" @click="mode = 'join'">Присоединиться</button>
        <span class="segmented-thumb" :class="{ right: mode === 'join' }"></span>
      </div>

      <div v-if="auth.user" class="field">
        <span>Имя</span>
        <p class="lobby-as">Вы играете как <b>{{ auth.user.display_name }}</b></p>
      </div>
      <label v-else class="field">
        <span>Имя</span>
        <input v-model="name" maxlength="24" placeholder="Как вас называть" @keyup.enter="submit" />
      </label>

      <Transition name="field">
        <label v-if="mode === 'join'" class="field">
          <span>Код комнаты</span>
          <input
            v-model="roomCode"
            class="code-input"
            maxlength="4"
            placeholder="ABCD"
            autocomplete="off"
            spellcheck="false"
            @keyup.enter="submit"
          />
        </label>
      </Transition>

      <button class="primary block" :disabled="!playerName || (mode === 'join' && !roomCode.trim())" @click="submit">
        {{ mode === "create" ? "Создать комнату" : "Войти в комнату" }}
      </button>
    </section>
  </div>
</template>
