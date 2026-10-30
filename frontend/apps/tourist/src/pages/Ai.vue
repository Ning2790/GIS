<script setup lang="ts">
import {
  askStream,
  deleteConversation,
  getConversationDetail,
  listConversations,
  renameConversation,
  type AiConversationPublic,
  type KnowledgeSource,
} from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhEmpty, QhInput } from '@qh/ui';
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

import AiMascot from '../components/AiMascot.vue';

interface DisplayMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  knowledgeSources?: KnowledgeSource[];
}

const conversations = ref<AiConversationPublic[]>([]);
const activeId = ref<number | null>(null);
const messages = ref<DisplayMessage[]>([]);
const question = ref('');
const sending = ref(false);
const error = ref('');
const messagesEl = ref<HTMLDivElement | null>(null);
// 会话管理（增强项）：重命名用行内输入，删除需二次确认
const renamingId = ref<number | null>(null);
const renameText = ref('');
const sessionMsg = ref('');

const SUGGESTIONS = ['高原反应怎么预防？', '青海湖什么时候去最好？', '去青海要带什么装备？'];

const MASCOT_ACTIONS = [
  'scratch',
  'laugh',
  'fall',
  'wave',
  'spin',
  'sneeze',
  'dance',
  'jump',
  'angry',
  'startle',
] as const;
type MascotActionId = (typeof MASCOT_ACTIONS)[number];
type MascotAction = 'idle' | MascotActionId;
const mascotAction = ref<MascotAction>('idle');
let lastMascotAction: MascotAction = 'idle';
let mascotQueue: MascotActionId[] = [];
let mascotTimer: number | undefined;
const MASCOT_ACTION_MS: Record<MascotActionId, number> = {
  scratch: 1700,
  laugh: 2000,
  fall: 2800,
  wave: 1800,
  spin: 2200,
  sneeze: 1800,
  dance: 2000,
  jump: 2100,
  angry: 1900,
  startle: 1800,
};

/** 洗牌抽签：一轮内所有动作都出现后才重新洗牌，避免连续重复。 */
function drawMascotAction(): MascotActionId {
  if (mascotQueue.length === 0) {
    mascotQueue = [...MASCOT_ACTIONS];
    for (let i = mascotQueue.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [mascotQueue[i], mascotQueue[j]] = [mascotQueue[j], mascotQueue[i]];
    }
    if (mascotQueue[0] === lastMascotAction && mascotQueue.length > 1) {
      const j = 1 + Math.floor(Math.random() * (mascotQueue.length - 1));
      [mascotQueue[0], mascotQueue[j]] = [mascotQueue[j], mascotQueue[0]];
    }
  }
  return mascotQueue.shift()!;
}

/** 点击形象随机触发一个动作，动作结束自动回到待机。 */
function playMascotAction() {
  if (mascotAction.value !== 'idle') {
    return;
  }
  const next = drawMascotAction();
  lastMascotAction = next;
  mascotAction.value = next;
  window.clearTimeout(mascotTimer);
  mascotTimer = window.setTimeout(() => {
    mascotAction.value = 'idle';
  }, MASCOT_ACTION_MS[next]);
}

onBeforeUnmount(() => window.clearTimeout(mascotTimer));

async function loadConversations() {
  try {
    const data = await listConversations();
    conversations.value = data.items;
  } catch {
    /* 列表加载失败不打断聊天 */
  }
}

async function openConversation(id: number) {
  if (sending.value) {
    return;
  }
  activeId.value = id;
  error.value = '';
  try {
    const detail = await getConversationDetail(id);
    messages.value = detail.messages.map((message) => ({
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
      // 历史消息的知识来源（N12 后续：随消息持久化，重开会话后卡片仍在）
      knowledgeSources: message.knowledge_sources ?? [],
    }));
    void scrollToBottom();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载会话失败';
  }
}

function newConversation() {
  activeId.value = null;
  messages.value = [];
  error.value = '';
}

/** 进入重命名状态（行内输入框）。 */
function startRename(item: AiConversationPublic) {
  if (sending.value) {
    sessionMsg.value = '正在生成回答，请稍候再改名';
    return;
  }
  renamingId.value = item.id;
  renameText.value = item.title;
  sessionMsg.value = '';
}

