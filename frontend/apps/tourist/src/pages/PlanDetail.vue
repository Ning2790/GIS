<script setup lang="ts">
import {
  deleteItinerary,
  getItineraryDetail,
  listAttractions,
  replaceItineraryStops,
  type AttractionPublic,
  type ItineraryDetail,
} from '@qh/api-client';
import { QhButton, QhCard, QhEmpty, QhTag } from '@qh/ui';
import { computed, onMounted, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';

interface DraftStop {
  attraction_id: number;
  day: number;
  name: string;
  note: string | null;
}

const route = useRoute();
const router = useRouter();

const itinerary = ref<ItineraryDetail | null>(null);
const attractions = ref<AttractionPublic[]>([]);
const loading = ref(true);
const error = ref('');
const saving = ref(false);

const editing = ref(false);
const draft = ref<DraftStop[]>([]);
const addAttractionId = ref<number | null>(null);
const addDay = ref(1);

/** 按天分组的展示数据（编辑态用 draft，浏览态用 itinerary.stops）。 */
const grouped = computed(() => {
  const groups = new Map<number, { key: string; index: number; name: string; note: string | null; attractionId: number }[]>();
  if (editing.value) {
    draft.value.forEach((item, index) => {
      const list = groups.get(item.day) ?? [];
      list.push({ key: `draft-${index}`, index, name: item.name, note: item.note, attractionId: item.attraction_id });
      groups.set(item.day, list);
    });
  } else if (itinerary.value) {
    for (const stop of itinerary.value.stops) {
      const list = groups.get(stop.day) ?? [];
      list.push({
        key: `stop-${stop.id}`,
        index: -1,
        name: stop.attraction_name ?? `景点 #${stop.attraction_id}`,
        note: stop.note,
        attractionId: stop.attraction_id,
      });
      groups.set(stop.day, list);
    }
  }
  return [...groups.entries()].sort((a, b) => a[0] - b[0]);
});

async function load() {
  loading.value = true;
  error.value = '';
  try {
    itinerary.value = await getItineraryDetail(Number(route.params.id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function loadAttractions() {
  try {
    const data = await listAttractions({ page: 1, page_size: 100 });
    attractions.value = data.items;
  } catch {
    /* 编辑添加时的候选列表；失败则无法添加 */
  }
}

function startEdit() {
  if (!itinerary.value) {
    return;
  }
  draft.value = itinerary.value.stops.map((stop) => ({
    attraction_id: stop.attraction_id,
    day: stop.day,
    name: stop.attraction_name ?? `景点 #${stop.attraction_id}`,
    note: stop.note,
  }));
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  draft.value = [];
}

/** 同天内交换位置（跨天移动请用删除 + 添加到目标天）。 */
function moveWithinDay(index: number, direction: -1 | 1) {
  const item = draft.value[index];
  const siblings = draft.value
    .map((stop, i) => ({ stop, i }))
    .filter((entry) => entry.stop.day === item.day);
  const position = siblings.findIndex((entry) => entry.i === index);
  const target = siblings[position + direction];
  if (!target) {
    return;
  }
  const temp = draft.value[index];
  draft.value[index] = draft.value[target.i];
  draft.value[target.i] = temp;
}

function removeDraftStop(index: number) {
  draft.value.splice(index, 1);
}

function addDraftStop() {
  if (addAttractionId.value === null) {
    return;
  }
  const attraction = attractions.value.find((item) => item.id === addAttractionId.value);
  if (!attraction) {
    return;
  }
  draft.value.push({
    attraction_id: attraction.id,
    day: addDay.value,
    name: attraction.name,
    note: null,
  });
}

async function save() {
  if (!itinerary.value || saving.value) {
    return;
  }
  // 按天 + 数组顺序整理提交（后端按顺序编号同日 position）
  const sorted = [...draft.value].sort((a, b) => a.day - b.day);
  saving.value = true;
  error.value = '';
  try {
    itinerary.value = await replaceItineraryStops(
      itinerary.value.id,
      sorted.map((stop) => ({ attraction_id: stop.attraction_id, day: stop.day, note: stop.note })),
    );
    editing.value = false;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败';
  } finally {
    saving.value = false;
  }
}

async function handleDelete() {
  if (!itinerary.value) {
    return;
  }
  if (!window.confirm(`确定删除行程「${itinerary.value.title}」？`)) {
    return;
  }
  try {
    await deleteItinerary(itinerary.value.id);
    void router.push('/plan');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败';
  }
}

onMounted(() => {
  void load();
  void loadAttractions();
});
</script>

<template>
  <p class="back">
    <RouterLink to="/plan">← 返回行程规划</RouterLink>
  </p>

  <p v-if="loading" class="state">加载中…</p>
  <p v-else-if="error" class="state state--error">{{ error }}</p>

  <template v-else-if="itinerary">
    <QhCard class="head">
      <div class="head__row">
        <h2>{{ itinerary.title }}</h2>
        <div class="head__actions">
          <template v-if="editing">
            <QhButton size="sm" variant="ghost" :disabled="saving" @click="cancelEdit">取消</QhButton>
            <QhButton size="sm" :disabled="saving" @click="save">
              {{ saving ? '保存中…' : '保存' }}
            </QhButton>
          </template>
          <template v-else>
            <QhButton size="sm" variant="ghost" @click="startEdit">编辑停靠点</QhButton>
            <QhButton size="sm" variant="danger" @click="handleDelete">删除</QhButton>
          </template>
        </div>
      </div>
      <div class="head__meta">
        <QhTag tone="default">{{ itinerary.days }} 天</QhTag>
        <QhTag v-if="itinerary.budget != null" tone="default">预算 ￥{{ itinerary.budget }}</QhTag>
        <QhTag v-if="itinerary.total_distance_km != null" tone="default">
          全程约 {{ itinerary.total_distance_km.toFixed(1) }} 公里
        </QhTag>
        <QhTag v-if="itinerary.fitness" tone="default">体力 {{ itinerary.fitness }}</QhTag>
        <QhTag v-if="itinerary.preferences" tone="default">{{ itinerary.preferences }}</QhTag>
      </div>
      <p v-if="itinerary.risk_notes" class="head__notes">{{ itinerary.risk_notes }}</p>
    </QhCard>

    <QhEmpty v-if="grouped.length === 0" text="暂无停靠点，点击「编辑停靠点」添加" />

    <div v-else class="days">
      <QhCard v-for="[day, stops] in grouped" :key="day" class="day">
        <template #header>第 {{ day }} 天</template>
        <ul class="stops">
          <li v-for="(stop, order) in stops" :key="stop.key" class="stops__item">
            <span class="stops__dot">{{ order + 1 }}</span>
            <div class="stops__info">
              <RouterLink :to="`/attractions/${stop.attractionId}`" class="stops__name">
                {{ stop.name }}
              </RouterLink>
              <p v-if="stop.note" class="stops__note">{{ stop.note }}</p>
            </div>
            <div v-if="editing" class="stops__ops">
              <button type="button" :disabled="order === 0" @click="moveWithinDay(stop.index, -1)">
                ↑
              </button>
              <button
                type="button"
                :disabled="order === stops.length - 1"
                @click="moveWithinDay(stop.index, 1)"
              >
                ↓
              </button>
              <button type="button" class="stops__remove" @click="removeDraftStop(stop.index)">
                ✕
              </button>
            </div>
          </li>
        </ul>
      </QhCard>
    </div>

    <QhCard v-if="editing" class="adder">
      <template #header>添加停靠点</template>
      <div class="adder__row">
        <select v-model.number="addAttractionId" class="adder__select">
          <option :value="null" disabled>选择景点</option>
          <option v-for="item in attractions" :key="item.id" :value="item.id">
            {{ item.name }}（{{ item.city }}）
          </option>
        </select>
        <select v-model.number="addDay" class="adder__select adder__select--day">
          <option v-for="day in itinerary.days" :key="day" :value="day">第 {{ day }} 天</option>
        </select>
        <QhButton size="sm" :disabled="addAttractionId === null" @click="addDraftStop">添加</QhButton>
      </div>
    </QhCard>
  </template>
</template>

<style scoped>
.back {
  margin: 0 0 var(--qh-space-4);
  font-size: var(--qh-fs-sm);
}
.head {
  margin-bottom: var(--qh-space-4);
}
.head__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-4);
  margin-bottom: var(--qh-space-3);
}
.head__row h2 {
  margin: 0;
  font-size: var(--qh-fs-xl);
}
.head__actions {
  display: flex;
  gap: var(--qh-space-2);
}
.head__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--qh-space-2);
  margin-bottom: var(--qh-space-3);
}
.head__notes {
  margin: 0;
  padding: var(--qh-space-3) var(--qh-space-4);
  background: var(--qh-warning-bg);
  border-radius: var(--qh-radius-sm);
  color: var(--qh-warning);
  font-size: var(--qh-fs-sm);
  line-height: 1.7;
}
.days {
  display: grid;
  gap: var(--qh-space-4);
}
.stops {
  list-style: none;
  margin: 0;
  padding: 0;
}
.stops__item {
  display: flex;
  align-items: flex-start;
  gap: var(--qh-space-3);
  padding: var(--qh-space-3) 0;
  border-bottom: 1px solid var(--qh-border);
}
.stops__item:last-child {
  border-bottom: none;
}
.stops__dot {
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--qh-primary-weak);
  color: var(--qh-primary);
  font-size: var(--qh-fs-xs);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}
