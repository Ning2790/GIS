<script setup lang="ts">
import {
  ApiError,
  getDashboardSummary,
  getMetricsSummary,
  getSalesOverview,
  type AuditLogPublic,
  type DashboardSummary,
  type MetricsSummary,
  type SalesOverview,
} from '@qh/api-client';
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';

const summary = ref<DashboardSummary | null>(null);
// 销量看板（增强）：近 14 天日趋势 + 热销 Top 5（商户看自己 / 管理员全平台）
const overview = ref<SalesOverview | null>(null);
const overviewMax = computed(() =>
  Math.max(1, ...(overview.value?.series ?? []).map((item) => item.revenue)),
);
// 接口始终补齐 N 天（含全 0），不能用 series.length 判断“有没有成交”
const hasSales = computed(() =>
  (overview.value?.series ?? []).some((item) => item.orders > 0),
);
const loading = ref(true);
const error = ref('');
// 看板单独维护加载 / 错误态：失败不应伪装成「暂无成交数据」，也不阻塞主卡片
const overviewLoading = ref(false);
const overviewError = ref('');

async function loadOverview() {
  overviewLoading.value = true;
  overviewError.value = '';
  try {
    overview.value = await getSalesOverview(14);
  } catch (err) {
    overview.value = null;
    overviewError.value = err instanceof ApiError ? err.message : '看板加载失败';
  } finally {
    overviewLoading.value = false;
  }
}

const ACTION_LABEL: Record<string, string> = {
  'review.approve': '审核通过',
  'review.reject': '审核驳回',
  'user.disable': '禁用用户',
  'user.enable': '启用用户',
  'order.cancel': '取消订单',
  'payment.callback': '支付回调',
  'route.create': '新建路线',
  'route.update': '更新路线',
  'route.delete': '删除路线',
  'cs.transfer': '用户转人工',
  'cs.claim': '客服接入',
  'cs.release': '客服释放',
  'cs.close': '结束会话',
};

// 运行指标（N10）：平台级数据，仅管理员拉取
const metrics = ref<MetricsSummary | null>(null);
const metricsLoading = ref(false);
const metricsError = ref('');

async function loadMetrics() {
  if (summary.value?.role !== 'admin') {
    return;
  }
  metricsLoading.value = true;
  metricsError.value = '';
  try {
    metrics.value = await getMetricsSummary();
  } catch (err) {
    // 指标不可用不影响概览其他部分；但要与「真的没有数据」区分开（便于排查 401/503）
    metrics.value = null;
    metricsError.value = err instanceof ApiError ? err.message : '指标加载失败';
  } finally {
    metricsLoading.value = false;
  }
}

const inflightText = computed(() =>
  metrics.value
    ? ['view', 'trade', 'auth', 'ai'].map((key) => metrics.value?.queue_inflight[key] ?? 0).join(' / ')
    : '—',
);
const capacityText = computed(() =>
  metrics.value
    ? ['view', 'trade', 'auth', 'ai']
        .map((key) => {
          const value = metrics.value?.queue_capacity[key] ?? 0;
          return value > 0 ? value : '不限'; // 容量 <= 0 表示不限制（见 queue_gate.capacity_of）
        })
        .join(' / ')
    : '—',
);
const p95Text = computed(() =>
  metrics.value?.latency_p95_seconds != null
    ? `${Math.round(metrics.value.latency_p95_seconds * 1000)} ms`
    : '—',
);
const avgText = computed(() =>
  metrics.value?.latency_avg_seconds != null
    ? `${Math.round(metrics.value.latency_avg_seconds * 1000)} ms`
    : '—',
);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    summary.value = await getDashboardSummary();
    // 指标与看板并行加载；看板失败只影响自己的卡片
    await Promise.all([loadMetrics(), loadOverview()]);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function logText(log: AuditLogPublic): string {
  return ACTION_LABEL[log.action] ?? log.action;
}

onMounted(load);
</script>

