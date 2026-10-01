// Small sound cues (Web Audio): synthesized, with optional mp3 samples on top.
import { reactive, watch } from "vue";

const STORAGE_KEY = "bridge-sound";
const DEFAULT_VOLUME = 0.6;

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (s && typeof s.volume === "number") {
      return { volume: Math.min(Math.max(s.volume, 0), 1), muted: !!s.muted };
    }
  } catch {
    // no storage / bad value -- fall back to defaults
  }
  return { volume: DEFAULT_VOLUME, muted: false };
}

// volume is 0..1 (the slider position); muted keeps the volume for un-muting
export const sound = reactive(loadSettings());

let ctx = null;
let master = null;
let bus = null;

// squared so the slider feels even to the ear
function masterLevel() {
  return sound.muted ? 0 : sound.volume * sound.volume;
}

function getCtx() {
  if (!ctx) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
    master = ctx.createGain();
    master.gain.value = masterLevel();
    master.connect(ctx.destination);

    // notes go into the bus: straight to master, plus a quiet, darkened
    // feedback echo that gives the chime some room around it
    bus = ctx.createGain();
    bus.connect(master);
    const delay = ctx.createDelay(1);
    delay.delayTime.value = 0.17;
    const feedback = ctx.createGain();
    feedback.gain.value = 0.3;
    const damp = ctx.createBiquadFilter();
    damp.type = "lowpass";
    damp.frequency.value = 2400;
    const wet = ctx.createGain();
    wet.gain.value = 0.22;
    bus.connect(delay);
    delay.connect(damp);
    damp.connect(feedback);
    feedback.connect(delay);
    damp.connect(wet);
    wet.connect(master);

    loadSamples(ctx);
  }
  return ctx;
}

watch(
  () => [sound.volume, sound.muted],
  () => {
    if (master) master.gain.value = masterLevel();
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ volume: sound.volume, muted: sound.muted }));
    } catch {
      // storage unavailable -- the setting just won't persist
    }
  }
);

export function toggleMute() {
  if (sound.muted || sound.volume === 0) {
    if (sound.volume === 0) sound.volume = DEFAULT_VOLUME;
    sound.muted = false;
  } else {
    sound.muted = true;
  }
}

// browsers keep an AudioContext suspended until a user gesture; wake it on the
// first tap / key press so a cue fired later by a server message can be heard
function unlock() {
  try {
    const c = getCtx();
    if (c && c.state === "suspended") c.resume();
  } catch {
    // audio unavailable
  }
}
for (const ev of ["pointerdown", "keydown", "touchend"]) {
  window.addEventListener(ev, unlock, { capture: true, passive: true });
}

// bell partials: [frequency ratio, level, share of the note's decay time].
// pure sines, the overtones quieter and shorter-lived than the fundamental
const BELL_PARTIALS = [
  [1, 1, 1],
  [2, 0.26, 0.6],
  [3.01, 0.09, 0.35],
  [4.2, 0.04, 0.2],
];

function bell(c, freq, at, dur, peak) {
  for (const [ratio, level, life] of BELL_PARTIALS) {
    const osc = c.createOscillator();
    const gain = c.createGain();
    const end = at + dur * life;
    osc.type = "sine";
    osc.frequency.value = freq * ratio;
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peak * level, at + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    osc.connect(gain).connect(bus);
    osc.start(at);
    osc.stop(end + 0.02);
  }
}

// runs `schedule(ctx, startTime)` once the context is awake; silently does
// nothing when muted, unsupported or still locked before the first gesture
async function cue(schedule) {
  if (masterLevel() === 0) return;
  try {
    const c = getCtx();
    if (!c) return;
    if (c.state !== "running") await c.resume();
    if (c.state !== "running") return;
    schedule(c, c.currentTime + 0.04);
  } catch {
    // no audio -- every cue is optional
  }
}

// "your turn": two glassy bell notes a fifth apart (D5 -> A5) over a soft low
// D4, left to ring out with a touch of echo
export function playTurnChime() {
  return cue((c, t0) => {
    bell(c, 293.66, t0, 1.1, 0.12);
    bell(c, 587.33, t0, 1.3, 0.34);
    bell(c, 880, t0 + 0.16, 1.7, 0.3);
  });
}

// end of a deal: a slow, warm rising major chord (G4 - C5 - E5 - G5)
export function playRoundEnd(delay = 0) {
  return cue((c, t0) => {
    const at = t0 + delay;
    bell(c, 196, at, 1.8, 0.1);
    bell(c, 392, at, 1.6, 0.22);
    bell(c, 523.25, at + 0.14, 1.7, 0.22);
    bell(c, 659.25, at + 0.28, 1.9, 0.22);
    bell(c, 783.99, at + 0.44, 2.4, 0.24);
  });
}

// ---- recorded samples (public/sounds/<name>.mp3) ----
// a cue with a loaded sample plays it; otherwise it falls back to the synth
const SAMPLE_NAMES = ["draw", "place", "shuffle", "win", "lose"];
const samples = {};

