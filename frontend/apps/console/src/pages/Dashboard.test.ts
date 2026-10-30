/** 概览页测试：管理员运行指标卡片（数据渲染 / 商户不展示 / 加载失败可重试）。 */

import { flushPromises, mount } from '@vue/test-utils';
import ElementPlus from 'element-plus';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  getDashboardSummary: vi.fn(),
  getMetricsSummary: vi.fn(),
  getSalesOverview: vi.fn(),
}));

import { ApiError, getDashboardSummary, getMetricsSummary, getSalesOverview } from '@qh/api-client';

import Dashboard from './Dashboard.vue';

const mockedSummary = vi.mocked(getDashboardSummary);
const mockedMetrics = vi.mocked(getMetricsSummary);
const mockedOverview = vi.mocked(getSalesOverview);

function summary(role: string) {
  return {
    role,
    my_products: 3,
    my_products_on_sale: 2,
    my_products_off_shelf: 1,
    my_orders_created: 5,
    my_orders_paid: 4,
    my_orders_cancelled: 1,
    today_orders: 2,
    today_revenue: 198,
    low_stock: 0,
    low_stock_threshold: 5,
    users_total: 12,
    pending_reviews: 1,
    products_total: 8,
    cs_queue: 0,
    recent_logs: [],
  } as never;
}

const metricsPayload = {
  requests_total: 1234,
  server_error_total: 2,
  latency_p95_seconds: 0.2387,
  latency_avg_seconds: 0.1287,
  rate_limit_hits_total: 7,
  queue_rejections_total: 3,
  stock_gate_drift_total: 5,
  db_unavailable_total: 2,
  db_unretryable_failure_total: 1,
  queue_inflight: { view: 1, trade: 0, auth: 0, ai: 0 },
  queue_capacity: { view: 0, trade: 50, auth: 20, ai: 30 },
};

async function mountDashboard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const wrapper = mount(Dashboard, {
    global: { plugins: [ElementPlus, pinia], stubs: { RouterLink: true } },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  mockedOverview.mockResolvedValue({ days: 14, series: [], top_products: [] } as never);
  vi.clearAllMocks();
  mockedSummary.mockResolvedValue(summary('admin'));
  mockedMetrics.mockResolvedValue(metricsPayload);
});

describe('概览页运行指标卡片（控制台）', () => {
  it('管理员可见，渲染请求量 / P95 / 限流 / 在途与容量（容量 0 显示为不限）', async () => {
    const wrapper = await mountDashboard();

    expect(mockedMetrics).toHaveBeenCalled();
    const text = wrapper.text();
    expect(text).toContain('运行指标');
    expect(text).toContain('1234'); // 累计请求
    expect(text).toContain('239 ms'); // P95（0.2387s 四舍五入到毫秒）
    expect(text).toContain('限流命中');
    expect(text).toContain('在途请求');
    expect(text).toMatch(/不限 \/ 50 \/ 20 \/ 30/); // view 容量 0 => 不限
    expect(text).toContain('闸门回补 5 次');
    expect(text).toContain('数据库不可达');
  });

  it('商户不展示运行指标，也不发起指标请求', async () => {
    mockedSummary.mockResolvedValue(summary('merchant'));
    const wrapper = await mountDashboard();

    expect(mockedMetrics).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain('运行指标');
  });

  it('指标接口失败时显示原因与重试入口，点击重试后恢复', async () => {
    mockedMetrics.mockRejectedValueOnce(new ApiError(40300, '无权限访问该接口'));
    const wrapper = await mountDashboard();

    expect(wrapper.text()).toContain('指标加载失败');
    expect(wrapper.text()).toContain('无权限访问该接口');

    const retry = wrapper.findAll('button').find((button) => button.text().includes('重试'));
    expect(retry).toBeTruthy();
    await retry!.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('1234');
    expect(wrapper.text()).not.toContain('指标加载失败');
  });
});

describe('销量看板（增强）', () => {
  it('渲染近 14 天趋势与热销 Top 5', async () => {
    mockedSummary.mockResolvedValue(summary('merchant') as never);
    mockedOverview.mockResolvedValue({
      days: 14,
      series: [
        { date: '2026-10-15', orders: 2, revenue: 300 },
        { date: '2026-10-16', orders: 1, revenue: 150 },
      ],
      top_products: [{ name: '祁连山牦牛肉干', quantity: 3, revenue: 414 }],
    } as never);
    const wrapper = await mountDashboard();
    await flushPromises();

    expect(wrapper.text()).toContain('销量趋势（近 14 天）');
    expect(wrapper.text()).toContain('热销商品 Top 5');
    expect(wrapper.text()).toContain('祁连山牦牛肉干');
    expect(wrapper.text()).toContain('×3');
    // 两根柱子（按日）
    expect(wrapper.findAll('.bars__bar')).toHaveLength(2);
  });

  it('全零序列显示「暂无成交数据」而不是一排 0 高柱', async () => {
    mockedSummary.mockResolvedValue(summary('merchant') as never);
    mockedOverview.mockResolvedValue({
      days: 14,
      series: Array.from({ length: 14 }, (_, index) => ({
        date: `2026-10-${String(index + 4).padStart(2, '0')}`,
        orders: 0,
        revenue: 0,
      })),
      top_products: [],
    } as never);
    const wrapper = await mountDashboard();
    await flushPromises();

    expect(wrapper.text()).toContain('暂无成交数据');
    expect(wrapper.findAll('.bars__bar')).toHaveLength(0);
    expect(wrapper.text()).toContain('暂无销售记录');
  });

  it('看板接口失败：概览主卡片仍正常显示，看板显示失败原因与重试', async () => {
    mockedSummary.mockResolvedValue(summary('merchant') as never);
    mockedOverview.mockRejectedValue(new ApiError(500, 'boom'));
    const wrapper = await mountDashboard();
    await flushPromises();

    expect(wrapper.text()).toContain('我的经营概览');
    // 失败与「真的没有数据」要能区分
    expect(wrapper.text()).toContain('看板加载失败');
    expect(wrapper.text()).toContain('boom');
    expect(wrapper.text()).not.toContain('暂无成交数据');

    mockedOverview.mockResolvedValue({
      days: 14,
      series: [{ date: '2026-10-17', orders: 1, revenue: 20 }],
      top_products: [],
    } as never);
    const retry = wrapper.findAll('button').find((btn) => btn.text().includes('重试'));
    expect(retry).toBeTruthy();
    await retry!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).not.toContain('看板加载失败');
    expect(wrapper.findAll('.bars__bar')).toHaveLength(1);
  });
});
