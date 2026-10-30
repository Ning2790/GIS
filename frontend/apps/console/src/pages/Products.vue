<script setup lang="ts">
import {
  ApiError,
  createProduct,
  listMyProducts,
  setProductStatus,
  updateProduct,
  uploadFile,
  type FilePublic,
  type ProductPublic,
} from '@qh/api-client';
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type UploadRequestOptions,
} from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';

import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
// 只能编辑自己的商品（管理员看全平台列表时不显示编辑入口）
const myId = computed(() => auth.user?.id ?? 0);

const rows = ref<ProductPublic[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const loading = ref(false);
const error = ref('');
const statusFilter = ref<'' | 'on_sale' | 'off_shelf'>('');

const dialogVisible = ref(false);
const submitting = ref(false);
const uploading = ref(false);
const imagePreview = ref('');
// 编辑模式：editingId 非空表示编辑该商品；imageCleared 表示已移除原主图
const editingId = ref<number | null>(null);
const imageCleared = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({
  name: '',
  price: 0,
  stock: 0,
  description: '',
  image_file_id: null as number | null,
});

const RULES = {
  name: [{ required: true, message: '请输入商品名称', trigger: 'blur' }],
  price: [{ required: true, message: '请输入价格', trigger: 'blur' }],
};

/** 自定义上传：先传为公开图片，拿到平台文件 id 供上架时引用。 */
async function handleImageUpload(options: UploadRequestOptions) {
  uploading.value = true;
  try {
    const result = await uploadFile(options.file as File, { public: true });
    form.image_file_id = result.id;
    imagePreview.value = result.url;
    imageCleared.value = false;
    ElMessage.success(compressHint(result));
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '图片上传失败');
  } finally {
    uploading.value = false;
  }
}

/** 服务端上传时会压缩图片：有压缩发生时把「原始 → 存入」告诉商户（无压缩则普通提示）。 */
function compressHint(result: FilePublic): string {
  const original = result.original_size ?? 0;
  if (!original || result.size >= original) {
    return '图片已上传';
  }
  const saved = Math.round((1 - result.size / original) * 100);
  return `图片已上传并压缩：${formatSize(original)} → ${formatSize(result.size)}（省 ${saved}%）`;
}

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function clearImage() {
  form.image_file_id = null;
  imagePreview.value = '';
  imageCleared.value = true;
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await listMyProducts(
      page.value,
      pageSize,
      statusFilter.value === '' ? undefined : statusFilter.value,
    );
    rows.value = data.items;
    total.value = data.total;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

/** 上架 / 下架（下架后公开列表不可见、不可购买）。 */
async function toggleStatus(row: ProductPublic) {
  const offShelf = row.status === 'on_sale';
  if (offShelf) {
    await ElMessageBox.confirm(`下架「${row.name}」？下架后商城不再展示且不可购买。`, '下架', {
      type: 'warning',
    });
  }
  try {
    await setProductStatus(row.id, offShelf ? 'off_shelf' : 'on_sale');
    ElMessage.success(offShelf ? '已下架' : '已上架');
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '操作失败');
  }
}

function openDialog() {
  editingId.value = null;
  form.name = '';
  form.price = 0;
  form.stock = 0;
  form.description = '';
  form.image_file_id = null;
  imagePreview.value = '';
  imageCleared.value = false;
  dialogVisible.value = true;
}

