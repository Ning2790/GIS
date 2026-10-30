/** dashboard 模块接口：控制台首页概览（按角色返回不同字段）。 */

import { apiGet } from './http';
import type { DashboardSummary, MetricsSummary } from './types';

/** 控制台首页概览（商户 / 企业 / 管理员）。 */
export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiGet<DashboardSummary>('/api/v1/dashboard/summary');
}


/** 运行指标汇总（仅管理员；与 /metrics 同源，供概览页监控卡片）。 */
export function getMetricsSummary(): Promise<MetricsSummary> {
  return apiGet<MetricsSummary>('/api/v1/dashboard/metrics');
}
