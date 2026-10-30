<script setup lang="ts">
import {
  ApiError,
  claimCsSession,
  closeCsSession,
  listCsMessages,
  listCsQueue,
  releaseCsSession,
  sendCsMessage,
  type CsMessagePublic,
  type CsSessionPublic,
} from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();

const queue = ref<CsSessionPublic[]>([]);
const active = ref<CsSessionPublic | null>(null);
const messages = ref<CsMessagePublic[]>([]);
const draft = ref('');
const sending = ref(false);
const loading = ref(false);
const messagesEl = ref<HTMLDivElement | null>(null);
let timer: number | null = null;

const isMySession = computed(() => active.value?.agent_id === auth.user?.id);
const canReply = computed(() => active.value?.status === 'human' && isMySession.value);

async function loadQueue() {
  try {
    const data = await listCsQueue(1, 50);
    queue.value = data.items;
  } catch {
    /* 静默 */
  }
}

async function openSession(session: CsSessionPublic) {
  active.value = session;
  try {
    const data = await listCsMessages(session.id);
    messages.value = data.items;
    void scrollToBottom();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '加载消息失败');
  }
}

async function claim(session: CsSessionPublic) {
  try {
    const updated = await claimCsSession(session.id);
    ElMessage.success('已接入会话');
    await openSession(updated);
    void loadQueue();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '接入失败（可能已被其他客服接入）');
    void loadQueue();
  }
}

async function send() {
  const content = draft.value.trim();
  if (!content || sending.value || !active.value) {
    return;
  }
  draft.value = '';
  sending.value = true;
  try {
    const result = await sendCsMessage(active.value.id, content);
    messages.value.push(result.message);
    if (result.reply) {
      messages.value.push(result.reply);
    }
    void scrollToBottom();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '发送失败');
  } finally {
    sending.value = false;
  }
}

async function release() {
  if (!active.value) {
    return;
  }
  try {
    active.value = await releaseCsSession(active.value.id);
    ElMessage.success('已释放会话（回到人工队列）');
    void loadQueue();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '释放失败');
  }
}

async function close() {
  if (!active.value) {
    return;
  }
  await ElMessageBox.confirm('确定结束该会话？', '提示', { type: 'warning' });
  try {
    active.value = await closeCsSession(active.value.id);
    ElMessage.success('会话已结束');
    void loadQueue();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '结束失败');
  }
}

async function refreshMessages() {
  if (!active.value) {
    return;
  }
  try {
    const data = await listCsMessages(active.value.id);
    if (data.items.length !== messages.value.length) {
      messages.value = data.items;
      void scrollToBottom();
    }
  } catch {
    /* 静默 */
  }
}

async function scrollToBottom() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
}

const SENDER_LABEL: Record<string, string> = {
  user: '游客',
  ai: 'AI 客服',
  agent: '客服',
};

function statusText(status: string): string {
  return { ai: 'AI 接待中', queued: '排队中', human: '人工接待中', closed: '已结束' }[status] ?? status;
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false });
}

onMounted(async () => {
  loading.value = true;
  await loadQueue();
  loading.value = false;
  timer = window.setInterval(() => {
    void loadQueue();
    void refreshMessages();
  }, 5000);
});

onBeforeUnmount(() => {
  if (timer !== null) {
    window.clearInterval(timer);
  }
});
</script>

<template>
  <div class="wb">
    <el-card shadow="never" class="wb__queue" v-loading="loading">
      <template #header>人工队列（{{ queue.length }}）</template>
      <el-empty v-if="queue.length === 0" description="暂无排队会话" :image-size="80" />
      <ul v-else class="q-list">
        <li
          v-for="item in queue"
          :key="item.id"
          class="q-item"
          :class="{ 'q-item--active': item.id === active?.id }"
          @click="openSession(item)"
        >
          <div class="q-item__main">
            <strong>会话 #{{ item.id }}</strong>
            <span class="q-item__meta">游客 {{ item.user_id }}</span>
          </div>
          <el-button size="small" type="primary" @click.stop="claim(item)">接入</el-button>
        </li>
      </ul>
    </el-card>

    <el-card shadow="never" class="wb__chat">
      <template #header>
        <div class="chat-head">
          <span v-if="active">会话 #{{ active.id }} · {{ statusText(active.status) }}</span>
          <span v-else>请从左侧队列接入一个会话</span>
          <span v-if="active" class="chat-head__ops">
            <el-button v-if="canReply" size="small" @click="release">释放</el-button>
            <el-button size="small" type="danger" @click="close">结束</el-button>
          </span>
        </div>
      </template>

      <div ref="messagesEl" class="msgs">
        <el-empty v-if="messages.length === 0" description="暂无消息" :image-size="80" />
        <div
          v-for="message in messages"
          :key="message.id"
          class="msg"
          :class="message.sender_type === 'agent' ? 'msg--agent' : 'msg--other'"
        >
          <p class="msg__label">{{ SENDER_LABEL[message.sender_type] ?? message.sender_type }} · {{ formatTime(message.created_at) }}</p>
          <p class="msg__content">{{ message.content }}</p>
        </div>
      </div>

      <div class="bar">
        <el-input
          v-model="draft"
          :disabled="!canReply"
          :placeholder="canReply ? '输入回复，回车发送' : '接入会话后可回复（AI 接待中由 AI 自动应答）'"
          maxlength="2000"
          @keyup.enter="send"
        />
        <el-button type="primary" :disabled="!canReply || sending" @click="send">发送</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.wb {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 16px;
  height: calc(100vh - 150px);
  min-height: 480px;
}
.wb__queue,
.wb__chat {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.q-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.q-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}
.q-item--active {
  background: var(--el-color-primary-light-9);
}
.q-item__main {
  display: flex;
  flex-direction: column;
}
.q-item__meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.chat-head__ops {
  display: flex;
  gap: 8px;
}
.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg {
  max-width: 80%;
}
.msg--agent {
  align-self: flex-end;
  text-align: right;
}
.msg--other {
  align-self: flex-start;
}
.msg__label {
  margin: 0 0 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.msg__content {
  display: inline-block;
  margin: 0;
  padding: 8px 12px;
  border-radius: 10px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
}
.msg--agent .msg__content {
  background: var(--el-color-primary);
  color: #fff;
  text-align: left;
}
.bar {
  display: flex;
  gap: 10px;
  padding-top: 12px;
}
</style>
