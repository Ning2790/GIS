<script setup lang="ts">
import { ApiError, changePassword, fetchMe, listDevices, revokeDevice, updateProfile } from '@qh/api-client';
import type { DevicePublic } from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhInput, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();

const loading = ref(true);
const error = ref('');

const nickname = ref('');
const nicknameMsg = ref('');
const nicknameOk = ref(false);
const savingNickname = ref(false);

const oldPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const passwordMsg = ref('');
const passwordOk = ref(false);
const savingPassword = ref(false);

// 登录设备（需求量 4.2 的设备绑定：二次访问免密 + 逐设备移除）
const devices = ref<DevicePublic[]>([]);
const devicesMsg = ref('');
const devicesOk = ref(false);
const revokingId = ref<number | null>(null);

const ROLE_LABEL: Record<string, string> = {
  tourist: '游客',
  merchant: '商户',
  enterprise: '企业',
  admin: '管理员',
};

const STATUS_LABEL: Record<string, string> = {
  active: '正常',
  pending_review: '待审核',
  rejected: '已驳回',
  disabled: '已禁用',
};

const profile = ref<{
  id: number;
  phone: string;
  role: string;
  status: string;
  nickname: string | null;
  created_at: string;
} | null>(null);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    profile.value = await fetchMe();
    nickname.value = profile.value.nickname ?? '';
    await loadDevices();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function loadDevices() {
  try {
    devices.value = await listDevices();
  } catch {
    devices.value = []; // 设备列表失败不阻塞个人中心其他功能
  }
}

async function removeDevice(device: DevicePublic) {
  const name = device.device_label ?? `设备 ${device.id}`;
  if (!window.confirm(`确定移除「${name}」？该设备上的登录将失效，需要重新登录。`)) {
    return;
  }
  revokingId.value = device.id;
  devicesMsg.value = '';
  try {
    await revokeDevice(device.id);
    devicesOk.value = true;
    devicesMsg.value = device.is_current
      ? '当前设备已移除，本机会在下次刷新时退出登录'
      : `已移除「${name}」`;
    await loadDevices();
  } catch (err) {
    devicesOk.value = false;
    devicesMsg.value = err instanceof ApiError ? err.message : '移除失败';
  } finally {
    revokingId.value = null;
  }
}

async function saveNickname() {
  if (savingNickname.value) {
    return;
  }
  nicknameMsg.value = '';
  savingNickname.value = true;
  try {
    profile.value = await updateProfile(nickname.value.trim());
    await auth.fetchUser(); // 顶栏昵称同步（auth store 是展示来源）
    nicknameOk.value = true;
    nicknameMsg.value = '昵称已保存';
  } catch (err) {
    nicknameOk.value = false;
    nicknameMsg.value = err instanceof ApiError ? err.message : '保存失败';
  } finally {
    savingNickname.value = false;
  }
}

