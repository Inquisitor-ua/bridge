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
      <h3>Раздача закончена валетом!</h3>
      <p>Выберите эффект:</p>
      <div class="modal-actions column">
        <button class="primary" @click="jackEndChoice('penalty')">
          Взять себе {{ penalty }} очков
        </button>
        <button class="primary" @click="jackEndChoice('multiply')">
          Умножить очки у остальных на x{{ factor }}
        </button>
      </div>
    </div>
  </div>
</template>
