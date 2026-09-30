<script setup>
import { ref, reactive, computed, watch } from "vue";
import { state, playCards, drawCard, passTurn, leaveRoom } from "../store.js";
import PlayingCard from "./PlayingCard.vue";
import Scoreboard from "./Scoreboard.vue";
import PromptSuit from "./PromptSuit.vue";
import PromptBridge from "./PromptBridge.vue";
import PromptJackEnd from "./PromptJackEnd.vue";
import RoundSummary from "./RoundSummary.vue";

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
    <Scoreboard />

    <div v-if="game.game_over" class="standings">
      <h2>Игра окончена!</h2>
      <ol>
        <li v-for="s in game.standings" :key="s.id">
          {{ s.name }} — {{ s.score }} очк. <span v-if="s.eliminated">(выбыл)</span>
        </li>
      </ol>
      <button class="ghost" @click="leaveRoom">В лобби</button>
    </div>

    <template v-else>
      <div class="turn-banner" :class="{ mine: isMyTurn }">
        <span v-if="game.awaiting_continue">Раздача завершена — ждём, пока все нажмут «Продолжить»</span>
        <span v-else-if="prompt">Ожидаем решение игрока {{ promptOwnerName }}…</span>
        <span v-else-if="isMyTurn && mustCoverSix">Нужно накрыть шестёрку — тяните карты, пока не найдётся подходящая</span>
        <span v-else-if="isMyTurn && game.suit_pending">Можно доложить ещё валетов — масть выберете, когда закончите ход</span>
        <span v-else-if="isMyTurn && game.has_played_this_turn">Можно доложить ещё карт того же номинала или закончить ход</span>
        <span v-else-if="isMyTurn">Ваш ход</span>
        <span v-else>
          Ход: {{ (game.players || []).find(p => p.id === game.turn_player_id)?.name || "…" }}
        </span>
      </div>

      <div
        ref="tableAreaEl"
        class="table-area"
        :class="{ 'drop-ready': drag.active && drag.phase === 'drag', 'drop-hover': drag.active && drag.overTable }"
        @click="commitSelection"
      >
        <div class="deck-pile" :title="`В колоде: ${game.deck_count}`" @click.stop="canAct && game.can_draw && drawCard()">
          <div class="deck-stack-shadow s2"></div>
          <div class="deck-stack-shadow s1"></div>
          <PlayingCard :card="null" face-down :class="{ pulse: deckPulse }" />
          <span class="deck-count">{{ game.deck_count }}</span>
          <span v-if="game.multiplier > 1" class="multiplier">x{{ game.multiplier }}</span>
        </div>

        <div class="discard-pile">
          <Transition name="table-card">
            <PlayingCard v-if="game.table_top" :card="game.table_top" :key="cardKey(game.table_top)" />
          </Transition>
          <span v-if="game.declared_suit" class="declared-suit">
            масть: {{ { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" }[game.declared_suit] }}
          </span>
        </div>
      </div>

      <div class="log-panel">
        <p v-for="(line, i) in (game.log || []).slice(-6)" :key="i">{{ line }}</p>
      </div>

      <div class="hand-panel">
        <TransitionGroup tag="div" name="hand" class="hand">
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
        <div v-if="canAct" class="hand-actions">
          <button v-if="selected.length" class="primary" @click="commitSelection">
            Сыграть ({{ selected.length }})
          </button>
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