async function savePassword() {
  if (savingPassword.value) {
    return;
  }
  passwordMsg.value = '';
  if (newPassword.value.length < 6) {
    passwordOk.value = false;
    passwordMsg.value = '新密码至少 6 位';
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordOk.value = false;
    passwordMsg.value = '两次输入的新密码不一致';
    return;
  }
  savingPassword.value = true;
  try {
    await changePassword(oldPassword.value, newPassword.value);
    passwordOk.value = true;
    passwordMsg.value = '密码已修改，其他设备已退出登录';
    oldPassword.value = '';
    newPassword.value = '';
    confirmPassword.value = '';
  } catch (err) {
    passwordOk.value = false;
    passwordMsg.value = err instanceof ApiError ? err.message : '修改失败';
  } finally {
    savingPassword.value = false;
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

onMounted(load);
</script>

<template>
  <PageTitle title="个人中心" subtitle="查看账号信息，修改昵称与登录密码" />

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>

  <div v-else-if="profile" class="grid">
    <QhCard>
      <template #header>账号信息</template>
      <dl class="info">
        <dt>ID</dt>
        <dd>{{ profile.id }}</dd>
        <dt>手机号</dt>
        <dd>{{ profile.phone }}</dd>
        <dt>角色</dt>
        <dd>
          <QhTag tone="primary">{{ ROLE_LABEL[profile.role] ?? profile.role }}</QhTag>
        </dd>
        <dt>状态</dt>
        <dd>
          <QhTag :tone="profile.status === 'active' ? 'success' : 'warning'">
            {{ STATUS_LABEL[profile.status] ?? profile.status }}
          </QhTag>
        </dd>
        <dt>注册时间</dt>
        <dd>{{ formatTime(profile.created_at) }}</dd>
      </dl>
    </QhCard>

    <div class="column">
      <QhCard>
        <template #header>昵称</template>
        <div class="field">
          <QhInput v-model="nickname" :maxlength="64" placeholder="给自己起个昵称" />
          <QhButton size="sm" :disabled="savingNickname" @click="saveNickname">
            {{ savingNickname ? '保存中…' : '保存昵称' }}
          </QhButton>
        </div>
        <p v-if="nicknameMsg" class="state" :class="{ 'state--error': !nicknameOk }">
          {{ nicknameMsg }}
        </p>
      </QhCard>

      <QhCard>
        <template #header>修改密码</template>
        <div class="form">
          <label class="field field--stack">
            <span>原密码</span>
            <QhInput v-model="oldPassword" type="password" placeholder="当前登录密码" />
          </label>
          <label class="field field--stack">
            <span>新密码（6–64 位）</span>
            <QhInput v-model="newPassword" type="password" placeholder="至少 6 位" />
          </label>
          <label class="field field--stack">
            <span>确认新密码</span>
            <QhInput v-model="confirmPassword" type="password" placeholder="再输一次新密码" />
          </label>
          <QhButton size="sm" :disabled="savingPassword" @click="savePassword">
            {{ savingPassword ? '提交中…' : '修改密码' }}
          </QhButton>
          <p class="hint">修改成功后，其他设备上的登录会失效，需要重新登录。</p>
        </div>
        <p v-if="passwordMsg" class="state" :class="{ 'state--error': !passwordOk }">
          {{ passwordMsg }}
        </p>
      </QhCard>

      <QhCard>
        <template #header>收货地址</template>
        <p class="hint">维护常用收货地址；下单结算时自动带出默认地址。</p>
        <p class="addresses-link">
          <RouterLink to="/addresses">管理收货地址 →</RouterLink>
        </p>
      </QhCard>

      <QhCard>
        <template #header>我的收藏</template>
        <p class="hint">心动过的青海特产清单，在商品详情页点心形按钮即可加进来。</p>
        <p class="addresses-link">
          <RouterLink to="/favorites">查看我的收藏 →</RouterLink>
        </p>
      </QhCard>

      <QhCard>
        <template #header>浏览历史</template>
        <p class="hint">最近看过的商品会自动记录（同一件只记一次，重复浏览刷新时间）。</p>
        <p class="addresses-link">
          <RouterLink to="/history">查看浏览历史 →</RouterLink>
        </p>
      </QhCard>

      <QhCard>
        <template #header>售后记录</template>
        <p class="hint">已提交的售后单处理进度（商户受理 / 完成 / 拒绝）都在这里跟踪。</p>
        <p class="addresses-link">
          <RouterLink to="/after-sales">查看我的售后 →</RouterLink>
        </p>
      </QhCard>

      <QhCard>
        <template #header>登录设备</template>
        <p class="hint">
          已绑定设备在本机二次访问时可免密登录（勾选「记住我」为 30 天）；移除后该设备上的登录立即失效。
        </p>
        <p v-if="devices.length === 0" class="hint">暂无已绑定设备。</p>
        <ul v-else class="devices">
          <li v-for="device in devices" :key="device.id" class="devices__item">
            <div class="devices__meta">
              <p class="devices__name">
                {{ device.device_label ?? '未知设备' }}
                <QhTag v-if="device.is_current" tone="primary">当前设备</QhTag>
              </p>
              <p class="devices__sub">
                最近活跃：{{ formatTime(device.last_seen_at) }}
                <span v-if="device.last_ip"> · IP {{ device.last_ip }}</span>
              </p>
            </div>
            <QhButton
              variant="ghost"
              size="sm"
              :disabled="revokingId === device.id"
              @click="removeDevice(device)"
            >
              {{ revokingId === device.id ? '移除中…' : '移除' }}
            </QhButton>
          </li>
        </ul>
        <p v-if="devicesMsg" class="state" :class="{ 'state--error': !devicesOk }">
          {{ devicesMsg }}
        </p>
      </QhCard>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: var(--qh-space-4);
  align-items: start;
}
.column {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-4);
}
.info {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--qh-space-2) var(--qh-space-4);
  margin: 0;
  font-size: var(--qh-fs-sm);
}
.info dt {
  color: var(--qh-muted);
}
.info dd {
  margin: 0;
}
.field {
  display: flex;
  align-items: center;
  gap: var(--qh-space-3);
}
.field--stack {
  flex-direction: column;
  align-items: stretch;
  gap: var(--qh-space-1);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
  max-width: 420px;
}
.hint {
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.addresses-link {
  margin: var(--qh-space-3) 0 0;
  font-size: var(--qh-fs-sm);
}
.devices {
  list-style: none;
  margin: var(--qh-space-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
}
.devices__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-3);
  padding-bottom: var(--qh-space-3);
  border-bottom: 1px solid var(--qh-border);
}
.devices__item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}
.devices__meta {
  min-width: 0;
}
.devices__name {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--qh-space-2);
  font-size: var(--qh-fs-sm);
}
.devices__sub {
  margin: var(--qh-space-1) 0 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.state {
  margin: var(--qh-space-2) 0 0;
  color: var(--qh-success, #15803d);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
