<script setup>
import { ref } from "vue";
import { friends, acceptFriendRequest, dropFriendRequest } from "../friends.js";
import { openProfile } from "../router.js";
import UserAvatar from "./UserAvatar.vue";

// incoming friend requests with accept / decline; used in the lobby and in
// the friends window
const emit = defineEmits(["navigate"]);

const busy = ref(null); // username being answered
const error = ref("");

async function answer(username, accept) {
  busy.value = username;
  error.value = "";
  try {
    await (accept ? acceptFriendRequest(username) : dropFriendRequest(username));
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = null;
  }
}

function showProfile(username) {
  emit("navigate");
  openProfile(username);
}
</script>

<template>
  <ul class="friend-list">
    <li v-for="r in friends.incoming" :key="r.username" class="friend-row">
      <button class="friend-who" :title="`Профиль ${r.display_name}`" @click="showProfile(r.username)">
        <UserAvatar :name="r.display_name" :src="r.avatar_url" class="friend-avatar" />
        <span class="friend-names">
          <span class="friend-name">{{ r.display_name }}</span>
          <span class="friend-login">@{{ r.username }}</span>
        </span>
      </button>
      <span class="friend-actions">
        <button class="primary small" :disabled="busy === r.username" @click="answer(r.username, true)">Принять</button>
        <button class="ghost small" :disabled="busy === r.username" @click="answer(r.username, false)">Отклонить</button>
      </span>
    </li>
  </ul>
  <p v-if="error" class="auth-error friend-error">{{ error }}</p>
</template>