function cancelRename() {
  renamingId.value = null;
  renameText.value = '';
}

/** 提交重命名：成功后就地更新列表标题。 */
async function submitRename(id: number) {
  const title = renameText.value.trim();
  if (!title) {
    sessionMsg.value = '标题不能为空';
    return;
  }
  try {
    const updated = await renameConversation(id, title);
    const item = conversations.value.find((row) => row.id === id);
    if (item) {
      item.title = updated.title;
    }
    cancelRename();
  } catch (err) {
    sessionMsg.value = err instanceof Error ? err.message : '重命名失败';
  }
}

/** 删除会话（二次确认）：连同消息一起删；删的是当前会话时清空右侧。 */
async function removeConversation(item: AiConversationPublic) {
  if (sending.value) {
    // 模型正在回答时删除会话：后端会按「会话不存在」返回 404，问题也白问了
    sessionMsg.value = '正在生成回答，请稍候再删除';
    return;
  }
  if (!window.confirm(`删除会话「${item.title}」？该会话的聊天记录会一起删除。`)) {
    return;
  }
  try {
    await deleteConversation(item.id);
    conversations.value = conversations.value.filter((row) => row.id !== item.id);
    if (activeId.value === item.id) {
      newConversation();
    }
    sessionMsg.value = '已删除会话';
  } catch (err) {
    sessionMsg.value = err instanceof Error ? err.message : '删除失败';
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
}

async function send() {
  const text = question.value.trim();
  if (!text || sending.value) {
    return;
  }
  question.value = '';
  error.value = '';
  messages.value.push({ role: 'user', content: text });
  const assistant = reactive<DisplayMessage>({ role: 'assistant', content: '' });
  messages.value.push(assistant);
  sending.value = true;
  void scrollToBottom();

  try {
    await askStream(text, activeId.value, {
      onConversation: (id) => {
        if (activeId.value === null) {
          activeId.value = id;
        }
      },
      onDelta: (delta) => {
        assistant.content += delta;
        void scrollToBottom();
      },
      onSources: (sources) => {
        assistant.sources = sources;
      },
      onKnowledgeSources: (sources) => {
        assistant.knowledgeSources = sources;
      },
    });
    void loadConversations();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提问失败';
    if (!assistant.content) {
      messages.value.pop();
    }
  } finally {
    sending.value = false;
    void scrollToBottom();
  }
}

function useSuggestion(text: string) {
  question.value = text;
  void send();
}

onMounted(() => {
  void loadConversations();
  void scrollToBottom();
});
</script>

<template>
  <PageTitle
    size="large"
    title="AI 助手"
    subtitle="青海旅游问答（接大模型后将自动生成正式回答；当前为模拟回复）"
  />

  <div class="chat-layout">
    <aside class="assistant-panel" aria-label="AI 助手形象">
      <div class="assistant-panel__inner">
        <div class="assistant-panel__stage" :class="{ 'is-active': mascotAction !== 'idle' }">
          <button
            type="button"
            class="assistant-panel__mascot-button"
            aria-label="和 AI 助手互动"
            title="戳一下，看看我会做什么"
            @click="playMascotAction"
          >
            <span class="assistant-panel__mascot-frame">
              <AiMascot :action="mascotAction" class="assistant-panel__mascot" />
            </span>
            <span class="assistant-panel__tap-hint">戳我一下</span>
          </button>
          <span
            v-if="mascotAction === 'scratch'"
            class="assistant-panel__fx assistant-panel__fx--question"
            aria-hidden="true"
          >
            ?
          </span>
          <span
            v-if="mascotAction === 'laugh'"
            class="assistant-panel__fx assistant-panel__fx--laugh"
            aria-hidden="true"
          >
            哈哈哈
          </span>
          <span
            v-if="mascotAction === 'fall'"
            class="assistant-panel__fx assistant-panel__fx--fall"
            aria-hidden="true"
          >
            扑通！
          </span>
          <span
            v-if="mascotAction === 'wave'"
            class="assistant-panel__fx assistant-panel__fx--wave"
            aria-hidden="true"
          >
            嗨～
          </span>
          <span
            v-if="mascotAction === 'spin'"
            class="assistant-panel__fx assistant-panel__fx--spin"
            aria-hidden="true"
          >
            转圈圈
          </span>
          <span
            v-if="mascotAction === 'sneeze'"
            class="assistant-panel__fx assistant-panel__fx--sneeze"
            aria-hidden="true"
          >
            阿嚏！
          </span>
          <span
            v-if="mascotAction === 'dance'"
            class="assistant-panel__fx assistant-panel__fx--dance"
            aria-hidden="true"
          >
            ♪
          </span>
          <span
            v-if="mascotAction === 'jump'"
            class="assistant-panel__fx assistant-panel__fx--jump"
            aria-hidden="true"
          >
            嘿咻！
          </span>
          <span
            v-if="mascotAction === 'angry'"
            class="assistant-panel__fx assistant-panel__fx--angry"
            aria-hidden="true"
          >
            哼！
          </span>
          <span
            v-if="mascotAction === 'startle'"
            class="assistant-panel__fx assistant-panel__fx--startle"
            aria-hidden="true"
          >
            哇！
          </span>
        </div>
        <div class="assistant-panel__meta">
          <span class="assistant-panel__status">
            <span class="assistant-panel__dot" aria-hidden="true"></span>
            AI 在线
          </span>
          <p class="assistant-panel__name">天境源康 AI</p>
          <p class="assistant-panel__desc">景点 · 季节 · 装备 · 高原安全</p>
        </div>
      </div>
    </aside>

    <aside class="sessions">
      <QhCard class="sessions__card">
        <template #header>会话</template>
        <QhButton class="sessions__new" size="sm" @click="newConversation">＋ 新对话</QhButton>
        <p v-if="sessionMsg" class="sessions__msg">{{ sessionMsg }}</p>
        <QhEmpty v-if="conversations.length === 0" text="暂无历史会话" />
        <ul v-else class="sessions__list">
          <li
            v-for="item in conversations"
            :key="item.id"
            class="sessions__item"
            :class="{ 'sessions__item--active': item.id === activeId }"
          >
            <template v-if="renamingId === item.id">
              <QhInput
                v-model="renameText"
                class="sessions__rename"
                placeholder="会话标题"
                @keyup.enter="submitRename(item.id)"
              />
              <span class="sessions__actions">
                <QhButton size="sm" @click="submitRename(item.id)">保存</QhButton>
                <QhButton size="sm" variant="ghost" @click="cancelRename">取消</QhButton>
              </span>
            </template>
            <template v-else>
              <button type="button" class="sessions__title" @click="openConversation(item.id)">
                {{ item.title }}
              </button>
              <span class="sessions__actions">
                <QhButton size="sm" variant="ghost" @click="startRename(item)">重命名</QhButton>
                <QhButton size="sm" variant="ghost" @click="removeConversation(item)">删除</QhButton>
              </span>
            </template>
          </li>
        </ul>
      </QhCard>
    </aside>

    <section class="chat">
      <div ref="messagesEl" class="chat__messages">
        <div v-if="messages.length === 0" class="chat__welcome">
          <p class="chat__welcome-eyebrow">天境源康 · 高原旅行 AI</p>
          <h2 class="chat__welcome-title">今天想从哪里出发？</h2>
          <p class="chat__hello">
            我是青海旅游助手，可以问景点、季节、装备或高原注意事项。
          </p>
          <p class="chat__suggestions-label">试试这样问</p>
          <div class="chat__suggestions">
            <button
              v-for="(text, index) in SUGGESTIONS"
              :key="text"
              type="button"
              class="chat__suggestion-card"
              @click="useSuggestion(text)"
            >
              <span class="chat__suggestion-index">0{{ index + 1 }}</span>
              <span class="chat__suggestion-text">{{ text }}</span>
              <span class="chat__suggestion-arrow" aria-hidden="true">↗</span>
            </button>
          </div>
        </div>
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="msg"
          :class="message.role === 'user' ? 'msg--user' : 'msg--assistant'"
        >
          <p class="msg__content">{{ message.content || '…' }}</p>
          <div
            v-if="message.knowledgeSources && message.knowledgeSources.length > 0"
            class="msg__knowledge"
          >
            <span class="msg__knowledge-title">参考平台知识</span>
            <div
              v-for="source in message.knowledgeSources"
              :key="source.topic"
              class="knowledge-card"
            >
              <div class="knowledge-card__head">
                <span class="knowledge-card__topic">{{ source.topic }}</span>
                <span class="knowledge-card__score">
                  {{ source.matched_by === 'vector' ? '语义匹配' : '关键词匹配' }}
                  {{ source.matched_by === 'vector' ? source.score.toFixed(2) : '' }}
                </span>
              </div>
              <p class="knowledge-card__excerpt">{{ source.excerpt }}</p>
            </div>
          </div>
          <p v-if="message.sources && message.sources.length > 0" class="msg__sources">
            参考：<a v-for="source in message.sources" :key="source" :href="source" target="_blank">
              {{ source }}
            </a>
          </p>
        </div>
      </div>

      <div class="chat__footer">
        <div class="chat__bar">
          <QhInput
            v-model="question"
            :maxlength="500"
            :disabled="sending"
            placeholder="输入问题，回车发送（如：高原反应怎么预防？）"
            @keyup.enter="send"
          />
          <QhButton :disabled="sending || question.trim().length === 0" @click="send">
            {{ sending ? '回复中…' : '发送' }}
          </QhButton>
        </div>
        <p v-if="error" class="chat__error">{{ error }}</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chat-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 220px;
  grid-template-areas: 'assistant chat sessions';
  gap: var(--qh-space-4);
  height: calc(100vh - var(--qh-header-h) - 180px);
  min-height: 420px;
}
.assistant-panel {
  grid-area: assistant;
  position: relative;
  overflow: hidden;
  border: 1px solid #e3eefb;
  border-radius: var(--qh-radius-lg);
  background:
    radial-gradient(circle at 50% 34%, rgba(147, 197, 253, 0.2), rgba(147, 197, 253, 0) 62%),
    linear-gradient(180deg, #f8fbff, #eef6ff);
}
.assistant-panel::before {
  content: '';
  position: absolute;
  top: 38%;
  left: 50%;
  width: 230px;
  height: 230px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0) 68%);
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.assistant-panel__inner {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 24px 16px;
  text-align: center;
}
.assistant-panel__stage {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.assistant-panel__mascot-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 0;
  border: 0;
  border-radius: 18px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  transition: transform 0.2s ease;
}
.assistant-panel__mascot-button:hover {
  transform: translateY(-2px);
}
.assistant-panel__mascot-button:active {
  transform: translateY(0) scale(0.99);
}
.assistant-panel__mascot-button:focus-visible {
  outline: 2px solid #93c5fd;
  outline-offset: 5px;
}
.assistant-panel__mascot-frame {
  display: block;
  width: 100%;
  padding: 8px 6px;
  margin: -8px -6px;
  overflow: hidden;
  border-radius: 18px;
}
.assistant-panel__tap-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #1d4ed8;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  opacity: 0.65;
  transition: opacity 0.2s ease;
}
.assistant-panel__tap-hint::before {
  content: '✦';
  font-size: 9px;
}
.assistant-panel__mascot-button:hover .assistant-panel__tap-hint {
  opacity: 1;
}
.assistant-panel__stage.is-active .assistant-panel__tap-hint {
  opacity: 0;
}
.assistant-panel__fx {
  position: absolute;
  z-index: 3;
  color: #1d4ed8;
  font-weight: 700;
  white-space: nowrap;
  pointer-events: none;
  text-shadow: 0 2px 0 rgba(255, 255, 255, 0.95);
}
.assistant-panel__fx--question {
  top: -2px;
  right: 2%;
  font-size: 36px;
  line-height: 1;
  animation: mascot-fx-pop 1.5s ease-out forwards;
}
.assistant-panel__fx--laugh {
  top: -18px;
  left: 50%;
  font-size: 15px;
  letter-spacing: 0.12em;
  animation: mascot-fx-float 1.7s ease-out forwards;
}
.assistant-panel__fx--fall {
  bottom: 18%;
  left: 4%;
  font-size: 15px;
  animation: mascot-fx-pop 1.2s ease-out 1.35s both;
}
.assistant-panel__fx--wave {
  top: -6px;
  right: 2%;
  font-size: 14px;
  animation: mascot-fx-pop 1.7s ease-out forwards;
}
.assistant-panel__fx--spin {
  top: -12px;
  left: 50%;
  font-size: 14px;
  animation: mascot-fx-float 1.8s ease-out forwards;
}
.assistant-panel__fx--sneeze {
  top: -8px;
  right: 2%;
  font-size: 14px;
  animation: mascot-fx-pop 1s ease-out 0.65s both;
}
.assistant-panel__fx--dance {
  top: -8px;
  left: 50%;
  font-size: 18px;
  animation: mascot-fx-float 1.7s ease-out forwards;
}
.assistant-panel__fx--jump {
  top: -8px;
  left: 2%;
  font-size: 16px;
  animation: mascot-fx-pop 1.9s ease-out forwards;
}
.assistant-panel__fx--angry {
  top: 0;
  right: 2%;
  font-size: 16px;
  animation: mascot-fx-pop 1.8s ease-out forwards;
}
.assistant-panel__fx--startle {
  top: -8px;
  left: 2%;
  font-size: 20px;
  animation: mascot-fx-pop 1.6s ease-out 0.1s both;
}
@keyframes mascot-fx-pop {
  0% {
    opacity: 0;
    transform: scale(0.5) translateY(6px);
  }
  25% {
    opacity: 1;
    transform: scale(1.1) translateY(0);
  }
  60% {
    opacity: 1;
    transform: scale(1);
  }
  100% {
    opacity: 0;
    transform: scale(1) translateY(-8px);
  }
}
@keyframes mascot-fx-float {
  0% {
    opacity: 0;
    transform: translate(-50%, 6px) scale(0.9);
  }
  25% {
    opacity: 1;
    transform: translate(-50%, 0) scale(1);
  }
  100% {
    opacity: 0;
    transform: translate(-50%, -16px) scale(1);
  }
}
.assistant-panel__mascot {
  width: 228px;
  filter: drop-shadow(0 16px 24px rgba(30, 58, 95, 0.14));
}
.assistant-panel__meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  margin-top: 2px;
}
.assistant-panel__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid rgba(37, 99, 235, 0.16);
  border-radius: var(--qh-radius-pill);
  background: rgba(255, 255, 255, 0.85);
  color: #1d4ed8;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.assistant-panel__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.14);
}
.assistant-panel__name {
  margin: 4px 0 0;
  color: var(--qh-ink);
  font-size: var(--qh-fs-md);
  font-weight: 600;
}
.assistant-panel__desc {
  margin: 0;
  color: var(--qh-muted);
  font-size: 11px;
  line-height: 1.7;
}
.sessions {
  grid-area: sessions;
  min-height: 0;
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
  /* 两行布局：标题独占一行（窄侧栏里才不会只剩省略号），操作按钮在下一行常显 */
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: var(--qh-space-2) var(--qh-space-3);
  border-radius: var(--qh-radius-sm);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
.sessions__title {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sessions__actions {
  /* 常显：仅悬停显示在触屏与截图上都不可发现（重命名态的保存 / 取消也会被藏住） */
  display: inline-flex;
  gap: 4px;
  justify-content: flex-end;
}
.sessions__rename {
  width: 100%;
}
.sessions__msg {
  margin: 0 0 var(--qh-space-2);
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.sessions__item:hover {
  background: var(--qh-bg);
}
.sessions__item--active {
  background: var(--qh-primary-weak);
  color: var(--qh-primary);
  font-weight: 600;
}
.chat {
  grid-area: chat;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--qh-border);
  border-radius: var(--qh-radius-lg);
  background: var(--qh-surface);
  box-shadow: var(--qh-shadow-sm);
  overflow: hidden;
}
.chat__messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--qh-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-4);
}
.chat__welcome {
  width: 100%;
  max-width: 640px;
  align-self: center;
  margin-block: auto;
  padding: var(--qh-space-3) 0;
}
.chat__welcome-eyebrow {
  margin: 0 0 12px;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
}
.chat__welcome-title {
  margin: 0 0 10px;
  color: var(--qh-ink);
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.3;
}
.chat__hello {
  max-width: 520px;
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-md);
  line-height: 1.8;
}
.chat__suggestions-label {
  margin: var(--qh-space-5) 0 var(--qh-space-2);
  color: var(--qh-faint);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
}
.chat__suggestions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.chat__suggestion-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 108px;
  padding: 14px;
  border: 1px solid #dbe7f3;
  border-radius: 12px;
  background: #f8fbff;
  color: var(--qh-ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}
