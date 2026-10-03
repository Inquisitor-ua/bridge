import { reactive, watch } from "vue";
import { auth } from "./auth.js";
import { state, onMessage, joinRoom, leaveRoom } from "./store.js";

export const friends = reactive({
  list: [], // { username, display_name, avatar_url, online }
  incoming: [], // requests to me
  outgoing: [], // requests I sent
  loaded: false,
  // room invites from friends: { key, room, from: { name, username, avatar_url } }
  invites: [],
});

const INVITE_TTL_MS = 60000;

async function call(method, path, body) {
  const res = await fetch(`/api/friends${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "ошибка сервера");
  return data;
}

export async function loadFriends() {
  if (!auth.user) return;
  try {
    const data = await call("GET", "");
    friends.list = data.friends;
    friends.incoming = data.incoming;
    friends.outgoing = data.outgoing;
    friends.loaded = true;
  } catch {
    // keep the last known lists; the next push or action reloads them
  }
}

function reset() {
  friends.list = [];
  friends.incoming = [];
  friends.outgoing = [];
  friends.invites = [];
  friends.loaded = false;
}

// every change goes through the server and then reloads the lists, so all
// screens show the same thing
async function act(method, path, body) {
  const data = await call(method, path, body);
  await loadFriends();
  return data;
}

export const sendFriendRequest = (username) => act("POST", "/requests", { username });
export const acceptFriendRequest = (username) => act("POST", `/requests/${encodeURIComponent(username)}/accept`);
// declines a request to me, or cancels one I sent
export const dropFriendRequest = (username) => act("DELETE", `/requests/${encodeURIComponent(username)}`);
export const removeFriend = (username) => act("DELETE", `/${encodeURIComponent(username)}`);

watch(
  () => auth.user?.username,
  (username) => (username ? loadFriends() : reset()),
  { immediate: true },
);

// the server pushes this whenever someone's request, friendship or online
// status touches my lists
onMessage("friends_changed", loadFriends);

// ---- room invites ----

const inviteTimers = {};

export function dismissInvite(key) {
  clearTimeout(inviteTimers[key]);
  delete inviteTimers[key];
  friends.invites = friends.invites.filter((i) => i.key !== key);
}

onMessage("invite", (msg) => {
  // one invite per friend: a newer one replaces the older
  const key = msg.from.username;
  dismissInvite(key);
  if (state.room === msg.room) return; // already there
  friends.invites.push({ key, room: msg.room, from: msg.from });
  inviteTimers[key] = setTimeout(() => dismissInvite(key), INVITE_TTL_MS);
});

export function acceptInvite(invite) {
  if (state.room && state.room !== invite.room) {
    const inGame = state.game?.started && !state.game.game_over;
    const question = inGame
      ? "Вы сейчас в игре. Выйти из неё и перейти в комнату друга? Вы выбудете из текущей партии."
      : "Выйти из текущей комнаты и перейти в комнату друга?";
    if (!confirm(question)) return;
    leaveRoom();
  }
  dismissInvite(invite.key);
  if (state.room !== invite.room) joinRoom(invite.room, auth.user?.display_name || "Игрок");
}
