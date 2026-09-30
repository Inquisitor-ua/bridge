<script setup>
import { computed } from "vue";
import { jackEndChoice } from "../store.js";

const props = defineProps({ count: { type: Number, required: true } });
const penalty = computed(() => -20 * props.count);
const factor = computed(() => props.count + 1);
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal">
      <div class="modal-emblem serif">J</div>
      <p class="overline">Раздача закончена валетом</p>
      <h3>Выберите эффект</h3>
      <div class="choice-list">
        <button class="choice" @click="jackEndChoice('penalty')">
          <span class="choice-value">{{ penalty }}</span>
          <span class="choice-text">Списать очки себе</span>
        </button>
        <button class="choice" @click="jackEndChoice('multiply')">
          <span class="choice-value">×{{ factor }}</span>
          <span class="choice-text">Умножить очки соперников</span>
        </button>
      </div>
    </div>
  </div>
</template>
