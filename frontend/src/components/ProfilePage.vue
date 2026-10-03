<script setup>
import { ref, computed, watch } from "vue";
import { auth, fetchUser, fetchUserStats, updateProfile, logout } from "../auth.js";
import { route, goHome } from "../router.js";
import ProfileStats from "./ProfileStats.vue";

const user = ref(null);
const stats = ref(null);
const statsError = ref(false);
const loading = ref(true);
const notFound = ref(false);
const loadError = ref("");

const editing = ref(false);
const nameDraft = ref("");
const saveError = ref("");
const saving = ref(false);

const isOwn = computed(
  () => !!auth.user && !!user.value && auth.user.username.toLowerCase() === user.value.username.toLowerCase(),
);
const initial = computed(() => (user.value?.display_name || "?").charAt(0).toUpperCase());
const since = computed(() =>
  user.value
    ? new Date(user.value.created_at * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
    : "",
);

async function load() {
  loading.value = true;
  notFound.value = false;
  loadError.value = "";
  editing.value = false;
  stats.value = null;
  statsError.value = false;
  // statistics are secondary: if they fail, the profile still shows
  const statsReq = fetchUserStats(route.username).catch(() => {
    statsError.value = true;
    return null;
  });
  try {
    user.value = await fetchUser(route.username);
  } catch (e) {
    user.value = null;
    // only a 404 means "no such user"; anything else is a connection problem
    notFound.value = e.status === 404;
    loadError.value = e.status === 404 ? "" : e.message;
  } finally {
    loading.value = false;
  }
  stats.value = await statsReq;
}
watch(() => route.username, load, { immediate: true });

// your own profile follows edits made here (and in another tab after a reload)
watch(
  () => auth.user,
  (me) => {
    if (me && isOwn.value) user.value = { ...me };
  },
);

function startEdit() {
  nameDraft.value = user.value.display_name;
  saveError.value = "";
  editing.value = true;
}

async function saveName() {
  if (!nameDraft.value.trim() || saving.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    await updateProfile(nameDraft.value.trim());
    editing.value = false;
  } catch (e) {
    saveError.value = e.message;
  } finally {
    saving.value = false;
  }
}

async function onLogout() {
  await logout();
  goHome();
}
</script>

<template>
  <div class="profile">
    <button class="ghost small profile-back" @click="goHome">← Назад</button>

    <section class="profile-card">
      <p v-if="loading" class="profile-muted">Загрузка…</p>

      <template v-else-if="notFound">
        <p class="rs-kicker">Профиль</p>
        <h2 class="profile-name">Не найден</h2>
        <p class="profile-muted">Пользователя «{{ route.username }}» не существует.</p>
      </template>

      <template v-else-if="loadError">
        <p class="rs-kicker">Профиль</p>
        <h2 class="profile-name">Не загрузился</h2>
        <p class="profile-muted">{{ loadError }}. Попробуйте обновить страницу.</p>
      </template>

      <template v-else-if="user">
        <div class="profile-head">
          <span class="avatar profile-avatar">{{ initial }}</span>
          <div class="profile-ident">
            <template v-if="!editing">
              <h2 class="profile-name">{{ user.display_name }}</h2>
              <p class="profile-username">@{{ user.username }}</p>
            </template>
            <form v-else class="profile-edit" @submit.prevent="saveName">
              <label class="field">
                <span>Имя в игре</span>
                <input v-model="nameDraft" maxlength="24" autofocus />
              </label>
              <p v-if="saveError" class="auth-error">{{ saveError }}</p>
              <div class="profile-edit-actions">
                <button type="submit" class="primary small" :disabled="!nameDraft.trim() || saving">Сохранить</button>
                <button type="button" class="ghost small" @click="editing = false">Отмена</button>
              </div>
            </form>
          </div>
        </div>

        <dl class="profile-facts">
          <div>
            <dt>В игре с</dt>
            <dd>{{ since }}</dd>
          </div>
        </dl>

        <div v-if="isOwn && !editing" class="profile-actions">
          <button class="ghost small" @click="startEdit">Изменить имя</button>
          <button class="ghost small danger-text" @click="onLogout">Выйти из аккаунта</button>
        </div>
      </template>
    </section>

    <section v-if="!loading && user && (stats || statsError)" class="profile-card">
      <ProfileStats v-if="stats" :stats="stats" />
      <p v-else class="profile-muted">Статистику не удалось загрузить. Попробуйте обновить страницу.</p>
    </section>
  </div>
</template>
