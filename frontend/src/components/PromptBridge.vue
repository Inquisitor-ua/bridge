<script setup>
import { declareBridge } from "../store.js";
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal">
      <div class="modal-emblem">
        <span>♠</span><span class="red">♥</span><span class="red">♦</span><span>♣</span>
      </div>
      <p class="overline">Четыре одинаковые карты от десятки до туза</p>
      <h3>Объявить «Бридж»?</h3>
      <p class="modal-text">Раздача завершится немедленно, и все игроки посчитают очки на руках.</p>
      <div class="modal-actions column">
        <button class="primary block" @click="declareBridge(true)">Объявить Бридж</button>
        <button class="ghost block" @click="declareBridge(false)">Продолжить игру</button>
      </div>
    </div>
  </div>
</template>
