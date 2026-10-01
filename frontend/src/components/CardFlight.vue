<script setup>
import { ref, onMounted } from "vue";
import PlayingCard from "./PlayingCard.vue";

// One card flying between two screen rects (deck -> a hand, or opponent's
// hand -> table). The element is laid out at full table-card size and only
// transformed, so the card art scales exactly like the real thing.
const props = defineProps({
  card: { type: Object, default: null }, // null -> face down
  from: { type: Object, required: true }, // { left, top, width }
  to: { type: Object, required: true },
  width: { type: Number, required: true },
  delay: { type: Number, default: 0 },
  duration: { type: Number, default: 460 },
  // leaves face down and turns over to show `card` on the way
  flip: { type: Boolean, default: false },
});
const emit = defineEmits(["done"]);

const el = ref(null);
const flipEl = ref(null);

function place(r, extra = "") {
  return `translate(${r.left}px, ${r.top}px) scale(${r.width / props.width})${extra}`;
}

onMounted(() => {
  const mid = {
    left: (props.from.left + props.to.left) / 2,
    top: Math.min(props.from.top, props.to.top) - 24,
    width: (props.from.width + props.to.width) / 2,
  };
  const anim = el.value.animate(
    [
      { transform: place(props.from, " rotate(0deg)"), opacity: 1 },
      { transform: place(mid, " rotate(-6deg)"), opacity: 1, offset: 0.5 },
      { transform: place(props.to, " rotate(0deg)"), opacity: 1 },
    ],
    { duration: props.duration, delay: props.delay, easing: "cubic-bezier(0.45, 0, 0.25, 1)", fill: "both" }
  );
  anim.onfinish = () => emit("done");
  anim.oncancel = () => emit("done");

  flipEl.value?.animate(
    [
      { transform: "rotateY(0deg)" },
      { transform: "rotateY(0deg)", offset: 0.25 },
      { transform: "rotateY(180deg)" },
    ],
    { duration: props.duration, delay: props.delay, easing: "ease-in-out", fill: "both" }
  );
});
</script>

<template>
  <div
    ref="el"
    class="card-flight"
    :class="{ flip }"
    :style="{ '--card-w': width + 'px', '--card-h': width * 1.4 + 'px' }"
  >
    <div v-if="flip" ref="flipEl" class="card-flipper">
      <PlayingCard :card="null" face-down />
      <PlayingCard class="flip-front" :card="card" />
    </div>
    <PlayingCard v-else :card="card" :face-down="!card" />
  </div>
</template>
