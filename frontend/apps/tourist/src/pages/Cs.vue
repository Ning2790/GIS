<script setup lang="ts">
import {
  closeCsSession,
  createCsSession,
  listCsMessages,
  listMyCsSessions,
  sendCsMessage,
  transferCsSession,
  type CsMessagePublic,
  type CsSessionPublic,
} from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhEmpty, QhInput, QhTag } from '@qh/ui';
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();

const STATUS_MAP: Record<string, { text: string; tone: 'primary' | 'warning' | 'success' | 'default' }> = {
  ai: { text: 'AI 客服接待中', tone: 'primary' },
  queued: { text: '排队等待人工客服', tone: 'warning' },
  human: { text: '人工客服接待中', tone: 'success' },
  closed: { text: '会话已结束', tone: 'default' },
};

const SENDER_LABEL: Record<string, string> = {
  user: '我',
  ai: 'AI 客服',
  agent: '人工客服',
};

const sessions = ref<CsSessionPublic[]>([]);
const active = ref<CsSessionPublic | null>(null);
const messages = ref<CsMessagePublic[]>([]);
const draft = ref('');
const sending = ref(false);
const error = ref('');
const messagesEl = ref<HTMLDivElement | null>(null);
let timer: number | null = null;

const statusInfo = computed(() =>
  active.value ? (STATUS_MAP[active.value.status] ?? { text: active.value.status, tone: 'default' as const }) : null,
);
const closed = computed(() => active.value?.status === 'closed');

async function scrollToBottom() {
  await nextTick();
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
}

async function loadSessions(autoOpen = true) {
  try {
    const data = await listMyCsSessions();
    sessions.value = data.items;
    if (autoOpen && !active.value && data.items.length > 0) {
      await openSession(data.items[0].id);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载会话列表失败';
  }
}

async function refreshMessages() {
  if (!active.value) {
    return;
  }
  try {
    const data = await listCsMessages(active.value.id);
    if (messages.value.length !== data.items.length) {
      messages.value = data.items;
      void scrollToBottom();
    }
  } catch {
    /* 轮询失败静默 */
  }
}

async function openSession(sessionId: number) {
  error.value = '';
  let found = sessions.value.find((item) => item.id === sessionId);
  if (!found) {
    await loadSessions(false);
    found = sessions.value.find((item) => item.id === sessionId);
  }
  if (found) {
    active.value = found;
  }
  const data = await listCsMessages(sessionId);
  messages.value = data.items;
  void scrollToBottom();
}

async function startSession() {
  error.value = '';
  try {
    const session = await createCsSession();
    sessions.value = [session, ...sessions.value];
    active.value = session;
    messages.value = [];
  } catch (err) {
    error.value = err instanceof Error ? err.message : '发起会话失败';
  }
}

async function send() {
  const content = draft.value.trim();
  if (!content || sending.value || !active.value) {
    return;
  }
  draft.value = '';
  sending.value = true;
  error.value = '';
  try {
    const result = await sendCsMessage(active.value.id, content);
    messages.value.push(result.message);
    if (result.reply) {
      messages.value.push(result.reply);
    }
    void scrollToBottom();
    void refreshSessionStatus();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '发送失败';
  } finally {
    sending.value = false;
  }
}

async function refreshSessionStatus() {
  if (!active.value) {
    return;
  }
  try {
    const data = await listMyCsSessions();
    sessions.value = data.items;
    const updated = data.items.find((item) => item.id === active.value?.id);
    if (updated) {
      active.value = updated;
    }
  } catch {
    /* 静默 */
  }
}

async function handleTransfer() {
  if (!active.value) {
    return;
  }
  try {
    const session = await transferCsSession(active.value.id);
    active.value = session;
    void refreshSessionStatus();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '转接失败';
  }
}

async function handleClose() {
  if (!active.value) {
    return;
  }
  try {
    const session = await closeCsSession(active.value.id);
    active.value = session;
    void refreshSessionStatus();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '结束会话失败';
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false });
}

onMounted(async () => {
  await loadSessions();
  // 从订单页「申请售后」跳转而来时直达对应会话
  const wanted = Number(route.query.session);
  if (Number.isInteger(wanted) && wanted > 0) {
    await openSession(wanted);
  }
  timer = window.setInterval(refreshMessages, 5000);
});

onBeforeUnmount(() => {
  if (timer !== null) {
    window.clearInterval(timer);
  }
});
</script>