function openEditDialog(row: ProductPublic) {
  editingId.value = row.id;
  form.name = row.name;
  form.price = row.price;
  form.stock = row.stock;
  form.description = row.description;
  form.image_file_id = null; // 未换图时不提交该字段
  imagePreview.value = row.image_url ?? '';
  imageCleared.value = false;
  dialogVisible.value = true;
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) {
    return;
  }
  submitting.value = true;
  try {
    if (editingId.value === null) {
      await createProduct({
        name: form.name,
        price: form.price,
        stock: form.stock,
        description: form.description,
        image_file_id: form.image_file_id,
      });
      ElMessage.success('上架成功');
      page.value = 1;
    } else {
      const payload: {
        name: string;
        price: number;
        stock: number;
        description: string;
        image_file_id?: number | null;
      } = {
        name: form.name,
        price: form.price,
        stock: form.stock,
        description: form.description,
      };
      // 换图 → 提交新文件 id；移除 → 提交 null；未动图 → 不提交该字段
      if (form.image_file_id !== null) {
        payload.image_file_id = form.image_file_id;
      } else if (imageCleared.value) {
        payload.image_file_id = null;
      }
      await updateProduct(editingId.value, payload);
      ElMessage.success('已保存');
    }
    dialogVisible.value = false;
    void load();
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '保存失败');
  } finally {
    submitting.value = false;
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

onMounted(load);
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>商品管理</span>
        <div class="head__actions">
          <el-select
            v-model="statusFilter"
            placeholder="全部状态"
            clearable
            style="width: 130px"
            @change="() => { page = 1; load(); }"
          >
            <el-option label="在售" value="on_sale" />
            <el-option label="已下架" value="off_shelf" />
          </el-select>
          <el-button type="primary" @click="openDialog">上架商品</el-button>
        </div>
      </div>
    </template>

    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="主图" width="90">
        <template #default="{ row }">
          <!-- 列表用缩略图（服务端生成的 400px 图），点击预览看原图 -->
          <el-image
            v-if="row.image_url"
            :src="row.image_thumbnail_url ?? row.image_url"
            :preview-src-list="[row.image_url]"
            preview-teleported
            fit="cover"
            class="thumb"
          />
          <span v-else class="thumb thumb--empty">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="price" label="价格（元）" width="110" />
      <el-table-column prop="stock" label="库存" width="90" />
      <!-- 收藏数：买家关注度（收藏增强项），商户侧只读 -->
      <el-table-column label="收藏" width="80">
        <template #default="{ row }">
          <span :class="{ 'favorite-zero': !row.favorite_count }">
            {{ row.favorite_count ?? 0 }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'on_sale' ? 'success' : 'info'" size="small">
            {{ row.status === 'on_sale' ? '在售' : '已下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button v-if="row.merchant_id === myId" link type="primary" @click="openEditDialog(row)">
            编辑
          </el-button>
          <el-button
            link
            :type="row.status === 'on_sale' ? 'danger' : 'success'"
            @click="toggleStatus(row)"
          >
            {{ row.status === 'on_sale' ? '下架' : '上架' }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
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

  <el-dialog v-model="dialogVisible" :title="editingId === null ? '上架商品' : '编辑商品'" width="480px">
    <el-form ref="formRef" :model="form" :rules="RULES" label-width="90px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" maxlength="128" placeholder="如：祁连山牦牛肉干（250g）" />
      </el-form-item>
      <el-form-item label="价格" prop="price">
        <el-input-number v-model="form.price" :min="0.01" :max="99999999" :precision="2" />
      </el-form-item>
      <el-form-item label="库存" prop="stock">
        <el-input-number v-model="form.stock" :min="0" :max="999999" />
      </el-form-item>
      <el-form-item label="简介">
        <el-input v-model="form.description" type="textarea" :rows="3" maxlength="500" />
      </el-form-item>
      <el-form-item label="商品主图">
        <div class="uploader">
          <el-upload
            :show-file-list="false"
            :http-request="handleImageUpload"
            accept="image/png,image/jpeg,image/webp"
            :disabled="uploading"
          >
            <img v-if="imagePreview" :src="imagePreview" class="uploader__preview" alt="主图预览" />
            <div v-else class="uploader__placeholder" v-loading="uploading">
              <span>{{ uploading ? '上传中…' : '点击上传图片' }}</span>
              <small>jpg / png / webp，≤ 10MB</small>
            </div>
          </el-upload>
          <el-button v-if="imagePreview" link type="danger" @click="clearImage">移除</el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ editingId === null ? '提交上架' : '保存修改' }}
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
.head__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.thumb {
  width: 64px;
  height: 48px;
  border-radius: 4px;
  display: block;
}
.thumb--empty {
  color: var(--el-text-color-placeholder);
}
.favorite-zero {
  color: var(--el-text-color-placeholder);
}
.uploader {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.uploader__preview {
  width: 160px;
  height: 120px;
  object-fit: cover;
  border-radius: 6px;
  display: block;
}
.uploader__placeholder {
  width: 160px;
  height: 120px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  font-size: 13px;
}
.uploader__placeholder small {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
