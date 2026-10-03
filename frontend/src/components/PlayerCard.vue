<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { fetchUser, fetchUserStats } from "../auth.js";
import { openProfile } from "../router.js";
import UserAvatar from "./UserAvatar.vue";
import FriendButton from "./FriendButton.vue";

// A quick look at another player from the table: who they are and how they
// usually do. The game keeps running underneath.
const props = defineProps({
  // a player from the game state: { name, avatar_url, username }
  player: { type: Object, required: true },
});
const emit = defineEmits(["close"]);

const user = ref(null);
const stats = ref(null);
const error = ref("");

// shown straight away from the game state, replaced by fresh data on arrival
const name = computed(() => user.value?.display_name || props.player.name);
const avatar = computed(() => (user.value ? user.value.avatar_url : props.player.avatar_url));
const since = computed(() =>
  user.value ? new Date(user.value.created_at * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }) : "",
);
const winRate = computed(() => (stats.value?.games ? Math.round((stats.value.wins / stats.value.games) * 100) : 0));

onMounted(async () => {
  try {
    [user.value, stats.value] = await Promise.all([fetchUser(props.player.username), fetchUserStats(props.player.username)]);
  } catch (e) {
    error.value = e.message;
  }
});

function goToProfile() {
  emit("close");
  openProfile(props.player.username);
}

function onKey(ev) {
  if (ev.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="modal-backdrop player-card-backdrop" @click.self="emit('close')">
    <div class="modal player-card" role="dialog" :aria-label="`Профиль: ${name}`">
      <button type="button" class="modal-close" aria-label="Закрыть" @click="emit('close')">✕</button>

      <UserAvatar :name="name" :src="avatar" class="player-card-avatar" />
      <h3 class="player-card-name">{{ name }}</h3>
      <p class="player-card-sub">
        @{{ player.username }}<template v-if="since"> · в игре с {{ since }}</template>
      </p>

      <p v-if="error" class="auth-error">{{ error }}</p>
      <p v-else-if="!stats" class="profile-muted player-card-loading">Загрузка…</p>
      <p v-else-if="!stats.games" class="profile-muted player-card-loading">Ещё не сыграл(а) ни одной партии</p>
      <div v-else class="player-card-stats">
        <div class="kpi">
          <span class="kpi-label">Партий</span>
          <span class="kpi-value">{{ stats.games }}</span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Побед</span>
          <span class="kpi-value">{{ stats.wins }}</span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Процент побед</span>
          <span class="kpi-value">{{ winRate }}%</span>
          <span class="meter" role="meter" aria-label="Процент побед" :aria-valuenow="winRate" aria-valuemin="0" aria-valuemax="100">
            <span class="meter-fill" :style="{ width: winRate + '%' }"></span>
          </span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Лучшая серия</span>
          <span class="kpi-value">{{ stats.best_streak }}</span>
        </div>
      </div>

      <div class="player-card-friend">
        <FriendButton :username="player.username" />
      </div>
      <button class="ghost block player-card-open" @click="goToProfile">Открыть профиль</button>
    </div>
  </div>
</template>
