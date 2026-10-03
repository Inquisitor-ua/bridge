<script setup>
import { onMounted, onBeforeUnmount } from "vue";
import PlayingCard from "./PlayingCard.vue";

const emit = defineEmits(["close"]);

const CARD_EFFECTS = [
  {
    cards: [{ rank: 6, suit: "hearts" }],
    name: "Шестёрка",
    text: "Её обязательно накрывает тот же игрок, который её положил: берёт карты из колоды, пока не найдётся подходящая. Раздача шестёркой не заканчивается.",
    points: "0 очков",
  },
  {
    cards: [{ rank: 7, suit: "clubs" }],
    name: "Семёрка",
    text: "Следующий игрок берёт 1 карту (за каждую семёрку — по карте).",
    points: "0 очков",
  },
  {
    cards: [{ rank: 8, suit: "diamonds" }],
    name: "Восьмёрка",
    text: "Следующий игрок берёт 2 карты и пропускает ход. Каждая восьмёрка бьёт своего соперника по кругу: две восьмёрки на троих — оба соперника берут по 2 и пропускают.",
    points: "0 очков",
  },
  {
    cards: [{ rank: 12, suit: "spades" }],
    name: "Дама пик",
    text: "Следующий игрок берёт 5 карт.",
    points: "10 очков",
  },
  {
    cards: [{ rank: 14, suit: "hearts" }],
    name: "Туз",
    text: "Следующий игрок пропускает ход. Каждый туз пропускает своего соперника по кругу.",
    points: "15 очков",
  },
  {
    cards: [{ rank: 11, suit: "diamonds" }],
    name: "Валет",
    text: "Кладётся на любую карту. Можно доложить ещё валетов, затем вы называете новую масть, и ход переходит дальше.",
    points: "10 очков, единственная карта на руке — 20",
  },
  {
    cards: [
      { rank: 9, suit: "spades" },
      { rank: 10, suit: "hearts" },
      { rank: 12, suit: "clubs" },
      { rank: 13, suit: "diamonds" },
    ],
    name: "9, 10, дама, король",
    text: "Без эффекта.",
    points: "9 — 0, остальные — 10 очков",
  },
];

function onKey(ev) {
  if (ev.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="modal-backdrop rules-backdrop" @click.self="emit('close')">
    <div class="modal rules-modal" role="dialog" aria-label="Правила игры">
      <button class="rules-close" aria-label="Закрыть" @click="emit('close')">✕</button>
      <p class="rs-kicker">Как играть</p>
      <h3>Правила</h3>

      <h4 class="rules-section">Что делают карты</h4>
      <ul class="rules-cards">
        <li v-for="e in CARD_EFFECTS" :key="e.name" class="rules-card-row">
          <span class="rules-card-pics">
            <span v-for="(c, i) in e.cards" :key="i" class="rules-card-pic">
              <PlayingCard :card="c" />
            </span>
          </span>
          <span class="rules-card-body">
            <span class="rules-card-name">{{ e.name }}</span>
            <span class="rules-card-text">{{ e.text }}</span>
          </span>
          <span class="rules-card-points" title="Очки, если карта осталась на руке">{{ e.points }}</span>
        </li>
      </ul>
      <p class="rules-note">
        Очки — сколько стоит карта, если осталась на руке в конце раздачи. Эффекты 7, 8, дамы пик и туза
        срабатывают, когда вы заканчиваете ход, и отбиться от них нельзя.
      </p>

      <h4 class="rules-section">Цель</h4>
      <p>
        Первым избавиться от всех карт. Остальные записывают себе очки за карты, оставшиеся на руке. Очки копятся
        от раздачи к раздаче: ровно <b>125</b> — счёт обнуляется, больше 125 — игрок выбывает. Побеждает последний
        оставшийся.
      </p>

      <h4 class="rules-section">Раздача</h4>
      <p>
        Колода — 36 карт (от шестёрки до туза). Всем по 5 карт, сдающему — 4: его пятая карта открывается на стол.
        Сдаёт игрок с наибольшим счётом, в первой раздаче — случайный.
      </p>

      <h4 class="rules-section">Ход</h4>
      <ul class="rules-list">
        <li>Карту на стол можно положить, если она совпадает с верхней по масти или номиналу. Валет кладётся на что угодно.</li>
        <li>За ход можно выложить несколько карт одного номинала: сразу или по одной. Сменить номинал в том же ходу нельзя.</li>
        <li>Ход заканчиваете вы сами, кнопкой «Закончить ход».</li>
        <li>Ходить не обязательно: можно взять одну карту из колоды, а потом сыграть или спасовать. Спасовать, ничего не сделав, нельзя.</li>
        <li>Карты выкладываются перетаскиванием на стол или выбором и кнопкой «Сыграть».</li>
      </ul>

      <h4 class="rules-section">«Бридж»</h4>
      <p>
        Если на столе подряд легли 4 десятки, 4 валета, 4 дамы, 4 короля или 4 туза, положивший последнюю карту
        может объявить «Бридж». Раздача сразу заканчивается, и очки на руках считают все, включая объявившего.
      </p>

      <h4 class="rules-section">Конец раздачи</h4>
      <ul class="rules-list">
        <li>
          Если вы вышли валетом, выбирайте: записать себе −20 очков за каждый валет или умножить очки остальных на
          (число валетов + 1).
        </li>
        <li>Если вышли 7, 8 или дамой пик, штрафные карты всё равно раздаются (за каждую восьмёрку — своему сопернику) и идут в подсчёт.</li>
        <li>Когда колода кончается, стол (кроме верхней карты) перемешивается в новую. Каждая такая пересдача добавляет +1 к множителю очков в этой раздаче.</li>
      </ul>

      <button class="primary block rules-ok" @click="emit('close')">Понятно</button>
    </div>
  </div>
</template>
