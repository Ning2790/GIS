<script setup lang="ts">
/** 收货地址簿（个人中心）：新增 / 编辑 / 删除 / 设默认；下单时自动带出默认地址。 */

import {
  ApiError,
  createAddress,
  deleteAddress,
  listAddresses,
  setDefaultAddress,
  updateAddress,
  type AddressPayload,
  type AddressPublic,
} from '@qh/api-client';
import { PageTitle, QhButton, QhCard, QhEmpty, QhInput, QhTag } from '@qh/ui';
import { onMounted, ref } from 'vue';

const rows = ref<AddressPublic[]>([]);
const loading = ref(true);
const error = ref('');
const message = ref('');
const messageOk = ref(false);
const saving = ref(false);
const busyId = ref<number | null>(null);

const formOpen = ref(false);
const editingId = ref<number | null>(null);
const form = ref<AddressPayload & { is_default: boolean }>({
  receiver_name: '',
  receiver_phone: '',
  address: '',
  is_default: false,
});

function resetForm() {
  form.value = { receiver_name: '', receiver_phone: '', address: '', is_default: false };
  editingId.value = null;
}

function openCreate() {
  resetForm();
  formOpen.value = true;
  message.value = '';
}

function openEdit(row: AddressPublic) {
  editingId.value = row.id;
  form.value = {
    receiver_name: row.receiver_name,
    receiver_phone: row.receiver_phone,
    address: row.address,
    is_default: row.is_default,
  };
  formOpen.value = true;
  message.value = '';
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    rows.value = await listAddresses();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function submit() {
  message.value = '';
  const payload: AddressPayload = {
    receiver_name: form.value.receiver_name.trim(),
    receiver_phone: form.value.receiver_phone.trim(),
    address: form.value.address.trim(),
    is_default: form.value.is_default,
  };
  if (!payload.receiver_name) {
    messageOk.value = false;
    message.value = '请填写收货人';
    return;
  }
  if (!/^1[3-9]\d{9}$/.test(payload.receiver_phone)) {
    messageOk.value = false;
    message.value = '请填写 11 位手机号';
    return;
  }
  if (payload.address.length < 5) {
    messageOk.value = false;
    message.value = '请填写完整收货地址（至少 5 个字）';
    return;
  }
  saving.value = true;
  try {
    if (editingId.value === null) {
      await createAddress(payload);
      messageOk.value = true;
      message.value = '地址已保存';
    } else {
      await updateAddress(editingId.value, payload);
      messageOk.value = true;
      message.value = '地址已更新';
    }
    formOpen.value = false;
    resetForm();
    await load();
  } catch (err) {
    messageOk.value = false;
    message.value = err instanceof ApiError ? err.message : '保存失败';
  } finally {
    saving.value = false;
  }
}

async function makeDefault(row: AddressPublic) {
  busyId.value = row.id;
  message.value = '';
  try {
    await setDefaultAddress(row.id);
    messageOk.value = true;
    message.value = `已将「${row.receiver_name}」设为默认地址`;
    await load();
  } catch (err) {
    messageOk.value = false;
    message.value = err instanceof ApiError ? err.message : '操作失败';
  } finally {
    busyId.value = null;
  }
}

async function remove(row: AddressPublic) {
  if (!window.confirm(`确定删除「${row.receiver_name}」的地址？`)) {
    return;
  }
  busyId.value = row.id;
  message.value = '';
  try {
    await deleteAddress(row.id);
    messageOk.value = true;
    message.value = '地址已删除';
    await load();
  } catch (err) {
    messageOk.value = false;
    message.value = err instanceof ApiError ? err.message : '删除失败';
  } finally {
    busyId.value = null;
  }
}

onMounted(load);
</script>

<template>
  <PageTitle title="收货地址" subtitle="下单时自动带出默认地址；最多保存 20 个" />

  <div class="toolbar">
    <QhButton size="sm" @click="openCreate">新增地址</QhButton>
  </div>

  <p v-if="message" class="state">
    <QhTag :tone="messageOk ? 'success' : 'danger'">{{ message }}</QhTag>
  </p>

  <QhCard v-if="formOpen" class="form-card">
    <template #header>{{ editingId === null ? '新增收货地址' : '编辑收货地址' }}</template>
    <div class="form">
      <div class="form__grid">
        <label class="field">
          <span>收货人</span>
          <QhInput v-model="form.receiver_name" :maxlength="32" placeholder="收货人姓名" />
        </label>
        <label class="field">
          <span>手机号</span>
          <QhInput v-model="form.receiver_phone" :maxlength="11" placeholder="11 位手机号" />
        </label>
      </div>
      <label class="field">
        <span>收货地址</span>
        <QhInput v-model="form.address" :maxlength="255" placeholder="省 / 市 / 区 + 详细地址" />
      </label>
      <label class="check">
        <input
          v-model="form.is_default"
          type="checkbox"
          :disabled="editingId !== null && form.is_default"
        />
        设为默认地址
        <span v-if="editingId !== null && form.is_default" class="check__hint">
          （当前默认地址；如需更换，请把其他地址设为默认）
        </span>
      </label>
      <div class="form__actions">
        <QhButton size="sm" :disabled="saving" @click="submit">
          {{ saving ? '保存中…' : '保存' }}
        </QhButton>
        <QhButton
          size="sm"
          variant="ghost"
          @click="
            formOpen = false;
            resetForm();
          "
        >
          取消
        </QhButton>
      </div>
    </div>
  </QhCard>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>
  <QhEmpty v-else-if="rows.length === 0 && !formOpen" text="还没有收货地址，点「新增地址」添加" />
  <div v-else class="list">
    <QhCard v-for="row in rows" :key="row.id" class="list__item">
      <div class="list__main">
        <p class="list__name">
          {{ row.receiver_name }} <span class="list__phone">{{ row.receiver_phone }}</span>
          <QhTag v-if="row.is_default" tone="primary">默认</QhTag>
        </p>
        <p class="list__address">{{ row.address }}</p>
      </div>
      <div class="list__actions">
        <QhButton
          v-if="!row.is_default"
          size="sm"
          variant="ghost"
          :disabled="busyId === row.id"
          @click="makeDefault(row)"
        >
          设为默认
        </QhButton>
        <QhButton size="sm" variant="ghost" @click="openEdit(row)">编辑</QhButton>
        <QhButton size="sm" variant="ghost" :disabled="busyId === row.id" @click="remove(row)">
          删除
        </QhButton>
      </div>
    </QhCard>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--qh-space-3);
}
.form-card {
  margin-bottom: var(--qh-space-4);
}
.form {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
  max-width: 560px;
}
.form__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--qh-space-3);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-1);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
.check {
  display: flex;
  align-items: center;
  gap: var(--qh-space-2);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
  cursor: pointer;
}
.check input {
  accent-color: var(--qh-accent);
}
.check input:disabled {
  cursor: not-allowed;
}
.check__hint {
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.form__actions {
  display: flex;
  gap: var(--qh-space-2);
}
.list {
  display: grid;
  gap: var(--qh-space-3);
}
.list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-4);
}
.list__main {
  min-width: 0;
}
.list__name {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--qh-space-2);
  font-size: var(--qh-fs-md);
}
.list__phone {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.list__address {
  margin: var(--qh-space-1) 0 0;
  color: var(--qh-ink-2);
  font-size: var(--qh-fs-sm);
}
.list__actions {
  display: flex;
  gap: var(--qh-space-1);
  flex-shrink: 0;
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 640px) {
  .form__grid {
    grid-template-columns: 1fr;
  }
  .list__item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
