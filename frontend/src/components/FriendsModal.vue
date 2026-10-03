<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { friends, loadFriends, sendFriendRequest, dropFriendRequest, removeFriend } from "../friends.js";
import { openProfile } from "../router.js";
import FriendRequests from "./FriendRequests.vue";
import UserAvatar from "./UserAvatar.vue";

const emit = defineEmits(["close"]);

const username = ref("");
const adding = ref(false);
const addError = ref("");
const addNotice = ref("");
const busy = ref(null);
const listError = ref("");

async function add() {
  const name = username.value.trim();
  if (!name || adding.value) return;
  adding.value = true;
  addError.value = "";
  addNotice.value = "";
  try {
    const res = await sendFriendRequest(name);
    addNotice.value =
      res.result === "accepted"
        ? `${res.user.display_name} теперь у вас в друзьях`
        : `Заявка отправлена: ${res.user.display_name}`;
    username.value = "";
  } catch (e) {
    addError.value = e.message;
  } finally {
    adding.value = false;
  }
}

async function run(key, action) {
  busy.value = key;
  listError.value = "";
  try {
    await action();
  } catch (e) {
    listError.value = e.message;
  } finally {
    busy.value = null;
  }
}

function remove(f) {
  if (!confirm(`Удалить ${f.display_name} из друзей?`)) return;
  run(f.username, () => removeFriend(f.username));
}

function showProfile(name) {
  emit("close");
  openProfile(name);
}

function onKey(ev) {
  if (ev.key === "Escape") emit("close");
}
onMounted(() => {
  window.addEventListener("keydown", onKey);
  loadFriends();
});
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="modal-backdrop friends-backdrop" @click.self="emit('close')">
    <div class="modal friends-modal" role="dialog" aria-label="Друзья">
      <button type="button" class="modal-close" aria-label="Закрыть" @click="emit('close')">✕</button>
      <p class="rs-kicker">Аккаунт</p>
      <h3>Друзья</h3>

      <form class="friends-add" @submit.prevent="add">
        <label class="field">
          <span>Добавить по логину</span>
          <div class="friends-add-row">
            <input
              v-model="username"
              maxlength="21"
              placeholder="логин друга"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
            />
            <button type="submit" class="primary" :disabled="!username.trim() || adding">Добавить</button>
          </div>
        </label>
        <p v-if="addError" class="auth-error">{{ addError }}</p>
        <p v-else-if="addNotice" class="friends-notice">{{ addNotice }}</p>
      </form>

      <template v-if="friends.incoming.length">
        <h4 class="pstats-group-title friends-section">Заявки в друзья · {{ friends.incoming.length }}</h4>
        <FriendRequests @navigate="emit('close')" />
      </template>

      <h4 class="pstats-group-title friends-section">
        Друзья<template v-if="friends.list.length"> · {{ friends.list.length }}</template>
      </h4>
      <p v-if="friends.loaded && !friends.list.length" class="profile-muted friends-empty">
        Пока никого. Добавьте друга по логину — он увидит заявку в главном меню.
      </p>
      <ul v-else class="friend-list">
        <li v-for="f in friends.list" :key="f.username" class="friend-row">
          <button class="friend-who" :title="`Профиль ${f.display_name}`" @click="showProfile(f.username)">
            <UserAvatar :name="f.display_name" :src="f.avatar_url" class="friend-avatar" :class="{ online: f.online }" />
            <span class="friend-names">
              <span class="friend-name">{{ f.display_name }}</span>
              <span class="friend-login">@{{ f.username }} · <span :class="{ 'friend-online': f.online }">{{ f.online ? "в сети" : "не в сети" }}</span></span>
            </span>
          </button>
          <span class="friend-actions">
            <button class="ghost small" @click="showProfile(f.username)">Профиль</button>
            <button class="ghost small danger-text" :disabled="busy === f.username" @click="remove(f)">Удалить</button>
          </span>
        </li>
      </ul>

      <template v-if="friends.outgoing.length">
        <h4 class="pstats-group-title friends-section">Ждут ответа</h4>
        <ul class="friend-list">
          <li v-for="f in friends.outgoing" :key="f.username" class="friend-row">
            <button class="friend-who" :title="`Профиль ${f.display_name}`" @click="showProfile(f.username)">
              <UserAvatar :name="f.display_name" :src="f.avatar_url" class="friend-avatar" />
              <span class="friend-names">
                <span class="friend-name">{{ f.display_name }}</span>
                <span class="friend-login">@{{ f.username }}</span>
              </span>
            </button>
            <span class="friend-actions">
              <button class="ghost small" :disabled="busy === f.username" @click="run(f.username, () => dropFriendRequest(f.username))">
                Отменить
              </button>
            </span>
          </li>
        </ul>
      </template>

      <p v-if="listError" class="auth-error friend-error">{{ listError }}</p>
    </div>
  </div>
</template>
