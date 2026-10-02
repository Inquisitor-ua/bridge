<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { login, register } from "../auth.js";

const emit = defineEmits(["close"]);

const mode = ref("login"); // "login" | "register"
const username = ref("");
const password = ref("");
const displayName = ref("");
const error = ref("");
const busy = ref(false);

const canSubmit = computed(() => username.value.trim() && password.value && !busy.value);

function switchMode(m) {
  mode.value = m;
  error.value = "";
}

async function submit() {
  if (!canSubmit.value) return;
  busy.value = true;
  error.value = "";
  try {
    if (mode.value === "login") {
      await login(username.value.trim(), password.value);
    } else {
      await register(username.value.trim(), password.value, displayName.value.trim());
    }
    emit("close");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}

function onKey(ev) {
  if (ev.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="modal-backdrop auth-backdrop" @click.self="emit('close')">
    <form class="modal auth-modal" role="dialog" aria-label="Вход" @submit.prevent="submit">
      <button type="button" class="modal-close" aria-label="Закрыть" @click="emit('close')">✕</button>
      <p class="rs-kicker">Аккаунт</p>
      <h3>{{ mode === "login" ? "Вход" : "Регистрация" }}</h3>

      <div class="segmented">
        <button type="button" :class="{ active: mode === 'login' }" @click="switchMode('login')">Вход</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="switchMode('register')">Регистрация</button>
        <span class="segmented-thumb" :class="{ right: mode === 'register' }"></span>
      </div>

      <label class="field">
        <span>Логин</span>
        <input
          v-model="username"
          maxlength="20"
          autocomplete="username"
          autocapitalize="off"
          spellcheck="false"
          :placeholder="mode === 'register' ? 'латиница, цифры и _' : ''"
        />
      </label>

      <label class="field">
        <span>Пароль</span>
        <input
          v-model="password"
          type="password"
          maxlength="128"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          :placeholder="mode === 'register' ? 'не короче 6 символов' : ''"
        />
      </label>

      <Transition name="field">
        <label v-if="mode === 'register'" class="field">
          <span>Имя в игре</span>
          <input v-model="displayName" maxlength="24" placeholder="по умолчанию — логин" />
        </label>
      </Transition>

      <p v-if="error" class="auth-error">{{ error }}</p>

      <button type="submit" class="primary block" :disabled="!canSubmit">
        {{ mode === "login" ? "Войти" : "Создать аккаунт" }}
      </button>
    </form>
  </div>
</template>
