<script setup>
import { declareBridge } from "../store.js";
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal">
      <h3>На столе 4 карты одного номинала!</h3>
      <p>Объявить «Бридж»? Раздача завершится немедленно, и все игроки посчитают очки на руках.</p>
      <div class="modal-actions">
        <button class="primary" @click="declareBridge(true)">Объявить Бридж</button>
        <button class="ghost" @click="declareBridge(false)">Продолжить игру</button>
      </div>
    </div>
  </div>
</template>
