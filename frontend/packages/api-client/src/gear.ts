/** gear 模块接口：行前装备建议（公开）。 */

import { apiGet } from './http';
import type { GearAdvice } from './types';

/** 按城市 / 日期取装备建议（快照 + 装备清单 + 注意事项）。 */
export function getGearAdvice(city: string, day?: string): Promise<GearAdvice> {
  const query = new URLSearchParams({ city });
  if (day) {
    query.set('date', day);
  }
  return apiGet<GearAdvice>(`/api/v1/gear/advice?${query.toString()}`);
}
