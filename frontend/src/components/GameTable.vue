<script setup>
import { ref, reactive, computed, watch, onUnmounted } from "vue";
import { state, playCards, drawCard, passTurn, leaveRoom, voteRematch } from "../store.js";
import { playTurnChime, playCardDraw, playCardPlace, playShuffle, playRoundEnd, playGameWin, playGameLose } from "../sound.js";
import PlayingCard from "./PlayingCard.vue";
import Scoreboard from "./Scoreboard.vue";
import PromptSuit from "./PromptSuit.vue";
import PromptBridge from "./PromptBridge.vue";
import PromptJackEnd from "./PromptJackEnd.vue";
import RoundSummary from "./RoundSummary.vue";
import CardFlight from "./CardFlight.vue";

const game = computed(() => state.game || {});
const myHand = computed(() => game.value.your_hand || []);
const isMyTurn = computed(() => game.value.turn_player_id === state.playerId);
const legalCards = computed(() => game.value.legal_cards || []);
const prompt = computed(() => game.value.prompt);
const DECK_SIZE = 36;

// nothing has been played yet: every card is in a hand, in the deck, or is
// the single opener on the table
function isFreshDeal(g) {
  if (!g || !g.round_active || !g.table_top || g.multiplier > 1) return false;
  const held = (g.players || []).reduce((sum, p) => sum + (p.eliminated ? 0 : p.hand_count), 0);
  return held + g.deck_count + 1 === DECK_SIZE;
}

// true while the opening deal is still flying out; the turn starts after it.
// Set from the start when the table opens straight onto a fresh deal.
const dealing = ref(isFreshDeal(state.game));
const canAct = computed(() => isMyTurn.value && !prompt.value && !dealing.value);
const mustCoverSix = computed(() => !!game.value.must_cover_six);
const myPrompt = computed(() => !dealing.value && prompt.value && prompt.value.player_id === state.playerId ? prompt.value : null);
const promptOwnerName = computed(() => {
  if (!prompt.value) return "";
  const p = (game.value.players || []).find((x) => x.id === prompt.value.player_id);
  return p ? p.name : "";
});
const turnPlayerName = computed(() => {
  const p = (game.value.players || []).find((x) => x.id === game.value.turn_player_id);
  return p ? p.name : "…";
});
// shown in place of the action buttons while there is nothing for me to do
const waitingText = computed(() => {
  if (canAct.value || myPrompt.value || game.value.awaiting_continue) return "";
  if (dealing.value) return "Раздаём карты";
  return prompt.value ? `Ждём решение: ${promptOwnerName.value}` : `Ждём ход: ${turnPlayerName.value}`;
});

// ---- "your turn" cue: table flash, vibration, chime, tab title ----
const BASE_TITLE = "Бридж";
const myTurnLive = computed(() => isMyTurn.value && !dealing.value && !game.value.awaiting_continue && !game.value.game_over);
const myTurnShown = computed(() => isMyTurn.value && !prompt.value && !dealing.value && !game.value.awaiting_continue);
const turnCue = ref(0); // > 0 while the flash is on the table; doubles as its key
const turnCueText = ref("Ваш ход");
let turnCueSeq = 0;
let turnCueTimer = null;

function announceTurn(text = "Ваш ход") {
  turnCueText.value = text;
  turnCue.value = ++turnCueSeq;
  clearTimeout(turnCueTimer);
  turnCueTimer = setTimeout(() => (turnCue.value = 0), 1300);
  try {
    navigator.vibrate?.(60);
  } catch {
    // vibration unsupported or blocked
  }
  playTurnChime();
}

watch(
  myTurnLive,
  (mine) => {
    document.title = mine ? `● Ваш ход — ${BASE_TITLE}` : BASE_TITLE;
    if (mine) announceTurn();
  },
  { immediate: true }
);

onUnmounted(() => {
  clearTimeout(turnCueTimer);
  cancelDeal();
  document.title = BASE_TITLE;
});

// ---- end-of-round summary ----
// shown while the server waits for everyone's "continue"; after the final
// round (game over) it stays up until this viewer closes it locally
const dismissedSummary = ref(null);
const roundSummary = computed(() => {
  const s = game.value.round_summary;
  if (!s || dismissedSummary.value === s.number) return null;
  return game.value.awaiting_continue || game.value.game_over ? s : null;
});

