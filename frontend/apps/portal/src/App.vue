<script setup lang="ts">
/** 统一登录门户（独立入口，5175）。
 *
 * 单卡两态：先选身份（游客 / 商户 / 企业），再切登录 / 注册。
 * - 游客登录 / 注册后回游客端；
 * - 商户 / 企业 / 管理员登录后进控制台；
 * - 开发环境三端不同端口，localStorage 不互通，登录成功用 hash 一次性交接令牌；
 *   生产环境三端同源（/portal/、/、/console/），直接共享登录态。
 */

import {
  ApiError,
  buildTokenHandoffUrl,
  clearTokens,
  consoleUrl,
  login,
  registerEnterprise,
  registerTourist,
  safeRedirectPath,
  touristUrl,
} from '@qh/api-client';
import { QhButton, QhCard, QhInput, QhTag } from '@qh/ui';
import { computed, ref } from 'vue';

import ParticleFlow from './components/ParticleFlow.vue';

type Identity = 'tourist' | 'merchant' | 'enterprise';
type Mode = 'login' | 'register';

const IDENTITIES: { value: Identity; label: string }[] = [
  { value: 'tourist', label: '游客' },
  { value: 'merchant', label: '商户' },
  { value: 'enterprise', label: '企业' },
];

const identity = ref<Identity>('tourist');
const mode = ref<Mode>('login');
const phone = ref('');
const password = ref('');
const nickname = ref('');
const licenseNo = ref('');
const remember = ref(true);
const message = ref('');
const messageOk = ref(false);
const submitting = ref(false);

// 旧登录页跳过来时带上 app 与目标路径，登录成功后回到被拦截的页面
const query = new URLSearchParams(window.location.search);
const rawFrom = query.get('from');
const from = rawFrom === 'tourist' || rawFrom === 'console' ? rawFrom : null;
const redirectPath = safeRedirectPath(query.get('redirect'));

if (from === 'console') {
  identity.value = 'merchant';
}

const isConsoleIdentity = computed(() => identity.value !== 'tourist');

const identityHint = computed(() => {
  if (identity.value === 'tourist') {
    return mode.value === 'login'
      ? '游客登录后回到游客端；注册成功即可登录。'
      : '游客注册立即可用；登录后回到游客端。';
  }
  return mode.value === 'login'
    ? '商户 / 企业 / 管理员登录后自动进入控制台。'
    : '商户 / 企业注册需营业执照号，提交后等待资质审核。';
});

function targetFor(role: string): string {
  const base = role === 'tourist' ? touristUrl() : consoleUrl();
  const sameApp =
    (role === 'tourist' && from === 'tourist') ||
    (role !== 'tourist' && from === 'console');
  return sameApp && redirectPath ? `${base.replace(/\/$/, '')}${redirectPath}` : base;
}

function enterApp(role: string): void {
  const target = targetFor(role);
  // 本地开发 / E2E 三端不同源，需要用 hash 交接令牌；生产同源直接共享登录态
  if (new URL(target).origin !== window.location.origin) {
    const handoff = buildTokenHandoffUrl(target);
    clearTokens();
    window.location.replace(handoff);
    return;
  }
  window.location.replace(target);
}

function pickIdentity(next: Identity): void {
  identity.value = next;
  message.value = '';
}

function pickMode(next: Mode): void {
  mode.value = next;
  message.value = '';
}

function fail(text: string): void {
  messageOk.value = false;
  message.value = text;
}

