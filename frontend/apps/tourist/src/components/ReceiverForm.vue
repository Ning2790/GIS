<script setup lang="ts">
/** 收货信息表单（下单必填）：默认带出常用地址，可切换或手填；变更通过 change 事件上报。 */

import { listAddresses, type AddressPublic, type ReceiverPayload } from '@qh/api-client';
import { QhInput } from '@qh/ui';
import { onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';

const emit = defineEmits<{ (e: 'change', value: ReceiverPayload): void }>();

const addresses = ref<AddressPublic[]>([]);
const selectedId = ref<number | null>(null);
const name = ref('');
const phone = ref('');
const address = ref('');

function currentValue(): ReceiverPayload {
  return {
    receiver_name: name.value.trim(),
    receiver_phone: phone.value.trim(),
    receiver_address: address.value.trim(),
  };
}

watch([name, phone, address], () => emit('change', currentValue()));

function apply(addressRow: AddressPublic) {
  selectedId.value = addressRow.id;
  name.value = addressRow.receiver_name;
  phone.value = addressRow.receiver_phone;
  address.value = addressRow.address;
}

function onPick(event: Event) {
  const id = Number((event.target as HTMLSelectElement).value);
  const found = addresses.value.find((item) => item.id === id);
  if (found) {
    apply(found);
  }
}

async function load() {
  try {
    addresses.value = await listAddresses();
  } catch {
    addresses.value = []; // 未登录 / 拉取失败：退化为手填
  }
  const preferred = addresses.value.find((item) => item.is_default) ?? addresses.value[0];
  if (preferred) {
    apply(preferred);
  }
  emit('change', currentValue());
}

onMounted(load);
</script>

<template>
  <div class="receiver">
    <label v-if="addresses.length" class="field">
      <span>常用地址（默认已带出）</span>
      <select :value="selectedId ?? ''" class="receiver__select" @change="onPick">
        <option v-for="item in addresses" :key="item.id" :value="item.id">
          {{ item.receiver_name }} · {{ item.receiver_phone }} · {{ item.address
          }}{{ item.is_default ? '（默认）' : '' }}
        </option>
      </select>
    </label>
    <div class="receiver__grid">
      <label class="field">
        <span>收货人</span>
        <QhInput v-model="name" :maxlength="32" placeholder="收货人姓名" />
      </label>
      <label class="field">
        <span>手机号</span>
        <QhInput v-model="phone" :maxlength="11" placeholder="11 位手机号" />
      </label>
    </div>
    <label class="field">
      <span>收货地址</span>
      <QhInput v-model="address" :maxlength="255" placeholder="省 / 市 / 区 + 详细地址" />
    </label>
    <p class="receiver__hint">
      收货信息会随订单保存（快照），之后修改不影响历史订单；可在
      <RouterLink to="/addresses">个人中心 · 收货地址</RouterLink> 管理常用地址。
    </p>
  </div>
</template>

<style scoped>
.receiver {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-3);
}
.receiver__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--qh-space-3);
}
.receiver__select {
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
}
.receiver__hint {
  margin: 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-xs);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--qh-space-1);
  font-size: var(--qh-fs-sm);
  color: var(--qh-ink-2);
}
@media (max-width: 640px) {
  .receiver__grid {
    grid-template-columns: 1fr;
  }
}
</style>