// a rematch restarts round numbering, so forget which summary was closed
watch(
  () => game.value.game_over,
  (over) => {
    if (!over) dismissedSummary.value = null;
  }
);

// ---- "new game" vote on the final standings screen ----
const rematchIds = computed(() => game.value.rematch_ids || []);
const rematchPlayerIds = computed(() => game.value.rematch_player_ids || []);
const iVotedRematch = computed(() => rematchIds.value.includes(state.playerId));
const rematchPossible = computed(() => rematchPlayerIds.value.length >= 2);
const rematchReady = computed(() => rematchPlayerIds.value.filter((id) => rematchIds.value.includes(id)).length);

// ---- full log window, opened by tapping the log lines ----
const LOG_HISTORY = 20;
const logOpen = ref(false);
const logHistory = computed(() => (game.value.log || []).slice(-LOG_HISTORY).reverse());

const selected = ref([]); // array of {rank, suit}

// ---- idle reminder: the game waits on me and I've done nothing for a while
// (typically: played a card and forgot to end the turn) ----
const IDLE_REMINDER_MS = 15000;
const awaitingMe = computed(
  () => (canAct.value || !!myPrompt.value) && !game.value.awaiting_continue && !game.value.game_over
);
const idleNudge = ref(false); // on from a reminder until my next action
let idleTimer = null;

function remindTurn() {
  idleNudge.value = true;
  announceTurn(canAct.value && game.value.can_pass && game.value.has_played_this_turn ? "Закончите ход" : "Ваш ход");
  idleTimer = setTimeout(remindTurn, IDLE_REMINDER_MS);
}

// any sign of life (a tap, a key, a selection, a new server state) restarts the wait
function armIdleReminder() {
  clearTimeout(idleTimer);
  idleNudge.value = false;
  if (awaitingMe.value) idleTimer = setTimeout(remindTurn, IDLE_REMINDER_MS);
}

watch([awaitingMe, () => state.game, selected], armIdleReminder, { immediate: true });
window.addEventListener("pointerdown", armIdleReminder, { passive: true });
window.addEventListener("keydown", armIdleReminder, { passive: true });
onUnmounted(() => {
  clearTimeout(idleTimer);
  window.removeEventListener("pointerdown", armIdleReminder);
  window.removeEventListener("keydown", armIdleReminder);
});

function sameCard(a, b) {
  return a.rank === b.rank && a.suit === b.suit;
}

function cardKey(card) {
  return `${card.rank}-${card.suit}`;
}

function isSelected(card) {
  return selected.value.some((c) => sameCard(c, card));
}

function isPlayable(card) {
  if (!canAct.value) return false;
  // once a leader of some rank is already picked (but not yet submitted),
  // any sibling of that same rank may be added to the pending selection --
  // it doesn't need to individually match the table on its own.
  if (selected.value.length > 0 && selected.value[0].rank === card.rank) {
    return true;
  }
  return legalCards.value.some((c) => sameCard(c, card));
}

function toggleSelect(card) {
  if (!isPlayable(card)) return;
  if (isSelected(card)) {
    selected.value = selected.value.filter((c) => !sameCard(c, card));
  } else if (selected.value.length === 0 || selected.value[0].rank === card.rank) {
    selected.value = [...selected.value, card];
  } else {
    selected.value = [card];
  }
}

function commitSelection() {
  if (selected.value.length === 0) return;
  playCards(selected.value);
  selected.value = [];
}

// ---- fan layout for the hand ----
function fanStyle(i, total) {
  const mid = (total - 1) / 2;
  const offset = i - mid;
  const angleStep = Math.min(5, 46 / Math.max(total, 1));
  const rotate = offset * angleStep;
  const lift = Math.min(Math.abs(offset) * 2.4, 16);
  return {
    "--n": total,
    "--fan-rotate": `${rotate}deg`,
    "--fan-lift": `${lift}px`,
    zIndex: i,
  };
}

// ---- deck draw pulse feedback (fires for any player's draw) ----
const deckPulse = ref(false);
let deckPulseTimer = null;
watch(
  () => game.value.deck_count,
  (nv, ov) => {
    if (typeof ov === "number" && typeof nv === "number" && nv < ov) {
      deckPulse.value = false;
      requestAnimationFrame(() => {
        deckPulse.value = true;
        clearTimeout(deckPulseTimer);
        deckPulseTimer = setTimeout(() => (deckPulse.value = false), 340);
      });
    }
  }
);

