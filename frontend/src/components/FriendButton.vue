<script setup>
import { ref, computed } from "vue";
import { auth } from "../auth.js";
import { friends, sendFriendRequest, acceptFriendRequest, dropFriendRequest } from "../friends.js";

// "add friend" for someone else's profile; its look follows where the two
// of you stand, read from the already loaded friend lists
const props = defineProps({
  username: { type: String, required: true },
});

const busy = ref(false);
const error = ref("");

const same = (a, b) => a.toLowerCase() === b.toLowerCase();
const has = (list) => list.some((f) => same(f.username, props.username));

// null = nothing to show (guest, own profile, lists not loaded yet)
const relation = computed(() => {
  if (!auth.user || !friends.loaded || same(auth.user.username, props.username)) return null;
  if (has(friends.list)) return "friend";
  if (has(friends.incoming)) return "incoming";
  if (has(friends.outgoing)) return "outgoing";
  return "none";
});

async function run(action) {
  busy.value = true;
  error.value = "";
  try {
    await action(props.username);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <span v-if="relation" class="friend-button">
    <button v-if="relation === 'none'" class="primary small" :disabled="busy" @click="run(sendFriendRequest)">
      Добавить в друзья
    </button>
    <button v-else-if="relation === 'incoming'" class="primary small" :disabled="busy" @click="run(acceptFriendRequest)">
      Принять заявку в друзья
    </button>
    <template v-else-if="relation === 'outgoing'">
      <span class="tag friend-tag">Заявка отправлена</span>
      <button class="ghost small" :disabled="busy" @click="run(dropFriendRequest)">Отменить</button>
    </template>
    <span v-else class="tag success friend-tag">✓ В друзьях</span>
    <span v-if="error" class="auth-error friend-button-error">{{ error }}</span>
  </span>
</template>
