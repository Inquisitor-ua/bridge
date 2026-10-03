<script setup>
import { ref, computed } from "vue";
import { createRoom, joinRoom, createBotGame } from "../store.js";
import { auth } from "../auth.js";
import { friends } from "../friends.js";
import FriendRequests from "./FriendRequests.vue";
import PlayingCard from "./PlayingCard.vue";

const name = ref(localStorage.getItem("bridge_name") || "");
const roomCode = ref("");
const MODES = ["create", "join", "bots"];
const mode = ref("create");

// a game against the computer: the choices are remembered for next time
const BOT_LEVELS = [
  { id: "easy", label: "Лёгкий", hint: "Ходит наугад и часто ошибается" },
  { id: "medium", label: "Средний", hint: "Сбрасывает дорогие карты и бережёт валетов" },
  { id: "hard", label: "Сложный", hint: "Считает вышедшие карты и просчитывает раздачу наперёд" },
];
const BOT_COUNTS = [1, 2, 3, 4, 5];
const botLevel = ref(readSetting("bridge_bot_level", BOT_LEVELS.map((l) => l.id), "medium"));
const botCount = ref(Number(readSetting("bridge_bot_count", BOT_COUNTS.map(String), "1")));
const botHint = computed(() => BOT_LEVELS.find((l) => l.id === botLevel.value).hint);

function readSetting(key, allowed, fallback) {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

function saveSetting(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // storage blocked: the choice just isn't remembered
  }
}

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
  } else if (mode.value === "bots") {
    saveSetting("bridge_bot_level", botLevel.value);
    saveSetting("bridge_bot_count", botCount.value);
    createBotGame(playerName.value, botLevel.value, botCount.value);
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
      <div class="segmented" :style="{ '--seg-n': MODES.length, '--seg-i': MODES.indexOf(mode) }">
        <button :class="{ active: mode === 'create' }" @click="mode = 'create'">Создать</button>
        <button :class="{ active: mode === 'join' }" @click="mode = 'join'">Войти</button>
        <button :class="{ active: mode === 'bots' }" @click="mode = 'bots'">С ботами</button>
        <span class="segmented-thumb"></span>
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

      <Transition name="field">
        <div v-if="mode === 'bots'" class="field">
          <span>Сложность</span>
          <div
            class="segmented compact"
            role="radiogroup"
            aria-label="Сложность"
            :style="{ '--seg-n': BOT_LEVELS.length, '--seg-i': BOT_LEVELS.findIndex((l) => l.id === botLevel) }"
          >
            <button
              v-for="l in BOT_LEVELS"
              :key="l.id"
              role="radio"
              :aria-checked="botLevel === l.id"
              :class="{ active: botLevel === l.id }"
              @click="botLevel = l.id"
            >
              {{ l.label }}
            </button>
            <span class="segmented-thumb"></span>
          </div>
          <p class="bot-level-hint">{{ botHint }}</p>
        </div>
      </Transition>

      <Transition name="field">
        <div v-if="mode === 'bots'" class="field">
          <span>Соперников</span>
          <div
            class="segmented compact"
            role="radiogroup"
            aria-label="Число соперников"
            :style="{ '--seg-n': BOT_COUNTS.length, '--seg-i': BOT_COUNTS.indexOf(botCount) }"
          >
            <button
              v-for="n in BOT_COUNTS"
              :key="n"
              role="radio"
              :aria-checked="botCount === n"
              :class="{ active: botCount === n }"
              @click="botCount = n"
            >
              {{ n }}
            </button>
            <span class="segmented-thumb"></span>
          </div>
        </div>
      </Transition>

      <button class="primary block" :disabled="!playerName || (mode === 'join' && !roomCode.trim())" @click="submit">
        {{ { create: "Создать комнату", join: "Войти в комнату", bots: botCount > 1 ? "Играть против ботов" : "Играть против бота" }[mode] }}
      </button>
    </section>

    <section v-if="auth.user && friends.incoming.length" class="lobby-card lobby-requests">
      <h4 class="pstats-group-title">Заявки в друзья · {{ friends.incoming.length }}</h4>
      <FriendRequests />
    </section>
  </div>
</template>
