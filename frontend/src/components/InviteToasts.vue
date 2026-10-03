<script setup>
import { friends, acceptInvite, dismissInvite } from "../friends.js";
import UserAvatar from "./UserAvatar.vue";
</script>

<template>
  <div class="invite-toasts" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="inv in friends.invites" :key="inv.key" class="invite-toast" role="alertdialog" :aria-label="`Приглашение от ${inv.from.name}`">
        <UserAvatar :name="inv.from.name" :src="inv.from.avatar_url" class="friend-avatar" />
        <div class="invite-text">
          <b>{{ inv.from.name }}</b> зовёт вас в комнату
          <span class="invite-room">{{ inv.room }}</span>
        </div>
        <div class="invite-actions">
          <button class="primary small" @click="acceptInvite(inv)">Принять</button>
          <button class="ghost small" @click="dismissInvite(inv.key)">Отклонить</button>
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>
