<script setup lang="ts">
import {
  ApiError,
  createRoute,
  deleteRoute,
  getRouteDetail,
  listAttractions,
  listRoutes,
  updateRoute,
  type AttractionPublic,
  type RouteDetail,
  type RoutePublic,
} from '@qh/api-client';
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';

const rows = ref<RoutePublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const loading = ref(false);
const error = ref('');

const attractions = ref<AttractionPublic[]>([]);

const dialogVisible = ref(false);
const submitting = ref(false);
const editingId = ref<number | null>(null);
const form = reactive({
  name: '',
  theme: '',
  days: 2,
  budget: 1000 as number | null,
  description: '',
  stops: [] as { attraction_id: number | null; day: number; note: string }[],
});

const RULES = {
  name: [{ required: true, message: '请输入路线名称', trigger: 'blur' }],
  days: [{ required: true, message: '请输入天数', trigger: 'blur' }],
};

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listRoutes({ page: page.value, page_size: pageSize });
    rows.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function loadAttractions() {
  try {
    const data = await listAttractions({ page_size: 50 });
    attractions.value = data.items;
  } catch {
    /* 下拉候选加载失败不阻断列表 */
  }
}

function openCreate() {
  editingId.value = null;
  form.name = '';
  form.theme = '';
  form.days = 2;
  form.budget = 1000;
  form.description = '';
  form.stops = [{ attraction_id: null, day: 1, note: '' }];
  dialogVisible.value = true;
}

async function openEdit(row: RoutePublic) {
  // 列表项不含停靠点，取详情回填
  try {
    const detail: RouteDetail = await getRouteDetail(row.id);
    editingId.value = row.id;
    form.name = detail.name;
    form.theme = detail.theme;
    form.days = detail.days;
    form.budget = detail.budget;
    form.description = detail.description;
    form.stops = detail.stops.map((stop) => ({
      attraction_id: stop.attraction_id,
      day: stop.day,
      note: stop.note ?? '',
    }));
    dialogVisible.value = true;
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '加载路线详情失败');
  }
}

function addStop() {
  form.stops.push({ attraction_id: null, day: 1, note: '' });
}

function removeStop(index: number) {
  form.stops.splice(index, 1);
}

async function submit() {
  const valid = form.stops.every((stop) => stop.attraction_id !== null);
  if (!valid) {
    ElMessage.warning('每个停靠点都要选择景点');
    return;
  }
  submitting.value = true;
  try {
    const payload = {
      name: form.name,
      theme: form.theme,
      days: form.days,
      budget: form.budget,
      description: form.description,
      stops: form.stops.map((stop) => ({
        attraction_id: stop.attraction_id as number,
        day: stop.day,
        note: stop.note || null,
      })),
    };
    if (editingId.value === null) {
      await createRoute(payload);
      ElMessage.success('路线已创建');
      page.value = 1;
    } else {
      await updateRoute(editingId.value, payload);
      ElMessage.success('路线已保存');
    }
    dialogVisible.value = false;
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '保存失败');
  } finally {
    submitting.value = false;
  }
}

async function removeRoute(row: RoutePublic) {
  await ElMessageBox.confirm(
    `删除路线「${row.name}」？删除后游客端将不再展示（已套用为个人行程的不受影响）。`,
    '删除路线',
    { type: 'warning' },
  );
  try {
    await deleteRoute(row.id);
    ElMessage.success('已删除');
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '删除失败');
  }
}

onMounted(() => {
  void load();
  void loadAttractions();
});
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>路线管理（预设路线，游客可一键套用）</span>
        <el-button type="primary" @click="openCreate">新建路线</el-button>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="theme" label="主题" width="90" />
      <el-table-column prop="days" label="天数" width="80" />
      <el-table-column label="停靠点" width="90">
        <template #default="{ row }">{{ row.stop_count }} 个</template>
      </el-table-column>
      <el-table-column label="人均预估" width="110">
        <template #default="{ row }">{{ row.budget ? `￥${row.budget}` : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="removeRoute(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        layout="prev, pager, next, total"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="(next: number) => { page = next; load(); }"
      />
    </div>
  </el-card>

  <el-dialog
    v-model="dialogVisible"
    :title="editingId === null ? '新建路线' : '编辑路线'"
    width="720px"
  >
    <el-form :model="form" :rules="RULES" label-width="90px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" maxlength="128" placeholder="如：青海湖 + 茶卡经典 3 日环线" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="主题">
            <el-input v-model="form.theme" maxlength="32" placeholder="环湖 / 人文 / 摄影" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="天数" prop="days">
            <el-input-number v-model="form.days" :min="1" :max="15" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="人均预估">
            <el-input-number v-model="form.budget" :min="0" :max="99999999" :precision="0" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="介绍">
        <el-input v-model="form.description" type="textarea" :rows="3" maxlength="2000" />
      </el-form-item>
      <el-form-item label="停靠点">
        <div class="stops">
          <div v-for="(stop, index) in form.stops" :key="index" class="stops__row">
            <el-select
              v-model="stop.attraction_id"
              placeholder="选择景点"
              style="flex: 1"
              filterable
            >
              <el-option
                v-for="item in attractions"
                :key="item.id"
                :label="`${item.name}（${item.city}）`"
                :value="item.id"
              />
            </el-select>
            <el-input-number v-model="stop.day" :min="1" :max="form.days" style="width: 110px" />
            <el-input v-model="stop.note" placeholder="当日提示（选填）" style="flex: 1" />
            <el-button link type="danger" @click="removeStop(index)">移除</el-button>
          </div>
          <el-button link type="primary" @click="addStop">＋ 添加停靠点</el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ editingId === null ? '创建路线' : '保存修改' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.stops {
  width: 100%;
}
.stops__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