// ---- opponents' cards flying between the table and their mini hands ----
const deckEl = ref(null);
const discardEl = ref(null);
const flights = ref([]);
const incoming = reactive({}); // player id -> cards still flying into that hand
let flightSeq = 0;

// while an opponent's card is in the air the table keeps showing the previous
// top card; the new one replaces it the moment the flying card lands
const heldTop = ref(undefined); // undefined = not holding
let holdCount = 0;
const tableEnter = ref("table-card");
const shownTop = computed(() => (heldTop.value !== undefined ? heldTop.value : game.value.table_top));

const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function rectOf(el) {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width };
}

function miniHandEl(playerId) {
  return document.querySelector(`.mini-hand[data-hand-for="${playerId}"]`);
}

// rect of the i-th card slot after the last back currently shown in a mini
// hand (i = 0 is the next free slot, i = -1 the last occupied one)
function miniSlot(handEl, i) {
  const backs = handEl.querySelectorAll(".mini-back");
  const n = backs.length;
  if (n === 0) {
    const r = handEl.getBoundingClientRect();
    const width = r.height / 1.4;
    return { left: r.left + Math.max(i, 0) * width * 0.45, top: r.top, width };
  }
  const last = rectOf(backs[n - 1]);
  const step = n > 1 ? last.left - backs[n - 2].getBoundingClientRect().left : last.width * 0.45;
  return { left: last.left + (i + 1) * step, top: last.top, width: last.width };
}

function sameCardOrNull(a, b) {
  return (!a && !b) || (a && b && sameCard(a, b));
}

function releaseTop() {
  if (holdCount === 0 || --holdCount > 0) return;
  tableEnter.value = "table-card-land";
  heldTop.value = undefined;
  setTimeout(() => (tableEnter.value = "table-card"), 50);
}

function finishFlight(f) {
  flights.value = flights.value.filter((x) => x.id !== f.id);
  f.onDone?.();
}

function landIncoming(playerId, n) {
  incoming[playerId] = (incoming[playerId] || 0) - n;
  if (incoming[playerId] <= 0) delete incoming[playerId];
}

function flyDraw(playerId, n) {
  const deckCard = deckEl.value?.querySelector(".card");
  const hand = miniHandEl(playerId);
  if (!deckCard || !hand) return;
  const from = rectOf(deckCard);
  const count = Math.min(n, 6);
  incoming[playerId] = (incoming[playerId] || 0) + n;
  for (let i = 0; i < count; i++) {
    const last = i === count - 1;
    flights.value.push({
      id: ++flightSeq,
      card: null,
      from,
      to: miniSlot(hand, i),
      width: from.width,
      delay: i * 110,
      onDone: () => landIncoming(playerId, last ? n - (count - 1) : 1),
    });
  }
}

function flyPlay(playerId, n, newTop, oldTop) {
  const hand = miniHandEl(playerId);
  const pile = discardEl.value;
  if (!hand || !pile) return;
  const to = rectOf(pile);
  const topChanged = !sameCardOrNull(newTop, oldTop);
  if (topChanged && holdCount++ === 0) heldTop.value = oldTop || null;
  const count = Math.min(n, 4);
  for (let i = 0; i < count; i++) {
    const last = i === count - 1;
    flights.value.push({
      id: ++flightSeq,
      // only the top card is known; the ones under it travel face down
      card: last && topChanged ? newTop : null,
      from: miniSlot(hand, -1 - i),
      to,
      width: to.width,
      delay: i * 110,
      onDone: last && topChanged ? releaseTop : null,
    });
  }
}

function resetFlights() {
  cancelDeal();
  flights.value = [];
  for (const k of Object.keys(incoming)) delete incoming[k];
  holdCount = 0;
  heldTop.value = undefined;
}

// ---- opening deal: cards leave the deck one by one, round the table, and
// the dealer's last card is turned over onto the table ----
const DEAL_FLIGHT = 300; // ms one dealt card spends in the air
const handEl = ref(null);
const handSizerEl = ref(null);
const dealtMine = ref(0); // my cards that have already landed
const dealLeft = ref(0); // cards of the deal still sitting on the deck
let dealRun = 0;
let dealTimer = null;

