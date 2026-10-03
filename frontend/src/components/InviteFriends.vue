<script setup>
import { reactive, computed, watch, onMounted, onBeforeUnmount } from "vue";
import { state, inviteFriend, onMessage } from "../store.js";
import { friends, loadFriends } from "../friends.js";
import UserAvatar from "./UserAvatar.vue";

// the waiting room's "call a friend" list; the invite itself goes over the
// game socket, the server checks friendship / online / cooldown
const SENT_SHOW_MS = 15000; // matches the server's per-friend cooldown

const sent = reactive({}); // username -> true while "Отправлено" shows
const timers = {};

const inRoom = computed(() => new Set((state.game?.lobby_players || []).map((p) => p.username).filter(Boolean)));

function status(f) {
  if (inRoom.value.has(f.username)) return "в комнате";
  if (!f.online) return "не в сети";
  return sent[f.username] ? "приглашение отправлено" : "в сети";
}

// a friend who came in has answered the invite: forget it, so if they leave
// again they can be called right away
watch(inRoom, (names) => {
  for (const name of names) {
    clearTimeout(timers[name]);
    delete sent[name];
  }
});

function canInvite(f) {
  return f.online && !inRoom.value.has(f.username) && !sent[f.username];
}

const off = onMessage("invite_sent", (msg) => {
  sent[msg.username] = true;
  clearTimeout(timers[msg.username]);
  timers[msg.username] = setTimeout(() => delete sent[msg.username], SENT_SHOW_MS);
});
onMounted(loadFriends);
onBeforeUnmount(() => {
  off();
  Object.values(timers).forEach(clearTimeout);
});
</script>

<template>
  <div class="invite-friends">
    <div class="seat-header">
      <span>Позвать друзей</span>
      <span class="seat-count">{{ friends.list.filter((f) => f.online).length }} в сети</span>
    </div>
    <p v-if="friends.loaded && !friends.list.length" class="invite-empty">
      Друзей пока нет — добавьте их в меню «Друзья» в шапке.
    </p>
    <ul v-else class="friend-list">
      <li v-for="f in friends.list" :key="f.username" class="friend-row" :class="{ offline: !f.online }">
        <span class="friend-who static">
          <UserAvatar :name="f.display_name" :src="f.avatar_url" class="friend-avatar" :class="{ online: f.online }" />
          <span class="friend-names">
            <span class="friend-name">{{ f.display_name }}</span>
            <span class="friend-login" :class="{ 'friend-online': f.online && !inRoom.has(f.username) }">{{ status(f) }}</span>
          </span>
        </span>
        <button class="ghost small" :disabled="!canInvite(f)" @click="inviteFriend(f.username)">Позвать</button>
      </li>
    </ul>
  </div>
</template>