.chat__suggestion-card:hover {
  border-color: #93c5fd;
  background: #fff;
  box-shadow: 0 10px 24px -20px rgba(29, 78, 216, 0.55);
  transform: translateY(-2px);
}
.chat__suggestion-index {
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.chat__suggestion-text {
  max-width: 88%;
  font-size: var(--qh-fs-sm);
  font-weight: 500;
  line-height: 1.6;
}
.chat__suggestion-arrow {
  position: absolute;
  right: 12px;
  bottom: 10px;
  color: #93c5fd;
  font-size: 14px;
  line-height: 1;
}
.msg {
  max-width: 78%;
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
}
.msg--user .msg__content {
  background: var(--qh-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.msg--assistant {
  align-self: flex-start;
}
.msg--assistant .msg__content {
  background: var(--qh-bg);
  border: 1px solid var(--qh-border);
  color: var(--qh-ink);
  border-bottom-left-radius: 4px;
}
.msg__knowledge {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg__knowledge-title {
  font-size: 12px;
  color: var(--qh-text-muted, #64748b);
}

.knowledge-card {
  border: 1px solid var(--qh-border, #e2e8f0);
  border-radius: 10px;
  padding: 8px 10px;
  background: var(--qh-surface-soft, #f8fafc);
}

.knowledge-card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.knowledge-card__topic {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--qh-primary, #0e5a6b);
}

.knowledge-card__score {
  font-size: 11px;
  color: var(--qh-text-muted, #64748b);
}

.knowledge-card__excerpt {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--qh-text, #1f2937);
}

.msg__sources {
  margin: var(--qh-space-1) 0 0;
  font-size: var(--qh-fs-xs);
  color: var(--qh-muted);
}
.msg__sources a {
  margin-right: var(--qh-space-2);
}
.chat__footer {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-2);
  padding: var(--qh-space-4);
  border-top: 1px solid var(--qh-border);
  background: var(--qh-surface);
}
.chat__bar {
  display: flex;
  gap: var(--qh-space-3);
  padding: 0;
  border: 0;
  background: transparent;
}
.chat__bar button {
  white-space: nowrap;
}
.chat__error {
  margin: 0;
  color: var(--qh-danger);
  font-size: var(--qh-fs-sm);
}
@media (max-width: 1080px) {
  .chat-layout {
    grid-template-columns: 1fr;
    grid-template-areas:
      'sessions'
      'assistant'
      'chat';
    height: auto;
  }
  .assistant-panel::before {
    display: none;
  }
  .assistant-panel__inner {
    flex-direction: row;
    justify-content: center;
    gap: var(--qh-space-5);
    padding: 12px 24px;
    text-align: left;
  }
  .assistant-panel__mascot {
    flex: none;
    width: 200px;
  }
  .assistant-panel__meta {
    align-items: flex-start;
  }
  .sessions__card {
    max-height: 200px;
  }
  .chat {
    height: 600px;
  }
}
@media (max-width: 900px) {
  .chat {
    height: 560px;
  }
}
@media (max-width: 720px) {
  .assistant-panel__inner {
    gap: var(--qh-space-4);
    padding: 10px 18px;
  }
}
@media (max-width: 600px) {
  .chat__welcome {
    margin-block: 0;
  }
  .chat__welcome-title {
    font-size: 22px;
  }
  .chat__suggestions {
    grid-template-columns: 1fr;
  }
  .chat__suggestion-card {
    flex-direction: row;
    align-items: center;
    gap: 10px;
    min-height: 0;
    padding: 12px 14px;
  }
  .chat__suggestion-text {
    max-width: none;
  }
  .chat__suggestion-arrow {
    position: static;
    margin-left: auto;
  }
  .assistant-panel__mascot {
    width: 160px;
  }
}
@media (max-width: 520px) {
  .assistant-panel__mascot {
    width: 140px;
  }
  .chat__footer {
    padding: 12px;
  }
  .msg {
    max-width: 94%;
  }
}
</style>
