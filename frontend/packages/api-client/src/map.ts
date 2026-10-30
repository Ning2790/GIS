/** map 模块接口：三图底图配置与点位查询（公开）。 */

import { apiGet } from './http';
import type { MapConfig, MapPointsData } from './types';

/** 底图配置（卫星 / 行政 / 地形，前端直接把 url_template 交给地图库）。 */
export function getMapConfig(): Promise<MapConfig> {
  return apiGet<MapConfig>('/api/v1/map/config');
}

/** 点位查询：不传 bbox 返回全部；传 "minLng,minLat,maxLng,maxLat" 按视野过滤。 */
export function getMapPoints(bbox?: string): Promise<MapPointsData> {
  const query = bbox ? `?bbox=${encodeURIComponent(bbox)}` : '';
  return apiGet<MapPointsData>(`/api/v1/map/points${query}`);
}