<template>
  <PageTitle
    size="large"
    title="在线客服"
    subtitle="AI 客服即时应答，需要时可转人工（商户 / 企业客服接入后回复）"
  />

  <div class="cs-layout">
    <aside class="sessions">
      <QhCard class="sessions__card">
        <template #header>会话</template>
        <QhButton class="sessions__new" size="sm" @click="startSession">＋ 开始新会话</QhButton>
        <QhEmpty v-if="sessions.length === 0" text="暂无会话" />
        <ul v-else class="sessions__list">
          <li
            v-for="item in sessions"
            :key="item.id"
            class="sessions__item"
            :class="{ 'sessions__item--active': item.id === active?.id }"
            @click="openSession(item.id)"
          >
            <span>会话 #{{ item.id }}</span>
            <QhTag :tone="(STATUS_MAP[item.status] ?? { tone: 'default' }).tone">
              {{ STATUS_MAP[item.status]?.text ?? item.status }}
            </QhTag>
          </li>
        </ul>
      </QhCard>
    </aside>

    <section class="chat">
      <header class="chat__head">
        <div class="chat__status">
          <strong v-if="active">会话 #{{ active.id }}</strong>
          <QhTag v-if="statusInfo" :tone="statusInfo.tone">{{ statusInfo.text }}</QhTag>
          <span v-else class="chat__placeholder">请选择或发起一个会话</span>
        </div>
        <div v-if="active && !closed" class="chat__ops">
          <QhButton
            v-if="active.status === 'ai'"
            size="sm"
            variant="ghost"
            @click="handleTransfer"
          >
            转人工客服
          </QhButton>
          <QhButton size="sm" variant="danger" @click="handleClose">结束会话</QhButton>
        </div>
      </header>

      <div ref="messagesEl" class="chat__messages">
        <QhEmpty v-if="messages.length === 0" text="还没有消息，说点什么吧" />
        <div
          v-for="message in messages"
          :key="message.id"
          class="msg"
          :class="message.sender_type === 'user' ? 'msg--user' : 'msg--other'"
        >
          <p class="msg__label">
            {{ SENDER_LABEL[message.sender_type] ?? message.sender_type }} ·
            {{ formatTime(message.created_at) }}
          </p>
          <p class="msg__content">{{ message.content }}</p>
        </div>
      </div>

      <div class="chat__bar">
        <QhInput
          v-model="draft"
          :disabled="!active || closed || sending"
          :maxlength="2000"
          :placeholder="closed ? '会话已结束' : '输入消息，回车发送'"
          @keyup.enter="send"
        />
        <QhButton :disabled="!active || closed || sending || draft.trim().length === 0" @click="send">
          发送
        </QhButton>
      </div>
      <p v-if="error" class="chat__error">{{ error }}</p>
    </section>
  </div>
</template>

<style scoped>
.cs-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: var(--qh-space-4);
  height: calc(100vh - var(--qh-header-h) - 180px);
  min-height: 420px;
}
.sessions__card {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.sessions__new {
  width: 100%;
  margin-bottom: var(--qh-space-3);
}
.sessions__list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
}
.sessions__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-2);
  padding: var(--qh-space-2) var(--qh-space-3);
  border-radius: var(--qh-radius-sm);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
  cursor: pointer;
}
.sessions__item:hover {
  background: var(--qh-bg);
}
.sessions__item--active {
  background: var(--qh-primary-weak);
}
.chat {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--qh-border);
  border-radius: var(--qh-radius-lg);
  background: var(--qh-surface);
  box-shadow: var(--qh-shadow-sm);
  overflow: hidden;
}
.chat__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-3);
  padding: var(--qh-space-3) var(--qh-space-4);
  border-bottom: 1px solid var(--qh-border);
}
.chat__status {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
}
.chat__placeholder {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.chat__ops {
  display: flex;
  gap: var(--qh-space-2);
}
.chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--qh-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
}
.msg {
  max-width: 78%;
}
.msg__label {
  margin: 0 0 2px;
  color: var(--qh-faint);
  font-size: var(--qh-fs-xs);
}
.msg__content {
  margin: 0;
  padding: var(--qh-space-3) var(--qh-space-4);
  border-radius: var(--qh-radius);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg--user {
  align-self: flex-end;
  text-align: right;
}
.msg--user .msg__content {
  background: var(--qh-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
  text-align: left;
}
.msg--other {
  align-self: flex-start;
}
.msg--other .msg__content {
  background: var(--qh-bg);
  border: 1px solid var(--qh-border);
  color: var(--qh-ink);
  border-bottom-left-radius: 4px;
}
.chat__bar {
  display: flex;
  gap: var(--qh-space-3);
  padding: var(--qh-space-4);
  border-top: 1px solid var(--qh-border);
}
.chat__error {
  margin: 0;
  padding: 0 var(--qh-space-4) var(--qh-space-3);
  color: var(--qh-danger);
  font-size: var(--qh-fs-sm);
}
@media (max-width: 900px) {
  .cs-layout {
    grid-template-columns: 1fr;
    height: auto;
  }
  .sessions__card {
    max-height: 200px;
  }
  .chat {
    height: 560px;
  }
}
</style>
