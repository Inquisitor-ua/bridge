<script setup>
import { ref, reactive, computed, watch } from "vue";
import { state, playCards, drawCard, passTurn, leaveRoom, voteRematch } from "../store.js";
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
const canAct = computed(() => isMyTurn.value && !prompt.value);
const mustCoverSix = computed(() => !!game.value.must_cover_six);
const myPrompt = computed(() => prompt.value && prompt.value.player_id === state.playerId ? prompt.value : null);
const promptOwnerName = computed(() => {
  if (!prompt.value) return "";
  const p = (game.value.players || []).find((x) => x.id === prompt.value.player_id);
  return p ? p.name : "";
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

const selected = ref([]); // array of {rank, suit}

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
  flights.value = [];
  for (const k of Object.keys(incoming)) delete incoming[k];
  holdCount = 0;
  heldTop.value = undefined;
}

watch(
  () => state.game,
  (nv, ov) => {
    if (!nv || !ov || nv.round_number !== ov.round_number || !ov.round_active) {
      resetFlights();
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
      <div class="turn-banner" :class="{ mine: isMyTurn && !prompt && !game.awaiting_continue }">
        <span class="turn-dot"></span>
        <span v-if="game.awaiting_continue">Раздача завершена — ждём, пока все нажмут «Продолжить»</span>
        <span v-else-if="prompt">Ожидаем решение игрока {{ promptOwnerName }}…</span>
        <span v-else-if="isMyTurn && mustCoverSix">Нужно накрыть шестёрку — тяните карты, пока не найдётся подходящая</span>
        <span v-else-if="isMyTurn && game.suit_pending">Можно доложить ещё валетов — масть выберете, когда закончите ход</span>
        <span v-else-if="isMyTurn && game.has_played_this_turn">Можно доложить ещё карт того же номинала или закончить ход</span>
        <span v-else-if="isMyTurn">Ваш ход</span>
        <span v-else>
          Ходит {{ (game.players || []).find(p => p.id === game.turn_player_id)?.name || "…" }}
        </span>
      </div>

      <div
        ref="tableAreaEl"
        class="table-area"
        :class="{ 'my-turn': isMyTurn && !prompt && !game.awaiting_continue, 'drop-ready': drag.active && drag.phase === 'drag', 'drop-hover': drag.active && drag.overTable }"
        @click="commitSelection"
      >
        <div class="pile">
          <div
            ref="deckEl"
            class="deck-pile"
            :class="{ drawable: canAct && game.can_draw }"
            :title="`В колоде: ${game.deck_count}`"
            @click.stop="canAct && game.can_draw && drawCard()"
          >
            <div class="deck-stack-shadow s2"></div>
            <div class="deck-stack-shadow s1"></div>
            <PlayingCard :card="null" face-down :class="{ pulse: deckPulse }" />
            <span v-if="game.multiplier > 1" class="multiplier">×{{ game.multiplier }}</span>
          </div>
          <span class="pile-label">Колода <b>{{ game.deck_count }}</b></span>
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
      </div>

      <div class="log-panel">
        <p v-for="(line, i) in (game.log || []).slice(-4)" :key="i">{{ line }}</p>
      </div>

      <div class="hand-panel">
        <TransitionGroup tag="div" name="hand" class="hand" :class="{ acting: canAct }">
          <div
            v-for="(card, i) in myHand"
            :key="cardKey(card)"
            class="hand-card"
            :class="{ 'is-dragging-source': isDragged(card) }"
            :style="fanStyle(i, myHand.length)"
            :ref="(el) => setCardEl(card, el)"
            @pointerdown="onCardPointerDown($event, card)"
          >
            <PlayingCard :card="card" :selected="isSelected(card)" :playable="isPlayable(card)" />
          </div>
        </TransitionGroup>
        <div class="hand-actions" :class="{ hidden: !canAct }">
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
            :disabled="!game.can_pass"
            :title="mustCoverSix ? 'Сначала нужно накрыть шестёрку' : (!game.can_pass ? 'Сначала нужно взять карту или сходить' : '')"
            @click="passTurn"
          >
            {{ game.has_played_this_turn ? "Закончить ход" : "Пас" }}
          </button>
        </div>
      </div>
    </template>

    <PromptSuit v-if="myPrompt && myPrompt.kind === 'suit'" />
    <PromptBridge v-if="myPrompt && myPrompt.kind === 'bridge'" />
    <PromptJackEnd v-if="myPrompt && myPrompt.kind === 'jack_end'" :count="myPrompt.data.count" />
    <RoundSummary v-if="roundSummary" :summary="roundSummary" @close="dismissedSummary = roundSummary.number" />

    <div class="flight-layer">
      <CardFlight
        v-for="f in flights"
        :key="f.id"
        :card="f.card"
        :from="f.from"
        :to="f.to"
        :width="f.width"
        :delay="f.delay"
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