function loadSamples(c) {
  for (const name of SAMPLE_NAMES) {
    fetch(`${import.meta.env.BASE_URL}sounds/${name}.mp3`)
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.status))))
      // callback form: older Safari has no promise-returning decodeAudioData
      .then((data) => new Promise((resolve, reject) => c.decodeAudioData(data, resolve, reject)))
      .then((buf) => (samples[name] = buf))
      .catch(() => {
        // missing or undecodable file -- the synth version stays in use
      });
  }
}

function playSample(c, name, at) {
  const buf = samples[name];
  if (!buf) return false;
  const src = c.createBufferSource();
  src.buffer = buf;
  src.connect(master);
  src.start(at);
  return true;
}

// end of the whole game, for the winner: a bright rising fanfare
// (C5 - E5 - G5 - C6) over a low C
export function playGameWin(delay = 0) {
  return cue((c, t0) => {
    const at = t0 + delay;
    if (playSample(c, "win", at)) return;
    bell(c, 261.63, at, 2.2, 0.12);
    bell(c, 523.25, at, 1.2, 0.24);
    bell(c, 659.25, at + 0.12, 1.2, 0.24);
    bell(c, 783.99, at + 0.24, 1.4, 0.24);
    bell(c, 1046.5, at + 0.4, 2.6, 0.3);
  });
}

// end of the whole game, for everyone else: a slow falling minor line
// (A4 - F4 - D4) over a low D
export function playGameLose(delay = 0) {
  return cue((c, t0) => {
    const at = t0 + delay;
    if (playSample(c, "lose", at)) return;
    bell(c, 440, at, 1.4, 0.24);
    bell(c, 349.23, at + 0.3, 1.5, 0.24);
    bell(c, 293.66, at + 0.6, 2.4, 0.26);
    bell(c, 146.83, at + 0.6, 2.6, 0.12);
  });
}

// ---- synthesized card sounds (fallback): shaped noise, no pitch ----
let noiseBuf = null;

function noiseSource(c) {
  if (!noiseBuf) {
    noiseBuf = c.createBuffer(1, c.sampleRate, c.sampleRate);
    const data = noiseBuf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  }
  const src = c.createBufferSource();
  src.buffer = noiseBuf;
  src.loop = true;
  return src;
}

// a burst of filtered noise; the filter frequency glides from f0 to f1
function burst(c, at, dur, peak, type, f0, f1, q = 0.8) {
  const src = noiseSource(c);
  const filter = c.createBiquadFilter();
  const gain = c.createGain();
  filter.type = type;
  filter.Q.value = q;
  filter.frequency.setValueAtTime(f0, at);
  filter.frequency.exponentialRampToValueAtTime(f1, at + dur);
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(peak, at + Math.min(0.012, dur * 0.3));
  gain.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  src.connect(filter).connect(gain).connect(master);
  src.start(at, Math.random() * 0.8);
  src.stop(at + dur + 0.02);
}

// one card sliding off the deck: a short papery swish
function slide(c, at, peak = 0.5) {
  burst(c, at, 0.15, peak, "bandpass", 1500 + Math.random() * 400, 4200 + Math.random() * 800, 0.9);
}

// one card landing on the felt: a papery slap over a soft low thump
function slap(c, at, peak = 0.7) {
  burst(c, at, 0.06, peak, "lowpass", 3400, 900, 0.6);
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(170, at);
  osc.frequency.exponentialRampToValueAtTime(70, at + 0.08);
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(peak * 0.5, at + 0.006);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.1);
  osc.connect(gain).connect(master);
  osc.start(at);
  osc.stop(at + 0.12);
}

// `count` cards drawn from the deck, one after another
export function playCardDraw(count = 1, delay = 0) {
  return cue((c, t0) => {
    for (let i = 0; i < count; i++) {
      const at = t0 + delay + i * 0.11;
      if (!playSample(c, "draw", at)) slide(c, at);
    }
  });
}

// `count` cards put on the table, one after another
export function playCardPlace(count = 1, delay = 0) {
  return cue((c, t0) => {
    for (let i = 0; i < count; i++) {
      const at = t0 + delay + i * 0.11;
      if (!playSample(c, "place", at)) slap(c, at);
    }
  });
}

// deck shuffle: two riffles (a run of quick card ticks that speeds up),
// each squared off with a slide
export function playShuffle() {
  return cue((c, t0) => {
    if (playSample(c, "shuffle", t0)) return;
    for (const start of [0, 0.42]) {
      let at = t0 + start;
      let gap = 0.03;
      for (let i = 0; i < 14; i++) {
        burst(c, at, 0.014, 0.22 + Math.random() * 0.14, "highpass", 2200 + Math.random() * 1200, 3000, 0.7);
        at += gap * (0.75 + Math.random() * 0.5);
        gap *= 0.93;
      }
      slide(c, at + 0.02, 0.32);
    }
  });
}