const shownHand = computed(() => (dealing.value ? myHand.value.slice(0, dealtMine.value) : myHand.value));

function cancelDeal() {
  dealRun++;
  clearTimeout(dealTimer);
  dealing.value = false;
  dealLeft.value = 0;
}

// where my k-th dealt card ends up: the right end of the centred fan so far
function handSlot(k) {
  const el = handEl.value?.$el;
  const width = handSizerEl.value?.offsetWidth;
  if (!el || !width) return null;
  const r = el.getBoundingClientRect();
  return {
    left: r.left + r.width / 2 - width / 2 + k * width * 0.375,
    top: r.top + parseFloat(getComputedStyle(el).paddingTop),
    width,
  };
}

// `wait` lets the table render (and settle) before the first card leaves
function startDeal(wait) {
  if (reduceMotion || document.visibilityState !== "visible") return cancelDeal();
  const g = game.value;
  const seats = (g.players || []).filter((p) => !p.eliminated && p.hand_count > 0);
  const order = [];
  for (let r = 0; seats.some((p) => r < p.hand_count); r++) {
    for (const p of seats) if (r < p.hand_count) order.push(p.id);
  }
  if (!order.length) return cancelDeal();

  const run = ++dealRun;
  dealing.value = true;
  dealtMine.value = 0;
  dealLeft.value = order.length + 1;
  for (const p of seats) if (p.id !== state.playerId) incoming[p.id] = p.hand_count;
  if (holdCount++ === 0) heldTop.value = null;

  const gap = Math.min(90, Math.max(55, 1500 / order.length));
  const airborne = {}; // player id -> cards launched but not landed yet
  let mineSent = 0;

  function dealOne(pid) {
    const mine = pid === state.playerId;
    const deckCard = deckEl.value?.querySelector(".card");
    const hand = mine ? null : miniHandEl(pid);
    const to = mine ? handSlot(mineSent++) : hand && miniSlot(hand, airborne[pid] || 0);
    airborne[pid] = (airborne[pid] || 0) + 1;
    dealLeft.value--;
    playCardDraw();
    const land = () => {
      if (run !== dealRun) return;
      airborne[pid]--;
      if (mine) dealtMine.value++;
      else landIncoming(pid, 1);
    };
    if (!deckCard || !to) return land();
    const from = rectOf(deckCard);
    flights.value.push({ id: ++flightSeq, card: null, from, to, width: from.width, delay: 0, duration: DEAL_FLIGHT, onDone: land });
  }

  function dealOpener() {
    const deckCard = deckEl.value?.querySelector(".card");
    const pile = discardEl.value;
    dealLeft.value = 0;
    playCardDraw();
    const land = () => {
      if (run !== dealRun) return;
      playCardPlace();
      releaseTop();
      dealing.value = false;
    };
    if (!deckCard || !pile) return land();
    const from = rectOf(deckCard);
    flights.value.push({ id: ++flightSeq, card: g.table_top, flip: true, from, to: rectOf(pile), width: from.width, delay: 0, duration: 560, onDone: land });
  }

  let i = 0;
  function step() {
    if (run !== dealRun) return;
    if (i < order.length) {
      dealOne(order[i++]);
      // the opener waits for the last hand card to land
      dealTimer = setTimeout(step, i < order.length ? gap : DEAL_FLIGHT);
    } else {
      dealOpener();
    }
  }
  dealTimer = setTimeout(step, wait);
}

// the table was opened straight onto a fresh deal (the game has just started)
if (dealing.value) startDeal(380);