<template>
  <div v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" show-icon style="margin-bottom: 12px" />

    <template v-if="summary">
      <p class="welcome">
        {{ summary.role === 'admin' ? '全平台概览' : '我的经营概览' }}
        <span class="welcome__hint">数据实时统计，卡片可点击进入对应页面</span>
      </p>

      <!-- 商品 / 订单（商户看自己，管理员看全平台） -->
      <el-row :gutter="12" class="row">
        <el-col :span="6">
          <RouterLink class="card-link" to="/products">
            <el-card shadow="hover" class="stat">
              <div class="stat__value">{{ summary.my_products ?? 0 }}</div>
              <div class="stat__label">
                {{ summary.role === 'admin' ? '全平台商品' : '我的商品' }}
              </div>
              <div class="stat__sub">
                在售 {{ summary.my_products_on_sale ?? 0 }} · 已下架
                {{ summary.my_products_off_shelf ?? 0 }}
              </div>
            </el-card>
          </RouterLink>
        </el-col>
        <el-col :span="6">
          <RouterLink class="card-link" to="/orders">
            <el-card shadow="hover" class="stat">
              <div class="stat__value">{{ summary.my_orders_created ?? 0 }}</div>
              <div class="stat__label">待支付订单</div>
              <div class="stat__sub">
                已支付 {{ summary.my_orders_paid ?? 0 }} · 已取消
                {{ summary.my_orders_cancelled ?? 0 }}
              </div>
            </el-card>
          </RouterLink>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat">
            <div class="stat__value">{{ summary.today_orders ?? 0 }}</div>
            <div class="stat__label">今日下单</div>
            <div class="stat__sub">今日成交 ￥{{ summary.today_revenue ?? 0 }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat" :class="{ 'stat--warn': (summary.low_stock ?? 0) > 0 }">
            <div class="stat__value">{{ summary.low_stock ?? 0 }}</div>
            <div class="stat__label">库存预警</div>
            <div class="stat__sub">在售且库存 ≤ {{ summary.low_stock_threshold ?? 10 }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 管理员：用户 / 待审核 / 客服队列 -->
      <el-row :gutter="12" class="row">
        <el-col v-if="summary.role === 'admin'" :span="6">
          <RouterLink class="card-link" to="/admin/users">
            <el-card shadow="hover" class="stat">
              <div class="stat__value">{{ summary.users_total ?? 0 }}</div>
              <div class="stat__label">平台用户</div>
              <div class="stat__sub">含游客 / 商户 / 企业</div>
            </el-card>
          </RouterLink>
        </el-col>
        <el-col v-if="summary.role === 'admin'" :span="6">
          <RouterLink class="card-link" to="/admin/reviews">
            <el-card
              shadow="hover"
              class="stat"
              :class="{ 'stat--warn': (summary.pending_reviews ?? 0) > 0 }"
            >
              <div class="stat__value">{{ summary.pending_reviews ?? 0 }}</div>
              <div class="stat__label">待审核资质</div>
              <div class="stat__sub">商户 / 企业入驻申请</div>
            </el-card>
          </RouterLink>
        </el-col>
        <el-col :span="6">
          <RouterLink class="card-link" to="/cs">
            <el-card
              shadow="hover"
              class="stat"
              :class="{ 'stat--warn': (summary.cs_queue ?? 0) > 0 }"
            >
              <div class="stat__value">{{ summary.cs_queue ?? 0 }}</div>
              <div class="stat__label">客服排队</div>
              <div class="stat__sub">等待人工接入的会话</div>
            </el-card>
          </RouterLink>
        </el-col>
        <el-col v-if="summary.role === 'admin'" :span="6">
          <RouterLink class="card-link" to="/admin/audit-logs">
            <el-card shadow="hover" class="stat">
              <div class="stat__value">{{ summary.recent_logs.length }}</div>
              <div class="stat__label">最近操作记录</div>
              <div class="stat__sub">最新 {{ summary.recent_logs.length }} 条审计日志</div>
            </el-card>
          </RouterLink>
        </el-col>
      </el-row>

      <!-- 销量趋势 + 热销 Top 5（增强）：纯 CSS 柱状图，不引图表库 -->
      <el-row :gutter="12" class="row" v-loading="overviewLoading">
        <el-col :span="14">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="logs__head">
                <span>销量趋势（近 {{ overview?.days ?? 14 }} 天）</span>
                <span class="panel__hint">
                  仅统计已支付及之后的订单
                  <el-button
                    v-if="overviewError"
                    link
                    type="primary"
                    size="small"
                    @click="loadOverview"
                  >
                    重试
                  </el-button>
                </span>
              </div>
            </template>
            <p v-if="overviewError" class="muted">看板加载失败：{{ overviewError }}</p>
            <p v-else-if="!overview || !hasSales" class="muted">
              暂无成交数据——下单并支付后这里会出现趋势
            </p>
            <div v-else class="bars">
              <div v-for="item in overview.series" :key="item.date" class="bars__col">
                <div class="bars__bar-wrap">
                  <div
                    class="bars__bar"
                    :style="{ height: `${Math.round((item.revenue / overviewMax) * 100)}%` }"
                    :title="`${item.date}：${item.revenue} 元 / ${item.orders} 单`"
                  ></div>
                </div>
                <span class="bars__label">{{ item.date.slice(5) }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card shadow="never" class="panel">
            <template #header>
              <div class="logs__head">
                <span>热销商品 Top 5</span>
                <span class="panel__hint">近 14 天</span>
              </div>
            </template>
            <p v-if="overviewError" class="muted">看板加载失败</p>
            <p v-else-if="!overview || overview.top_products.length === 0" class="muted">
              暂无销售记录
            </p>
            <ol v-else class="top-list">
              <li v-for="(item, index) in overview.top_products" :key="`${item.name}-${index}`">
                <span class="top-list__rank">{{ index + 1 }}</span>
                <span class="top-list__name">{{ item.name }}</span>
                <span class="top-list__qty">×{{ item.quantity }}</span>
                <span class="top-list__revenue">￥{{ item.revenue.toFixed(2) }}</span>
              </li>
            </ol>
          </el-card>
        </el-col>
      </el-row>

      <!-- 管理员：运行指标（N10；与 /metrics 同源，平台级数据） -->
      <el-card v-if="summary.role === 'admin'" shadow="never" class="metrics">
        <template #header>
          <div class="logs__head">
            <span>运行指标（本实例，自启动累计）</span>
            <el-button link type="primary" :loading="metricsLoading" @click="loadMetrics">
              刷新
            </el-button>
          </div>
        </template>
        <el-row v-if="metrics" :gutter="12">
          <el-col :span="6">
            <div class="stat">
              <div class="stat__value">{{ metrics.requests_total }}</div>
              <div class="stat__label">累计请求</div>
              <div class="stat__sub">
                服务端错误 {{ metrics.server_error_total }} 次 · 数据库不可达
                {{ metrics.db_unavailable_total }} 次
              </div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat">
              <div class="stat__value">{{ p95Text }}</div>
              <div class="stat__label">P95 延迟</div>
              <div class="stat__sub">平均 {{ avgText }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat">
              <div class="stat__value">{{ metrics.rate_limit_hits_total }}</div>
              <div class="stat__label">限流命中</div>
              <div class="stat__sub">排队拒绝 {{ metrics.queue_rejections_total }} 次</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat">
              <div class="stat__value">{{ inflightText }}</div>
              <div class="stat__label">在途请求（view / trade / auth / ai）</div>
              <div class="stat__sub">
                容量 {{ capacityText }} · 闸门回补 {{ metrics.stock_gate_drift_total }} 次
              </div>
            </div>
          </el-col>
        </el-row>
        <el-alert v-else-if="metricsError" type="warning" :closable="false" show-icon>
          <template #title>指标加载失败：{{ metricsError }}</template>
          <el-button link type="primary" @click="loadMetrics">重试</el-button>
        </el-alert>
        <el-empty v-else description="暂无指标数据" :image-size="60" />
      </el-card>

      <!-- 管理员：最近审计日志 -->
      <el-card v-if="summary.role === 'admin'" shadow="never" class="logs">
        <template #header>
          <div class="logs__head">
            <span>最近操作</span>
            <RouterLink to="/admin/audit-logs">查看全部 →</RouterLink>
          </div>
        </template>
        <el-empty v-if="summary.recent_logs.length === 0" description="暂无记录" :image-size="60" />
        <el-table v-else :data="summary.recent_logs" size="small">
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="actor_id" label="操作人" width="90" />
          <el-table-column label="动作" width="120">
            <template #default="{ row }">
              <el-tag size="small">{{ logText(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="目标" width="140">
            <template #default="{ row }">{{ row.target_type }} #{{ row.target_id }}</template>
          </el-table-column>
          <el-table-column label="详情" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.detail ?? '—' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.row + .row {
  margin-top: 12px;
}
.panel__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0;
}
.bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 160px;
  padding-top: 8px;
}
.bars__col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}
.bars__bar-wrap {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
}
.bars__bar {
  width: 100%;
  min-height: 2px;
  background: var(--el-color-primary);
  border-radius: 3px 3px 0 0;
  opacity: 0.85;
}
.bars__label {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.top-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.top-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  font-size: 13px;
}
.top-list li:last-child {
  border-bottom: none;
}
.top-list__rank {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}
.top-list__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.top-list__qty {
  color: var(--el-text-color-secondary);
}
.top-list__revenue {
  color: var(--el-color-primary);
  font-weight: 600;
}

.welcome {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
}
.welcome__hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 400;
}
.row {
  margin-bottom: 12px;
}
.card-link {
  text-decoration: none;
  color: inherit;
}
.stat {
  height: 112px;
}
.metrics {
  margin-top: 12px;
}
.stat :deep(.el-card__body) {
  padding: 14px 16px;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
.stat--warn {
  border-color: var(--el-color-warning);
}
.stat__value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
}
.stat__label {
  margin-top: 2px;
  color: var(--el-text-color-primary);
}
.stat__sub {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.logs__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
