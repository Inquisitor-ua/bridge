<script setup>
import { computed } from "vue";
import { openProfile } from "../router.js";

const props = defineProps({
  stats: { type: Object, required: true },
});

function plural(n, forms) {
  const n10 = n % 10;
  const n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return forms[0];
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1];
  return forms[2];
}

function formatNumber(n) {
  return n.toLocaleString("ru-RU");
}

function formatDuration(sec) {
  const min = Math.round(sec / 60);
  if (min < 1) return "меньше минуты";
  if (min < 60) return `${min} мин`;
  const h = Math.floor(min / 60);
  const rest = min % 60;
  return rest ? `${h} ч ${rest} мин` : `${h} ч`;
}

function percent(part, whole) {
  return whole ? Math.round((part / whole) * 100) : 0;
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

const s = computed(() => props.stats);
const winRate = computed(() => percent(s.value.wins, s.value.games));

const roundFacts = computed(() => [
  { label: "Раундов сыграно", value: formatNumber(s.value.rounds_played) },
  {
    label: "Вышел первым",
    value: formatNumber(s.value.rounds_won),
    note: s.value.rounds_played ? `${percent(s.value.rounds_won, s.value.rounds_played)}% раундов` : null,
  },
  { label: "Объявил «Бридж»", value: formatNumber(s.value.bridges) },
  { label: "Ровно 125 очков", value: formatNumber(s.value.resets) },
  { label: "Время в игре", value: formatDuration(s.value.play_seconds) },
]);

const cardFacts = computed(() => [
  { label: "Карт сыграно", value: formatNumber(s.value.cards_played) },
  { label: "Взято из колоды", value: formatNumber(s.value.cards_drawn) },
  { label: "Штрафных выдано", value: formatNumber(s.value.penalty_dealt) },
  { label: "Штрафных получено", value: formatNumber(s.value.penalty_drawn) },
  { label: "Пропусков выдано", value: formatNumber(s.value.skips_dealt) },
  { label: "Валетов сыграно", value: formatNumber(s.value.jacks_played) },
  { label: "Больше всего за ход", value: `${s.value.biggest_play} ${plural(s.value.biggest_play, ["карта", "карты", "карт"])}` },
  { label: "Больше всего на руке", value: `${s.value.max_hand} ${plural(s.value.max_hand, ["карта", "карты", "карт"])}` },
]);

function gameMeta(g) {
  return [
    `${g.player_count} ${plural(g.player_count, ["игрок", "игрока", "игроков"])}`,
    `${g.rounds} ${plural(g.rounds, ["раунд", "раунда", "раундов"])}`,
    formatDuration(g.duration_sec),
  ].join(" · ");
}
</script>

<template>
  <section class="pstats">
    <h3 class="pstats-title">Статистика</h3>

    <p v-if="!s.games" class="pstats-empty">
      Пока ни одной сыгранной партии. Статистика появится после первой игры с аккаунтом.
    </p>

    <template v-else>
      <div class="kpi-row">
        <div class="kpi">
          <span class="kpi-label">Партий</span>
          <span class="kpi-value">{{ formatNumber(s.games) }}</span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Побед</span>
          <span class="kpi-value">{{ formatNumber(s.wins) }}</span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Процент побед</span>
          <span class="kpi-value">{{ winRate }}%</span>
          <span
            class="meter"
            role="meter"
            aria-label="Процент побед"
            :aria-valuenow="winRate"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <span class="meter-fill" :style="{ width: winRate + '%' }"></span>
          </span>
        </div>
        <div class="kpi">
          <span class="kpi-label">Лучшая серия</span>
          <span class="kpi-value">{{ s.best_streak }}</span>
          <span class="kpi-note">{{ s.current_streak ? `сейчас ${s.current_streak} подряд` : "побед подряд" }}</span>
        </div>
      </div>

      <div class="pstats-groups">
        <div class="pstats-group">
          <h4 class="pstats-group-title">Раунды</h4>
          <dl class="pstats-list">
            <div v-for="f in roundFacts" :key="f.label" class="pstats-item">
              <dt>{{ f.label }}</dt>
              <dd>
                {{ f.value }}<span v-if="f.note" class="pstats-note">{{ f.note }}</span>
              </dd>
            </div>
          </dl>
        </div>
        <div class="pstats-group">
          <h4 class="pstats-group-title">Карты</h4>
          <dl class="pstats-list">
            <div v-for="f in cardFacts" :key="f.label" class="pstats-item">
              <dt>{{ f.label }}</dt>
              <dd>{{ f.value }}</dd>
            </div>
          </dl>
        </div>
      </div>

      <h4 class="pstats-group-title pstats-recent-title">Последние партии</h4>
      <ol class="recent-list">
        <li v-for="(g, i) in s.recent_games" :key="i" class="recent-game" :class="{ won: g.won }">
          <span class="recent-place" :title="`${g.place} место из ${g.player_count}`">
            <span class="recent-place-num">{{ g.place }}</span>
            <span class="recent-place-of">из {{ g.player_count }}</span>
          </span>
          <span class="recent-body">
            <span class="recent-head">
              <span class="recent-result">{{ g.won ? "Победа" : g.left ? "Вышел из игры" : `${g.place} место` }}</span>
              <span class="recent-date">{{ formatDate(g.finished_at) }}</span>
            </span>
            <span class="recent-meta">{{ gameMeta(g) }}</span>
            <span v-if="g.opponents.length" class="recent-opponents">
              против
              <template v-for="(o, j) in g.opponents" :key="j">
                <button v-if="o.username" class="link-btn" @click="openProfile(o.username)">{{ o.name }}</button>
                <span v-else>{{ o.name }}</span><template v-if="j < g.opponents.length - 1">, </template>
              </template>
            </span>
          </span>
          <span class="recent-score" title="Очки в конце партии">{{ g.score }}</span>
        </li>
      </ol>
    </template>
  </section>
</template>
