import { reactive } from "vue";

const WS_URL = (() => {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws`;
})();

const LS_KEY = "bridge_session";

export const state = reactive({
  connected: false,
  room: null,
  playerId: null,
  hostId: null,
  error: null,
  // full room/game state as sent by the server ("state" message minus the "type" field)
  game: null,
  // emotes on screen right now: player id -> { emoji, id }
  emotes: {},
});

export const EMOTES = ["😂", "😎", "😍", "🤔", "😱", "😭", "😡", "🥱", "👍", "👎", "👏", "🔥"];
const EMOTE_SHOW_MS = 3000;
const emoteTimers = {};
let emoteSeq = 0;

function showEmote(playerId, emoji) {
  if (!EMOTES.includes(emoji)) return;
  clearTimeout(emoteTimers[playerId]);
  // a fresh id restarts the pop animation when the same player sends another
  state.emotes[playerId] = { emoji, id: ++emoteSeq };
  emoteTimers[playerId] = setTimeout(() => delete state.emotes[playerId], EMOTE_SHOW_MS);
}

function clearEmotes() {
  for (const pid of Object.keys(emoteTimers)) {
    clearTimeout(emoteTimers[pid]);
    delete emoteTimers[pid];
  }
  state.emotes = {};
}

let socket = null;
let queuedMessages = [];

function saveSession() {
  if (state.room && state.playerId) {
    localStorage.setItem(LS_KEY, JSON.stringify({ room: state.room, playerId: state.playerId }));
  }
}

function loadSession() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function clearSession() {
  localStorage.removeItem(LS_KEY);
}

function send(payload) {
  const data = JSON.stringify(payload);
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(data);
  } else {
    queuedMessages.push(data);
  }
}

function handleMessage(msg) {
  if (msg.type === "joined") {
    state.room = msg.room;
    state.playerId = msg.player_id;
    state.hostId = msg.host_id;
    state.error = null;
    saveSession();
  } else if (msg.type === "state") {
    state.hostId = msg.host_id;
    state.game = msg;
  } else if (msg.type === "emote") {
    showEmote(msg.player_id, msg.emoji);
  } else if (msg.type === "error") {
    showError(msg.message);
  }
}

// the error banner hides itself; a repeated error restarts the wait
const ERROR_SHOW_MS = 4000;
let errorTimer = null;

function showError(message) {
  state.error = message;
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => (state.error = null), ERROR_SHOW_MS);
}

export function connect() {
  if (socket) return;
  socket = new WebSocket(WS_URL);

  socket.addEventListener("open", () => {
    state.connected = true;
    for (const data of queuedMessages) socket.send(data);
    queuedMessages = [];

    const saved = loadSession();
    if (saved && saved.room && saved.playerId) {
      send({ type: "rejoin", room: saved.room, player_id: saved.playerId });
    }
  });

  const ws = socket;
  ws.addEventListener("close", () => {
    // ignore a socket that reconnectNow() already replaced
    if (socket !== ws) return;
    state.connected = false;
    socket = null;
    setTimeout(connect, 1500);
  });

  ws.addEventListener("message", (ev) => {
    handleMessage(JSON.parse(ev.data));
  });
}

// Mobile browsers and installed PWAs drop the socket while the app is in the
// background; reconnect (and rejoin via the saved session) as soon as it's back
// instead of waiting for the close event and the retry timer.
function reconnectNow() {
  if (socket && socket.readyState === WebSocket.OPEN) return;
  if (socket && socket.readyState === WebSocket.CONNECTING) return;
  const old = socket;
  socket = null;
  state.connected = false;
  if (old) old.close();
  connect();
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") reconnectNow();
});
window.addEventListener("online", reconnectNow);

export function createRoom(name) {
  send({ type: "create_room", name });
}

export function joinRoom(room, name) {
  send({ type: "join_room", room, name });
}

export function startGame() {
  send({ type: "start_game" });
}

export function playCards(cards) {
  send({ type: "play_cards", cards });
}

export function drawCard() {
  send({ type: "draw_card" });
}

export function passTurn() {
  send({ type: "pass_turn" });
}

export function declareSuit(suit) {
  send({ type: "declare_suit", suit });
}

export function declareBridge(accept) {
  send({ type: "declare_bridge", accept });
}

export function jackEndChoice(choice) {
  send({ type: "jack_end_choice", choice });
}

export function continueRound() {
  send({ type: "continue_round" });
}

export function voteRematch() {
  send({ type: "rematch" });
}

export function sendEmote(emoji) {
  send({ type: "emote", emoji });
}

export function leaveRoom() {
  // tell the server first so the player is removed from the room (lobby) or
  // forfeits (running game); the socket itself stays open for the lobby
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "leave_room" }));
  }
  clearSession();
  state.room = null;
  state.playerId = null;
  state.hostId = null;
  state.game = null;
  state.error = null;
  clearEmotes();
}
