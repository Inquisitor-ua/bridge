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
});

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
  } else if (msg.type === "error") {
    state.error = msg.message;
  }
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

  socket.addEventListener("close", () => {
    state.connected = false;
    socket = null;
    setTimeout(connect, 1500);
  });

  socket.addEventListener("message", (ev) => {
    handleMessage(JSON.parse(ev.data));
  });
}

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
}
