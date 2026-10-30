<script setup lang="ts">
import {
  ApiError,
  closeDemand,
  closeSupply,
  createDemand,
  createSupply,
  listDemands,
  listSupplies,
  matchDemand,
  type B2bCreatePayload,
  type B2bMatchItem,
  type B2bPostPublic,
} from '@qh/api-client';
import { ElMessage, type FormInstance } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';

import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();

const tab = ref<'supplies' | 'demands'>('supplies');
const rows = ref<B2bPostPublic[]>([]);
const loading = ref(false);
const error = ref('');

const dialogVisible = ref(false);
const submitting = ref(false);
const formRef = ref<FormInstance>();
const form = reactive<B2bCreatePayload>({
  title: '',
  category: '',
  region: '',
  quantity: 1,
  unit: '吨',
  price_expect: null,
  description: '',
});

const matchVisible = ref(false);
const matchLoading = ref(false);
const matchItems = ref<B2bMatchItem[]>([]);

const RULES = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  category: [{ required: true, message: '请输入品类', trigger: 'blur' }],
  region: [{ required: true, message: '请输入地区', trigger: 'blur' }],
};

/** 我的发布：列表接口返回全部开放中信息，这里按发布者过滤 */
function myRows() {
  return rows.value.filter((item) => item.user_id === auth.user?.id);
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = tab.value === 'supplies' ? await listSupplies({ page: 1, page_size: 100 }) : await listDemands({ page: 1, page_size: 100 });
    rows.value = data.items;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

function openDialog() {
  form.title = '';
  form.category = '';
  form.region = '';
  form.quantity = 1;
  form.unit = '吨';
  form.price_expect = null;
  form.description = '';
  dialogVisible.value = true;
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) {
    return;
  }
  submitting.value = true;
  try {
    if (tab.value === 'supplies') {
      await createSupply({ ...form });
    } else {
      await createDemand({ ...form });
    }
    ElMessage.success('发布成功');
    dialogVisible.value = false;
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '发布失败');
  } finally {
    submitting.value = false;
  }
}

async function handleClose(row: B2bPostPublic) {
  try {
    if (tab.value === 'supplies') {
      await closeSupply(row.id);
    } else {
      await closeDemand(row.id);
    }
    ElMessage.success('已关闭');
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  }
}

async function handleMatch(row: B2bPostPublic) {
  matchVisible.value = true;
  matchLoading.value = true;
  matchItems.value = [];
  try {
    const result = await matchDemand(row.id);
    matchItems.value = result.matches;
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '匹配失败');
  } finally {
    matchLoading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <el-radio-group v-model="tab" @change="load">
          <el-radio-button value="supplies">我的供给</el-radio-button>
          <el-radio-button value="demands">我的需求</el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="openDialog">
          {{ tab === 'supplies' ? '发布供给' : '发布需求' }}
        </el-button>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />

    <el-table :data="myRows()" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
      <el-table-column prop="category" label="品类" width="110" />
      <el-table-column prop="region" label="地区" width="110" />
      <el-table-column label="数量" width="120">
        <template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template>
      </el-table-column>
      <el-table-column label="期望单价" width="110">
        <template #default="{ row }">
          {{ row.price_expect != null ? `￥${row.price_expect}` : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170">
        <template #default="{ row }">
          <el-button
            v-if="tab === 'demands'"
            link
            type="primary"
            @click="handleMatch(row)"
          >
            发起匹配
          </el-button>
          <el-button link type="danger" @click="handleClose(row)">关闭</el-button>
        </template>
      </el-table-column>
    </el-table>
    <p v-if="!loading && myRows().length === 0" class="empty-hint">
      我发布的{{ tab === 'supplies' ? '供给' : '需求' }}暂无开放中的信息
    </p>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="tab === 'supplies' ? '发布供给' : '发布需求'" width="520px">
    <el-form ref="formRef" :model="form" :rules="RULES" label-width="90px">
      <el-form-item label="标题" prop="title">
        <el-input v-model="form.title" maxlength="128" placeholder="如：祁连山牦牛肉干直供" />
      </el-form-item>
      <el-form-item label="品类" prop="category">
        <el-input v-model="form.category" maxlength="64" placeholder="如：肉制品" />
      </el-form-item>
      <el-form-item label="地区" prop="region">
        <el-input v-model="form.region" maxlength="64" placeholder="如：海北州" />
      </el-form-item>
      <el-form-item label="数量" prop="quantity">
        <el-input-number v-model="form.quantity" :min="0.01" :max="99999999" />
        <el-input v-model="form.unit" class="unit" maxlength="16" placeholder="单位" />
      </el-form-item>
      <el-form-item label="期望单价">
        <el-input-number v-model="form.price_expect" :min="0.01" :max="99999999" placeholder="选填" />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="3" maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">发布</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="matchVisible" title="规则匹配结果（品类一致 + 地区 / 数量加分）" width="560px">
    <div v-loading="matchLoading">
      <el-empty v-if="!matchLoading && matchItems.length === 0" description="暂无匹配的供给信息" />
      <el-table v-else :data="matchItems" size="small">
        <el-table-column label="供给" min-width="180">
          <template #default="{ row }">{{ row.supply.title }}</template>
        </el-table-column>
        <el-table-column label="地区" width="100">
          <template #default="{ row }">{{ row.supply.region }}</template>
        </el-table-column>
        <el-table-column label="数量" width="110">
          <template #default="{ row }">{{ row.supply.quantity }} {{ row.supply.unit }}</template>
        </el-table-column>
        <el-table-column label="匹配分" width="90">
          <template #default="{ row }">
            <el-tag :type="row.score >= 80 ? 'success' : 'primary'" size="small">{{ row.score }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.unit {
  width: 90px;
  margin-left: 8px;
}
.empty-hint {
  margin: 12px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