.stops__info {
  flex: 1;
  min-width: 0;
}
.stops__name {
  font-weight: 600;
  color: var(--qh-ink);
}
.stops__note {
  margin: var(--qh-space-1) 0 0;
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.stops__ops {
  display: flex;
  gap: var(--qh-space-2);
}
.stops__ops button {
  border: 1px solid var(--qh-border-strong);
  background: var(--qh-surface);
  border-radius: var(--qh-radius-sm);
  width: 28px;
  height: 28px;
  cursor: pointer;
  color: var(--qh-ink-2);
}
.stops__ops button:disabled {
  color: var(--qh-faint);
  cursor: not-allowed;
}
.stops__remove:hover {
  color: var(--qh-danger);
  border-color: var(--qh-danger);
}
.adder {
  margin-top: var(--qh-space-4);
}
.adder__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--qh-space-3);
}
.adder__select {
  flex: 1;
  min-width: 180px;
  padding: 9px 12px;
  border: 1px solid var(--qh-border-strong);
  border-radius: var(--qh-radius-sm);
  background: var(--qh-surface);
  color: var(--qh-ink);
  font-family: inherit;
  font-size: var(--qh-fs-md);
}
.adder__select--day {
  flex: none;
  min-width: 110px;
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
}
.state--error {
  color: var(--qh-danger);
}
</style>
