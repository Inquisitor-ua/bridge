<script setup>
import { computed } from "vue";
import { state, continueRound, leaveRoom } from "../store.js";
import UserAvatar from "./UserAvatar.vue";

const props = defineProps({
  summary: { type: Object, required: true },
});
const emit = defineEmits(["close"]);

const SUITS = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };
const RANKS = { 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A" };

const game = computed(() => state.game || {});
const rows = computed(() => props.summary.players || []);
const nameOf = (id) => rows.value.find((r) => r.id === id)?.name || "—";

const headline = computed(() => {
  const s = props.summary;
  const who = nameOf(s.player_id);
  if (s.reason === "bridge") return `${who} объявил(а) БРИДЖ!`;
  if (s.reason === "jack") {
    const n = s.jack_count || 1;
    const base = `${who} закончил(а) ${n > 1 ? `${n} валетами` : "валетом"}`;
    if (s.jack_choice === "penalty") return `${base} и списал(а) себе ${-20 * n} очков`;
    if (s.jack_choice === "multiply") return `${base} и умножил(а) очки соперников на x${n + 1}`;
    return base;
  }
  if (s.reason === "out") return `${who} избавился(-ась) от всех карт`;
  return "Раздача завершена";
});

const duration = computed(() => {
  const t = props.summary.duration_sec || 0;
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
});

function cardLabel(c) {
  return `${RANKS[c.rank]}${SUITS[c.suit]}`;
}
function isRed(c) {
  return c.suit === "hearts" || c.suit === "diamonds";
}
function signed(n) {
  return n > 0 ? `+${n}` : `${n}`;
}

// ---- per-player stat grid (rows = stat, columns = players) ----
const STAT_ROWS = [
  { key: "turns", label: "Ходов сделано" },
  { key: "cards_played", label: "Карт сыграно" },
  { key: "biggest_play", label: "Макс. карт за ход" },
  { key: "cards_drawn", label: "Взято из колоды" },
  { key: "penalty_drawn", label: "Штрафных карт получено" },
  { key: "penalty_dealt", label: "Штрафных карт выдано" },
  { key: "turns_skipped", label: "Пропущено ходов" },
  { key: "jacks_played", label: "Валетов сыграно" },
  { key: "max_hand", label: "Макс. карт на руке" },
];

function bestIn(key) {
  const vals = rows.value.map((r) => r.stats[key] || 0);
  return Math.max(0, ...vals);
}

// ---- highlights: short "awards" for the round's standout numbers ----
const HIGHLIGHTS = [
  { key: "penalty_dealt", icon: "◎", title: "Снайпер", text: (n) => `выдал(а) соперникам ${n} штрафн. карт` },
  { key: "biggest_play", icon: "✦", title: "Комбо", text: (n) => `выложил(а) ${n} карты за один ход`, min: 2 },
  { key: "_taken", icon: "◈", title: "Коллекционер", text: (n) => `набрал(а) ${n} карт из колоды` },
  { key: "turns_skipped", icon: "☾", title: "Отдыхающий", text: (n) => `пропустил(а) ${n} ход(а)` },
  { key: "jacks_played", icon: "J", title: "Любитель валетов", text: (n) => `сыграл(а) ${n} валет(а)`, min: 2 },
  { key: "max_hand", icon: "▤", title: "Полные руки", text: (n) => `держал(а) до ${n} карт одновременно`, min: 8 },
];

function statValue(row, key) {
  if (key === "_taken") return (row.stats.cards_drawn || 0) + (row.stats.penalty_drawn || 0);
  return row.stats[key] || 0;
}

const highlights = computed(() => {
  const out = [];
  for (const h of HIGHLIGHTS) {
    const best = Math.max(0, ...rows.value.map((r) => statValue(r, h.key)));
    if (best < (h.min || 1)) continue;
    const leaders = rows.value.filter((r) => statValue(r, h.key) === best).map((r) => r.name);
    out.push({ ...h, names: leaders.join(", "), value: best });
  }
  return out.slice(0, 4);
});

// ---- ready / continue ----
const alivePlayers = computed(() => (game.value.players || []).filter((p) => !p.eliminated));
const readyIds = computed(() => new Set(game.value.ready_ids || []));
const iAmIn = computed(() => alivePlayers.value.some((p) => p.id === state.playerId));
const iAmReady = computed(() => readyIds.value.has(state.playerId));
const waiting = computed(() => !!game.value.awaiting_continue);

// back to the lobby; mid-game that forfeits, so ask first (as the header's "Выйти" does)
function goHome() {
  if (iAmIn.value && !game.value.game_over && !confirm("Выйти из игры? Вы выбудете из текущей партии.")) return;
  leaveRoom();
}
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal round-summary">
      <p class="rs-kicker">Раздача №{{ summary.number }}</p>
      <h3 class="rs-headline">{{ headline }}</h3>

      <div class="rs-chips">
        <span class="rs-chip">Ходов: <b>{{ summary.turns }}</b></span>
        <span class="rs-chip">Время: <b>{{ duration }}</b></span>
        <span class="rs-chip">Перетасовок: <b>{{ summary.reshuffles }}</b></span>
        <span class="rs-chip" :class="{ hot: summary.multiplier > 1 }">Множитель: <b>x{{ summary.multiplier }}</b></span>
      </div>

      <h4 class="rs-section">Очки</h4>
      <div class="rs-scores">
        <div
          v-for="r in rows"
          :key="r.id"
          class="rs-score-row"
          :class="{ me: r.id === state.playerId, winner: r.id === summary.player_id && summary.reason !== 'bridge' }"
        >
          <div class="rs-name">
            <UserAvatar :name="r.name" :src="r.avatar_url" :bot="!!r.bot_level" class="rs-avatar" />
            <span v-if="r.id === summary.player_id && summary.reason !== 'bridge'" class="rs-crown">♛</span>
            <span class="rs-player-name" :title="r.name">{{ r.name }}</span>
            <span v-if="r.id === state.playerId" class="rs-you">вы</span>
          </div>
          <div class="rs-hand">
            <span v-if="!r.hand.length" class="rs-empty">рука пуста</span>
            <span v-for="c in r.hand" :key="c.rank + c.suit" class="rs-card" :class="{ red: isRed(c) }">{{ cardLabel(c) }}</span>
          </div>
          <div class="rs-delta" :class="{ plus: r.points > 0, minus: r.points < 0 }">{{ signed(r.points) }}</div>
          <div class="rs-total">
            <span class="rs-before">{{ r.score_before }}</span>
            <span class="rs-arrow">→</span>
            <b>{{ r.score_after }}</b>
            <span v-if="r.reset" class="tag success rs-badge">125 — обнуление</span>
            <span v-else-if="r.eliminated" class="tag danger rs-badge">выбыл(а)</span>
          </div>
        </div>
      </div>

      <template v-if="highlights.length">
        <h4 class="rs-section">Отличились</h4>
        <div class="rs-highlights">
          <div v-for="h in highlights" :key="h.key" class="rs-highlight">
            <span class="rs-hl-icon">{{ h.icon }}</span>
            <div>
              <div class="rs-hl-title">{{ h.title }}</div>
              <div class="rs-hl-text"><b>{{ h.names }}</b> {{ h.text(h.value) }}</div>
            </div>
          </div>
        </div>
      </template>

      <h4 class="rs-section">Статистика</h4>
      <div class="rs-table-wrap">
        <table class="rs-table">
          <thead>
            <tr>
              <th></th>
              <th v-for="r in rows" :key="r.id" :class="{ me: r.id === state.playerId }">{{ r.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in STAT_ROWS" :key="s.key">
              <td class="rs-stat-label">{{ s.label }}</td>
              <td
                v-for="r in rows"
                :key="r.id"
                :class="{ best: rows.length > 1 && r.stats[s.key] > 0 && r.stats[s.key] === bestIn(s.key) }"
              >
                {{ r.stats[s.key] }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="rs-footer">
        <template v-if="waiting">
          <div class="rs-ready">
            <span
              v-for="p in alivePlayers"
              :key="p.id"
              class="rs-ready-pill"
              :class="{ ready: readyIds.has(p.id) }"
            >
              <span class="rs-ready-mark">{{ readyIds.has(p.id) ? "✓" : "" }}</span>{{ p.name }}
            </span>
          </div>
          <p v-if="!iAmIn" class="rs-note">Вы выбыли — следующая раздача начнётся без вас.</p>
          <div class="rs-actions">
            <button v-if="iAmIn" class="primary rs-continue" :disabled="iAmReady" @click="continueRound">
              {{ iAmReady ? "Ждём остальных…" : "Продолжить" }}
            </button>
            <button v-else class="ghost" @click="emit('close')">Закрыть</button>
            <button class="ghost" @click="goHome">Домой</button>
          </div>
        </template>
        <div v-else class="rs-actions">
          <button class="primary rs-continue" @click="emit('close')">К итогам игры</button>
          <button class="ghost" @click="goHome">Домой</button>
        </div>
      </div>
    </div>
  </div>
</template>