// ---- card sounds, derived from what changed between two server states ----
function playSoundsFor(nv, ov) {
  if (!nv || !ov) return;
  // a fresh deal (next round or a rematch): the deal animation makes its own sounds
  if (nv.round_number !== ov.round_number || (!ov.round_active && nv.round_active)) return;
  if (!ov.round_active) return;
  // the multiplier only grows when the deck ran out and was reshuffled
  const reshuffled = nv.multiplier > ov.multiplier;
  if (reshuffled) playShuffle();
  const before = new Map((ov.players || []).map((p) => [p.id, p.hand_count]));
  for (const p of nv.players || []) {
    if (!before.has(p.id)) continue;
    const delta = p.hand_count - before.get(p.id);
    if (delta > 0) playCardDraw(Math.min(delta, 6), reshuffled ? 0.95 : 0);
    else if (delta < 0) playCardPlace(Math.min(-delta, 4));
  }
  if (nv.game_over && !ov.game_over) {
    // the whole game is decided: the winner and the rest hear different cues
    const standings = nv.standings || [];
    const winner = standings[0] && !standings[0].eliminated ? standings[0].id : null;
    if (winner === state.playerId) playGameWin(0.55);
    else if (standings.some((s) => s.id === state.playerId)) playGameLose(0.55);
    else playRoundEnd(0.55);
  } else if (nv.awaiting_continue && !ov.awaiting_continue) playRoundEnd(0.55);
}

watch(
  () => state.game,
  (nv, ov) => {
    playSoundsFor(nv, ov);
    if (!nv || !ov || nv.round_number !== ov.round_number || !ov.round_active) {
      resetFlights();
      if (ov && isFreshDeal(nv)) startDeal(150);
      return;
    }
    if (reduceMotion) return;
    const before = new Map((ov.players || []).map((p) => [p.id, p.hand_count]));
    for (const p of nv.players || []) {
      if (p.id === state.playerId || !before.has(p.id)) continue;
      const delta = p.hand_count - before.get(p.id);
      if (delta > 0) flyDraw(p.id, delta);
      else if (delta < 0) flyPlay(p.id, -delta, nv.table_top, ov.table_top);
    }
  }
);

// ---- custom pointer-based drag & drop (smooth, touch-friendly) ----
const tableAreaEl = ref(null);
const cardEls = {};

function setCardEl(card, el) {
  if (el) cardEls[cardKey(card)] = el;
  else delete cardEls[cardKey(card)];
}

const drag = reactive({
  active: false,
  cards: [],
  x: 0,
  y: 0,
  offsetX: 0,
  offsetY: 0,
  width: 0,
  height: 0,
  phase: "idle", // idle | drag | return | play
  overTable: false,
});

function isDragged(card) {
  return drag.active && drag.cards.some((c) => sameCard(c, card));
}

function isOverTable(x, y) {
  const el = tableAreaEl.value;
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
}

function onCardPointerDown(ev, card) {
  if (ev.button !== 0 && ev.pointerType === "mouse") return;
  if (!isPlayable(card)) return;

  const el = cardEls[cardKey(card)];
  if (!el) return;
  const originRect = el.getBoundingClientRect();
  const startX = ev.clientX;
  const startY = ev.clientY;
  let moved = false;

  function onMove(mv) {
    const dx = mv.clientX - startX;
    const dy = mv.clientY - startY;
    if (!moved && Math.hypot(dx, dy) > 6) {
      moved = true;
      const group = isSelected(card) && selected.value.length > 1 ? selected.value : [card];
      drag.cards = group;
      drag.width = originRect.width;
      drag.height = originRect.height;
      drag.offsetX = startX - originRect.left;
      drag.offsetY = startY - originRect.top;
      drag.x = originRect.left;
      drag.y = originRect.top;
      drag.phase = "drag";
      drag.active = true;
    }
    if (moved) {
      drag.x = mv.clientX - drag.offsetX;
      drag.y = mv.clientY - drag.offsetY;
      drag.overTable = isOverTable(mv.clientX, mv.clientY);
    }
  }

  function onUp() {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onCancel);

    if (!moved) {
      toggleSelect(card);
      return;
    }

    if (drag.overTable) {
      playCards(drag.cards);
      selected.value = [];
      flyToTable();
    } else {
      snapBack(originRect);
    }
  }

  function onCancel() {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onCancel);
    if (moved) snapBack(originRect);
  }

  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
  window.addEventListener("pointercancel", onCancel);
}

function flyToTable() {
  drag.phase = "play";
  drag.overTable = false;
  const el = tableAreaEl.value;
  if (el) {
    const r = el.getBoundingClientRect();
    drag.x = r.left + r.width / 2 - drag.width / 2;
    drag.y = r.top + r.height / 2 - drag.height / 2;
  }
  setTimeout(() => {
    drag.active = false;
    drag.phase = "idle";
    drag.cards = [];
  }, 220);
}