async function submit(): Promise<void> {
  message.value = '';
  if (!/^1\d{10}$/.test(phone.value.trim())) {
    fail('请输入 11 位手机号');
    return;
  }
  if (password.value.length < 6) {
    fail('密码至少 6 位');
    return;
  }
  if (mode.value === 'register' && isConsoleIdentity.value && !licenseNo.value.trim()) {
    fail('请填写营业执照号');
    return;
  }

  submitting.value = true;
  try {
    if (mode.value === 'register') {
      const trimmedPhone = phone.value.trim();
      if (identity.value === 'tourist') {
        await registerTourist(trimmedPhone, password.value, nickname.value.trim() || undefined);
        messageOk.value = true;
        message.value = '注册成功，请登录';
      } else {
        await registerEnterprise({
          phone: trimmedPhone,
          password: password.value,
          nickname: nickname.value.trim() || undefined,
          license_no: licenseNo.value.trim(),
          role: identity.value === 'enterprise' ? 'enterprise' : 'merchant',
        });
        messageOk.value = true;
        message.value = '注册成功，资质审核中；审核通过后即可登录';
      }
      password.value = '';
      mode.value = 'login';
      return;
    }

    const data = await login(phone.value.trim(), password.value, { remember: remember.value });
    const role = data.user.role;
    if (identity.value === 'tourist' && role !== 'tourist') {
      clearTokens();
      fail('该账号不是游客账号，请切换为「商户」或「企业」身份登录');
      return;
    }
    if (isConsoleIdentity.value && role === 'tourist') {
      clearTokens();
      fail('该账号是游客账号，请切换为「游客」身份登录');
      return;
    }
    enterApp(role);
  } catch (err) {
    fail(err instanceof ApiError ? err.message : '请求失败，请确认后端已启动');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="portal">
    <ParticleFlow class="portal__particles" />
    <main class="portal__panel">
      <header class="brand">
        <p class="brand__eyebrow">青海高原 · 智慧康养平台</p>
        <h1>天境源康</h1>
        <p class="brand__sub">一个入口，按身份注册后登录</p>
      </header>

      <QhCard padding="lg" class="portal-card">
        <div class="identity" role="group" aria-label="选择身份">
          <QhButton
            v-for="item in IDENTITIES"
            :key="item.value"
            :data-testid="`identity-${item.value}`"
            :variant="identity === item.value ? 'primary' : 'ghost'"
            size="sm"
            class="identity__btn"
            @click="pickIdentity(item.value)"
          >
            {{ item.label }}
          </QhButton>
        </div>
        <p class="hint">{{ identityHint }}</p>

        <div class="mode" role="group" aria-label="登录或注册">
          <QhButton
            data-testid="mode-login"
            :variant="mode === 'login' ? 'primary' : 'ghost'"
            size="sm"
            @click="pickMode('login')"
          >
            登录
          </QhButton>
          <QhButton
            data-testid="mode-register"
            :variant="mode === 'register' ? 'primary' : 'ghost'"
            size="sm"
            @click="pickMode('register')"
          >
            注册
          </QhButton>
        </div>

        <form class="form" @submit.prevent="submit">
          <label class="field">
            <span>手机号</span>
            <QhInput
              v-model="phone"
              data-testid="phone"
              type="tel"
              placeholder="11 位手机号"
              autocomplete="username"
              :maxlength="11"
            />
          </label>
          <label class="field">
            <span>密码</span>
            <QhInput
              v-model="password"
              data-testid="password"
              type="password"
              placeholder="至少 6 位"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            />
          </label>

          <template v-if="mode === 'register'">
            <label class="field">
              <span>{{ isConsoleIdentity ? '昵称 / 企业名（选填）' : '昵称（选填）' }}</span>
              <QhInput
                v-model="nickname"
                data-testid="nickname"
                :placeholder="isConsoleIdentity ? '如：某某农牧合作社' : '怎么称呼您'"
              />
            </label>
            <label v-if="isConsoleIdentity" class="field">
              <span>营业执照号（必填）</span>
              <QhInput
                v-model="licenseNo"
                data-testid="license-no"
                placeholder="统一社会信用代码"
              />
            </label>
          </template>

          <label v-if="mode === 'login'" class="remember">
            <input v-model="remember" type="checkbox" />
            记住我（本设备 30 天免密登录）
          </label>

          <QhButton type="submit" class="submit" :disabled="submitting" data-testid="submit">
            {{ submitting ? '提交中…' : mode === 'login' ? '登录' : '注册' }}
          </QhButton>
        </form>

        <p v-if="message" class="message">
          <QhTag :tone="messageOk ? 'success' : 'danger'">{{ message }}</QhTag>
        </p>
      </QhCard>

    </main>

    <footer class="portal__credit">
      <span class="portal__credit-rule" aria-hidden="true"></span>
      <p class="portal__credit-team">经纬方舟团队</p>
      <p class="portal__credit-org">青海师范大学 地理科学学院</p>
    </footer>
  </div>
</template>

<style scoped>
.portal {
  position: relative;
  overflow: hidden;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--qh-space-6) var(--qh-space-4) 96px;
  background:
    radial-gradient(900px 500px at 15% -10%, rgba(6, 182, 212, 0.22), transparent),
    radial-gradient(1000px 600px at 90% 0%, rgba(29, 78, 216, 0.35), transparent),
    var(--qh-ink);
}
.portal__credit {
  position: absolute;
  right: 0;
  bottom: 24px;
  left: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  color: rgba(226, 232, 240, 0.42);
  pointer-events: none;
  text-align: center;
}
.portal__credit-rule {
  width: 26px;
  height: 1px;
  margin-bottom: 4px;
  background: rgba(103, 232, 249, 0.45);
}
.portal__credit p {
  margin: 0;
  font-size: 11px;
  line-height: 1.6;
}
.portal__credit-team {
  color: rgba(226, 232, 240, 0.55);
  font-weight: 500;
  letter-spacing: 0.18em;
}
.portal__credit-org {
  color: rgba(148, 163, 184, 0.5);
  letter-spacing: 0.08em;
}
.portal__particles {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  opacity: 0.82;
}
.portal__panel {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 480px;
}
.brand {
  margin-bottom: var(--qh-space-5);
  text-align: center;
  color: #fff;
}
.brand__eyebrow {
  margin: 0 0 var(--qh-space-2);
  color: var(--qh-accent);
  font-size: var(--qh-fs-xs);
  letter-spacing: 0.2em;
}
.brand h1 {
  margin: 0;
  font-family: SimSun, 'Songti SC', 'STSong', serif;
  font-size: 48px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: 0.12em;
  color: var(--qh-accent);
  text-shadow:
    0 0 30px rgba(6, 182, 212, 0.45),
    0 6px 18px rgba(2, 6, 23, 0.65);
}
.brand__sub {
  margin: var(--qh-space-2) 0 0;
  color: rgba(255, 255, 255, 0.62);
  font-size: var(--qh-fs-md);
}
/* 卡片与整体深蓝 / 青色系保持一致（只覆盖门户页，不改共享组件） */
.portal__panel .portal-card {
  border: 1px solid rgba(125, 211, 252, 0.22);
  background:
    linear-gradient(160deg, rgba(30, 64, 175, 0.34), rgba(15, 23, 42, 0.9) 58%),
    #0f172a;
  box-shadow:
    0 30px 80px rgba(2, 6, 23, 0.6),
    0 0 48px rgba(6, 182, 212, 0.1);
  backdrop-filter: blur(14px);
}
.identity {
  display: flex;
  gap: var(--qh-space-2);
}
.identity__btn {
  flex: 1;
}
.hint {
  min-height: 38px;
  margin: var(--qh-space-3) 0 0;
  color: #94a3b8;
  font-size: var(--qh-fs-sm);
  line-height: 1.45;
}
.mode {
  display: flex;
  gap: var(--qh-space-2);
  margin: var(--qh-space-4) 0;
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-1);
  color: #cbd5e1;
  font-size: var(--qh-fs-sm);
}
.remember {
  display: flex;
  align-items: flex-start;
  gap: var(--qh-space-2);
  color: #cbd5e1;
  font-size: var(--qh-fs-sm);
  cursor: pointer;
}
.remember input {
  margin-top: 2px;
  accent-color: var(--qh-accent);
}
.portal__panel .portal-card :deep(.qh-input) {
  border-color: rgba(148, 163, 184, 0.32);
  background: rgba(2, 6, 23, 0.45);
  color: #f1f5f9;
}
.portal__panel .portal-card :deep(.qh-input::placeholder) {
  color: rgba(148, 163, 184, 0.68);
}
.portal__panel .portal-card :deep(.qh-input:focus) {
  border-color: #22d3ee;
  box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.18);
}
.portal__panel .portal-card :deep(.qh-btn--primary) {
  background: linear-gradient(135deg, #1d4ed8, #06b6d4);
  color: #fff;
  box-shadow: 0 8px 22px rgba(6, 182, 212, 0.26);
}
.portal__panel .portal-card :deep(.qh-btn--primary:hover) {
  background: linear-gradient(135deg, #1e40af, #0891b2);
}
.portal__panel .portal-card :deep(.qh-btn--ghost) {
  border-color: rgba(125, 211, 252, 0.35);
  background: rgba(15, 23, 42, 0.25);
  color: #7dd3fc;
}
.portal__panel .portal-card :deep(.qh-btn--ghost:hover) {
  border-color: rgba(125, 211, 252, 0.6);
  background: rgba(6, 182, 212, 0.14);
}
.portal__panel .portal-card :deep(.qh-tag--success) {
  background: rgba(21, 128, 61, 0.2);
  color: #86efac;
}
.portal__panel .portal-card :deep(.qh-tag--danger) {
  background: rgba(185, 28, 28, 0.22);
  color: #fca5a5;
}
.submit {
  width: 100%;
  margin-top: var(--qh-space-2);
}
.message {
  margin: var(--qh-space-4) 0 0;
}
@media (max-width: 520px) {
  .brand h1 {
    font-size: 34px;
    letter-spacing: 0.08em;
  }
}
</style>
