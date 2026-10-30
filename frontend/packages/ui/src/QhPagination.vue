<script setup lang="ts">
/** 分页控件（上一页 / 下一页 + 页码信息）· C 风格基线组件。 */
import { computed } from 'vue';

import QhButton from './QhButton.vue';

const props = withDefaults(
  defineProps<{ page: number; pageSize: number; total: number }>(),
  { pageSize: 12 },
);
const emit = defineEmits<{ change: [page: number] }>();

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)));
</script>

<template>
  <div class="qh-pagination">
    <QhButton
      variant="ghost"
      size="sm"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      上一页
    </QhButton>
    <span class="qh-pagination__info">{{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
    <QhButton
      variant="ghost"
      size="sm"
      :disabled="page >= totalPages"
      @click="emit('change', page + 1)"
    >
      下一页
    </QhButton>
  </div>
</template>

<style scoped>
.qh-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--qh-space-4);
  margin-top: var(--qh-space-5);
}
.qh-pagination__info {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
</style>