function snapBack(originRect) {
  drag.phase = "return";
  drag.overTable = false;
  drag.x = originRect.left;
  drag.y = originRect.top;
  setTimeout(() => {
    drag.active = false;
    drag.phase = "idle";
    drag.cards = [];
  }, 220);
}
</script>

<template>
  <div class="game-table">
    <Scoreboard :incoming="incoming" />

    <div v-if="game.game_over" class="standings">
      <p class="overline">Партия завершена</p>
      <h2 class="standings-title">Итоги игры</h2>
      <ol class="standings-list">
        <li v-for="(s, i) in game.standings" :key="s.id" :class="{ winner: i === 0 && !s.eliminated, me: s.id === state.playerId }">
          <span class="standings-place">{{ i + 1 }}</span>
          <span class="standings-name">
            {{ s.name }}
            <span v-if="s.id === state.playerId" class="you">вы</span>
          </span>
          <span v-if="rematchIds.includes(s.id)" class="tag success">готов</span>
          <span v-else-if="game.rematch_player_ids && !rematchPlayerIds.includes(s.id)" class="tag">ушёл</span>
          <span v-if="s.eliminated" class="tag danger">выбыл</span>
          <span v-else-if="i === 0" class="tag gold">победитель</span>
          <span class="standings-score">{{ s.score }}</span>
        </li>
      </ol>
      <div class="standings-actions">
        <button class="primary" :disabled="!rematchPossible || iVotedRematch" @click="voteRematch">
          {{ iVotedRematch ? "Вы готовы" : "Новая игра" }}
        </button>
        <button class="ghost" @click="leaveRoom">Вернуться в лобби</button>
      </div>
      <p class="standings-hint">
        <template v-if="!rematchPossible">Для новой игры в комнате не хватает игроков</template>
        <template v-else-if="iVotedRematch">Готовы {{ rematchReady }} из {{ rematchPlayerIds.length }} — ждём остальных</template>
        <template v-else>Новая игра начнётся, когда «Новая игра» нажмут все, кто в комнате</template>
      </p>
    </div>

    <template v-else>
      <div
        ref="tableAreaEl"
        class="table-area"
        :class="{ 'my-turn': myTurnShown, 'drop-ready': drag.active && drag.phase === 'drag', 'drop-hover': drag.active && drag.overTable }"
        @click="commitSelection"
      >
        <div class="pile">
          <div
            ref="deckEl"
            class="deck-pile"
            :class="{ drawable: canAct && game.can_draw }"
            :title="`В колоде: ${game.deck_count + dealLeft}`"
            @click.stop="canAct && game.can_draw && drawCard()"
          >
            <div class="deck-stack-shadow s2"></div>
            <div class="deck-stack-shadow s1"></div>
            <PlayingCard :card="null" face-down :class="{ pulse: deckPulse }" />
            <span v-if="game.multiplier > 1" class="multiplier">×{{ game.multiplier }}</span>
          </div>
          <span class="pile-label">Колода <b>{{ game.deck_count + dealLeft }}</b></span>
        </div>

        <div class="pile">
          <div ref="discardEl" class="discard-pile">
            <div v-if="!shownTop" class="card-slot"></div>
            <!-- a landed opponent card swaps in instantly (css off): Vue would
                 otherwise wait out the card's own box-shadow/transform transition
                 with both cards on the pile, one below the other -->
            <Transition :name="tableEnter" :css="tableEnter !== 'table-card-land'">
              <PlayingCard v-if="shownTop" :card="shownTop" :key="cardKey(shownTop)" />
            </Transition>
          </div>
          <span class="pile-label">
            <template v-if="game.declared_suit">
              Масть
              <b class="declared-suit" :class="{ red: game.declared_suit === 'hearts' || game.declared_suit === 'diamonds' }">
                {{ { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" }[game.declared_suit] }}
              </b>
            </template>
            <template v-else>Стол</template>
          </span>
        </div>

        <span v-if="drag.active && drag.phase === 'drag'" class="drop-hint">Отпустите, чтобы сыграть</span>
        <span v-if="turnCue" :key="turnCue" class="turn-flash">{{ turnCueText }}</span>
      </div>

      <div class="log-panel" title="Показать историю ходов" @click="logOpen = true">
        <!-- "your turn" is the last log line; it stands in for two lines of
             history, so the panel keeps its height -->
        <p v-for="(line, i) in (game.log || []).slice(myTurnShown ? -2 : -4)" :key="i">{{ line }}</p>
        <div v-if="myTurnShown" class="turn-banner mine">
          <span class="turn-dot"></span>
          <span>Ваш ход</span>
        </div>
      </div>

      <div class="hand-panel">
        <span ref="handSizerEl" class="hand-sizer"></span>
        <TransitionGroup
          ref="handEl"
          tag="div"
          :name="dealing ? 'hand-deal' : 'hand'"
          class="hand"
          :class="{ acting: canAct, idle: !canAct && !myPrompt && !dealing }"
        >
          <div
            v-for="(card, i) in shownHand"
            :key="cardKey(card)"
            class="hand-card"
            :class="{ 'is-dragging-source': isDragged(card) }"
            :style="fanStyle(i, shownHand.length)"
            :ref="(el) => setCardEl(card, el)"
            @pointerdown="onCardPointerDown($event, card)"
          >
            <PlayingCard :card="card" :selected="isSelected(card)" :playable="isPlayable(card)" />
          </div>
        </TransitionGroup>
        <div class="hand-actions">
          <template v-if="canAct">
            <Transition name="pop">
              <button v-if="selected.length" class="primary" @click="commitSelection">
                Сыграть <span class="btn-count">{{ selected.length }}</span>
              </button>
            </Transition>
            <button
              class="ghost"
              :disabled="!game.can_draw"
              :title="!game.can_draw ? (game.has_played_this_turn ? 'После хода картой брать нельзя — доложите карту того же номинала или закончите ход' : 'За ход можно взять только одну карту') : ''"
              @click="drawCard"
            >
              Взять карту
            </button>
            <button
              class="ghost"
              :class="{ nudge: idleNudge && game.can_pass }"
              :disabled="!game.can_pass"
              :title="mustCoverSix ? 'Сначала нужно накрыть шестёрку' : (!game.can_pass ? 'Сначала нужно взять карту или сходить' : '')"
              @click="passTurn"
            >
              {{ game.has_played_this_turn ? "Закончить ход" : "Пас" }}
            </button>
          </template>
          <p v-else-if="waitingText" class="hand-waiting">
            {{ waitingText }}<span class="wait-dots"><i></i><i></i><i></i></span>
          </p>
        </div>
      </div>
    </template>

    <PromptSuit v-if="myPrompt && myPrompt.kind === 'suit'" />
    <PromptBridge v-if="myPrompt && myPrompt.kind === 'bridge'" />
    <PromptJackEnd v-if="myPrompt && myPrompt.kind === 'jack_end'" :count="myPrompt.data.count" />
    <RoundSummary v-if="roundSummary" :summary="roundSummary" @close="dismissedSummary = roundSummary.number" />

    <div v-if="logOpen && !game.game_over" class="modal-backdrop" @click.self="logOpen = false">
      <div class="modal log-modal" role="dialog" aria-label="История ходов">
        <button class="rules-close" aria-label="Закрыть" @click="logOpen = false">✕</button>
        <p class="overline">История ходов</p>
        <!-- newest first in the DOM, drawn bottom-up: the list opens scrolled to the latest line -->
        <div class="log-list">
          <p v-for="(line, i) in logHistory" :key="logHistory.length - i">{{ line }}</p>
        </div>
      </div>
    </div>

    <div class="flight-layer">
      <CardFlight
        v-for="f in flights"
        :key="f.id"
        :card="f.card"
        :from="f.from"
        :to="f.to"
        :width="f.width"
        :delay="f.delay"
        :duration="f.duration"
        :flip="f.flip"
        @done="finishFlight(f)"
      />
    </div>

    <div
      v-if="drag.active"
      class="drag-ghost"
      :class="drag.phase"
      :style="{ left: drag.x + 'px', top: drag.y + 'px', width: drag.width + 'px', height: drag.height + 'px' }"
    >
      <div v-for="(card, i) in drag.cards" :key="cardKey(card)" class="drag-ghost-card" :style="{ '--gi': i }">
        <PlayingCard :card="card" />
      </div>
    </div>
  </div>
</template>
