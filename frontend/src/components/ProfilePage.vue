<script setup>
import { ref, computed, watch } from "vue";
import {
  auth,
  fetchUser,
  fetchUserStats,
  updateProfile,
  uploadAvatar,
  deleteAvatar,
  changePassword,
  logout,
} from "../auth.js";
import { prepareAvatar } from "../avatarImage.js";
import { route, goHome } from "../router.js";
import ProfileStats from "./ProfileStats.vue";
import UserAvatar from "./UserAvatar.vue";
import FriendButton from "./FriendButton.vue";

const PASSWORD_MIN = 6;

const user = ref(null);
const stats = ref(null);
const statsError = ref(false);
const loading = ref(true);
const notFound = ref(false);
const loadError = ref("");

// which inline form is open on your own profile: null | "name" | "password"
const mode = ref(null);
const formError = ref("");
const saving = ref(false);
const notice = ref("");

const nameDraft = ref("");

const oldPassword = ref("");
const newPassword = ref("");
const newPassword2 = ref("");
const passwordReady = computed(
  () => oldPassword.value && newPassword.value.length >= PASSWORD_MIN && newPassword.value === newPassword2.value,
);
const passwordHint = computed(() => {
  if (newPassword.value && newPassword.value.length < PASSWORD_MIN) return `не короче ${PASSWORD_MIN} символов`;
  if (newPassword2.value && newPassword.value !== newPassword2.value) return "пароли не совпадают";
  return "";
});

const avatarInput = ref(null);
const avatarBusy = ref(false);
const avatarError = ref("");

const isOwn = computed(
  () => !!auth.user && !!user.value && auth.user.username.toLowerCase() === user.value.username.toLowerCase(),
);
const since = computed(() =>
  user.value
    ? new Date(user.value.created_at * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
    : "",
);

async function load() {
  loading.value = true;
  notFound.value = false;
  loadError.value = "";
  closeForm();
  notice.value = "";
  avatarError.value = "";
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

function openForm(which) {
  mode.value = which;
  formError.value = "";
  notice.value = "";
  if (which === "name") nameDraft.value = user.value.display_name;
  oldPassword.value = "";
  newPassword.value = "";
  newPassword2.value = "";
}

function closeForm() {
  mode.value = null;
  formError.value = "";
}

async function submitForm(action) {
  if (saving.value) return;
  saving.value = true;
  formError.value = "";
  try {
    await action();
  } catch (e) {
    formError.value = e.message;
  } finally {
    saving.value = false;
  }
}

function saveName() {
  if (!nameDraft.value.trim()) return;
  submitForm(async () => {
    await updateProfile(nameDraft.value.trim());
    closeForm();
  });
}

function savePassword() {
  if (!passwordReady.value) return;
  submitForm(async () => {
    await changePassword(oldPassword.value, newPassword.value);
    closeForm();
    notice.value = "Пароль изменён. На других устройствах нужно будет войти заново.";
  });
}

function pickAvatar() {
  avatarError.value = "";
  avatarInput.value?.click();
}

async function onAvatarPicked(ev) {
  const file = ev.target.files?.[0];
  ev.target.value = ""; // picking the same file again should fire change too
  if (!file) return;
  avatarBusy.value = true;
  avatarError.value = "";
  try {
    await uploadAvatar(await prepareAvatar(file));
  } catch (e) {
    avatarError.value = e.message;
  } finally {
    avatarBusy.value = false;
  }
}

async function removeAvatar() {
  avatarBusy.value = true;
  avatarError.value = "";
  try {
    await deleteAvatar();
  } catch (e) {
    avatarError.value = e.message;
  } finally {
    avatarBusy.value = false;
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
          <button
            v-if="isOwn"
            type="button"
            class="avatar-edit"
            :class="{ busy: avatarBusy }"
            :disabled="avatarBusy"
            title="Сменить фото"
            aria-label="Сменить фото профиля"
            @click="pickAvatar"
          >
            <UserAvatar :name="user.display_name" :src="user.avatar_url" class="profile-avatar" />
            <span class="avatar-edit-overlay" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </span>
          </button>
          <UserAvatar v-else :name="user.display_name" :src="user.avatar_url" class="profile-avatar" />
          <input
            v-if="isOwn"
            ref="avatarInput"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/*"
            class="visually-hidden"
            tabindex="-1"
            @change="onAvatarPicked"
          />

          <div class="profile-ident">
            <template v-if="mode !== 'name'">
              <h2 class="profile-name">{{ user.display_name }}</h2>
              <p class="profile-username">@{{ user.username }}</p>
            </template>
            <form v-else class="profile-edit" @submit.prevent="saveName">
              <label class="field">
                <span>Имя в игре</span>
                <input v-model="nameDraft" maxlength="24" autofocus />
              </label>
              <p v-if="formError" class="auth-error">{{ formError }}</p>
              <div class="profile-edit-actions">
                <button type="submit" class="primary small" :disabled="!nameDraft.trim() || saving">Сохранить</button>
                <button type="button" class="ghost small" @click="closeForm">Отмена</button>
              </div>
            </form>
          </div>
        </div>

        <p v-if="avatarError" class="auth-error profile-avatar-error">{{ avatarError }}</p>

        <dl class="profile-facts">
          <div>
            <dt>В игре с</dt>
            <dd>{{ since }}</dd>
          </div>
        </dl>

        <form v-if="isOwn && mode === 'password'" class="profile-password" @submit.prevent="savePassword">
          <h4 class="pstats-group-title">Смена пароля</h4>
          <!-- lets password managers tie the new password to the right account -->
          <input type="text" class="visually-hidden" :value="user.username" autocomplete="username" readonly tabindex="-1" aria-hidden="true" />
          <label class="field">
            <span>Текущий пароль</span>
            <input v-model="oldPassword" type="password" maxlength="128" autocomplete="current-password" autofocus />
          </label>
          <label class="field">
            <span>Новый пароль</span>
            <input v-model="newPassword" type="password" maxlength="128" autocomplete="new-password" />
          </label>
          <label class="field">
            <span>Новый пароль ещё раз</span>
            <input v-model="newPassword2" type="password" maxlength="128" autocomplete="new-password" />
          </label>
          <p v-if="formError || passwordHint" class="auth-error">{{ formError || passwordHint }}</p>
          <div class="profile-edit-actions">
            <button type="submit" class="primary small" :disabled="!passwordReady || saving">Сменить пароль</button>
            <button type="button" class="ghost small" @click="closeForm">Отмена</button>
          </div>
        </form>

        <p v-if="notice" class="profile-notice">{{ notice }}</p>

        <div v-if="isOwn && !mode" class="profile-actions">
          <button class="ghost small" @click="openForm('name')">Изменить имя</button>
          <button class="ghost small" :disabled="avatarBusy" @click="pickAvatar">
            {{ user.avatar_url ? "Сменить фото" : "Загрузить фото" }}
          </button>
          <button v-if="user.avatar_url" class="ghost small" :disabled="avatarBusy" @click="removeAvatar">Удалить фото</button>
          <button class="ghost small" @click="openForm('password')">Сменить пароль</button>
          <button class="ghost small danger-text" @click="onLogout">Выйти из аккаунта</button>
        </div>
        <div v-else-if="!isOwn && auth.user" class="profile-actions">
          <FriendButton :username="user.username" />
        </div>
      </template>
    </section>

    <section v-if="!loading && user && (stats || statsError)" class="profile-card">
      <ProfileStats v-if="stats" :stats="stats" />
      <p v-else class="profile-muted">Статистику не удалось загрузить. Попробуйте обновить страницу.</p>
    </section>
  </div>
</template>
