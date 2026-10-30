<script setup lang="ts">
import { getMapPoints } from '@qh/api-client';
import { QhCard, QhEmpty, QhTag } from '@qh/ui';
import AiMascot from '../components/AiMascot.vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';

/** 青海大致中心：边界加载完成前先给一个兜底视野。 */
const QINGHAI_CENTER: [number, number] = [36.2, 99.6];
const INITIAL_ZOOM = 6;
/** 低于该缩放级别时只保留青海色块，隐藏州市标签/汇总点/县名，避免全国视野下挤成一团。 */
const OVERLAY_MIN_ZOOM = 5;
/** 地图可平移的最大范围：中国全境。 */
const CHINA_BOUNDS: L.LatLngBoundsExpression = [
  [17.5, 73],
  [54.5, 135.5],
];

/** 四色地图（参考图粉彩色调）：有共同边界的州市必不同色，仅点接触可同色。
 *  同色组：西宁=海西（黄）、玉树=海南（粉）、果洛=海东（青）、海北=黄南（绿），
 *  每组内均无共同边界。 */
const PREFECTURE_COLORS: Record<string, string> = {
  西宁市: '#F7F1CF', // 柔黄
  海西蒙古族藏族自治州: '#F7F1CF', // 柔黄
  玉树藏族自治州: '#F4E1EC', // 柔粉
  海南藏族自治州: '#F4E1EC', // 柔粉
  果洛藏族自治州: '#E5F3F4', // 柔青
  海东市: '#E5F3F4', // 柔青
  海北藏族自治州: '#E6F1DC', // 柔绿
  黄南藏族自治州: '#E6F1DC', // 柔绿
};

interface AdminInfo {
  name?: string;
  adcode?: number;
  center?: [number, number];
  centroid?: [number, number];
}

interface AdminFeature {
  type?: string;
  properties?: AdminInfo;
  geometry?: unknown;
}

interface PrefecturePoint {
  name: string;
  fullName: string;
  center: [number, number];
  /** 下辖县级区划数量：地图点位圆内显示该值。 */
  countyCount: number;
  /** 该州景点数：保留在侧栏旅游入口中。 */
  count: number;
}

interface CountyLabelEntry {
  tooltip: L.Tooltip;
  /** 行政区外接矩形面积：越大越优先保留标签，避免小辖区先占满视野。 */
  area: number;
}

interface LabelBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const router = useRouter();
const prefectures = ref<PrefecturePoint[]>([]);
const loading = ref(true);
const error = ref('');
const mapEl = ref<HTMLDivElement | null>(null);

let map: L.Map | null = null;
let markerGroup: L.LayerGroup | null = null;
let prefectureLabelGroup: L.LayerGroup | null = null;
let countyLabelGroup: L.LayerGroup | null = null;
let prefectureCenters: Omit<PrefecturePoint, 'count' | 'countyCount'>[] = [];
let countiesByPrefecture = new Map<string, string[]>();
let attractionsByPrefecture = new Map<string, string[]>();
let countyLabelEntries: CountyLabelEntry[] = [];
let layoutScheduled = false;
const markerRefs = new Map<string, L.Marker>();

type OverviewMode = 'admin' | 'terrain' | 'satellite';
const overviewOpen = ref(false);
const overviewMode = ref<OverviewMode>('admin');
const overviewRef = ref<HTMLElement | null>(null);
/** 全域总览看行政区划，文旅资源看景点。 */
const activeTab = ref<'overview' | 'culture'>('overview');

const totalAttractions = computed(() =>
  prefectures.value.reduce((sum, item) => sum + item.count, 0),
);
const sortedPrefectures = computed(() => {
  const list = [...prefectures.value];
  if (activeTab.value === 'culture') {
    return list.sort(
      (a, b) => b.count - a.count || a.fullName.localeCompare(b.fullName, 'zh-Hans-CN'),
    );
  }
  return list.sort(
    (a, b) =>
      b.countyCount - a.countyCount || a.fullName.localeCompare(b.fullName, 'zh-Hans-CN'),
  );
});

const SATELLITE_URL =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

const TERRAIN_ART_URL = '/geo/qinghai-terrain-art.jpg?v=20261022-draw4';
const TERRAIN_ART_BOUNDS = L.latLngBounds(
  [31.598981, 89.404697],
  [39.208344, 103.07097],
);
let terrainArtPromise: Promise<HTMLImageElement> | null = null;
function loadTerrainArt(): Promise<HTMLImageElement> {
  if (!terrainArtPromise) {
    terrainArtPromise = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => {
        terrainArtPromise = null;
        reject(new Error('terrain art load failed'));
      };
      img.src = TERRAIN_ART_URL;
    });
  }
  return terrainArtPromise;
}
let prefLayerRef: L.GeoJSON | null = null;
let countyLayerRef: L.GeoJSON | null = null;
let provinceLayerRef: L.GeoJSON | null = null;
let contextLayerRef: L.GeoJSON | null = null;
let satelliteLayer: L.GridLayer | null = null;
let terrainArtLayer: L.GridLayer | null = null;
let neighborLayer: L.GeoJSON | null = null;
let chinaGeoRef: Parameters<typeof L.geoJSON>[0] | null = null;
let provinceGeoRef: Parameters<typeof L.geoJSON>[0] | null = null;
const chinaPathCache = new Map<number, Path2D>();
const provincePathCache = new Map<number, Path2D>();

/** 省略自治州全称：海西蒙古族藏族自治州 → 海西州；西宁市 / 海东市保持原名。 */
function shortName(name: string): string {
  return name.replace(/蒙古族藏族自治州$/, '州').replace(/藏族自治州$/, '州');
}

/** 省略自治县全称：大通回族土族自治县 → 大通县；海西州直辖区域保留“直辖”。 */
function shortCountyName(name: string): string {
  if (name.endsWith('直辖')) {
    return name.replace('蒙古族藏族自治州', '州');
  }
  return name.replace(/(?:回族|土族|撒拉族|蒙古族|藏族)+自治县$/, '县');
}

function prefectureStyle(feature?: { properties?: unknown }): L.PathOptions {
  if (overviewMode.value === 'satellite') {
    return {
      color: '#ffffff',
      weight: 1,
      opacity: 0.85,
      fillOpacity: 0,
    };
  }
  if (overviewMode.value === 'terrain') {
    return {
      color: '#ffffff',
      weight: 1.05,
      opacity: 0.92,
      fillOpacity: 0,
    };
  }
  const { name = '' } = (feature?.properties ?? {}) as AdminInfo;
  return {
    color: '#879da7',
    weight: 0.8,
    opacity: 0.9,
    fillColor: PREFECTURE_COLORS[name] ?? '#d7dfe3',
    fillOpacity: 0.9,
  };
}

/** 市/州汇总点：圆内显示当前主题数值（县级区划数或景点数）；一个市/州只留一个点。 */
function prefectureIcon(countyCount: number): L.DivIcon {
  return L.divIcon({
    className: 'qh-map-prefecture-dot',
    html: `<span>${countyCount}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -16],
  });
}

function overlaps(a: LabelBox, b: LabelBox): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

/** 县名小字标注的防重叠布局：市/州标签与汇总点优先，剩余空间按辖区面积从大到小摆放。 */
function layoutCountyLabels() {
  if (!map) {
    return;
  }
  const size = map.getSize();
  const container = map.getContainer();
  const mapRect = container.getBoundingClientRect();
  const placed: LabelBox[] = [];

  // 市/州名称优先级最高，先占位
  container.querySelectorAll<HTMLElement>('.qh-map-label').forEach((el) => {
    if (el.style.display === 'none') {
      return;
    }
    const r = el.getBoundingClientRect();
    placed.push({
      left: r.left - mapRect.left,
      top: r.top - mapRect.top,
      right: r.right - mapRect.left,
      bottom: r.bottom - mapRect.top,
    });
  });

  // 汇总点圆心也占位，避免县名压在数字上
  markerRefs.forEach((marker) => {
    const p = map!.latLngToContainerPoint(marker.getLatLng());
    placed.push({ left: p.x - 17, top: p.y - 17, right: p.x + 17, bottom: p.y + 17 });
  });

  const measured: {
    el: HTMLElement;
    area: number;
    x: number;
    y: number;
    w: number;
    h: number;
  }[] = [];
  for (const entry of countyLabelEntries) {
    const el = entry.tooltip.getElement();
    if (!el) {
      continue;
    }
    el.style.display = '';
    const latlng = entry.tooltip.getLatLng();
    if (!latlng) {
      el.style.display = 'none';
      continue;
    }
    const p = map.latLngToContainerPoint(latlng);
    measured.push({
      el,
      area: entry.area,
      x: p.x,
      y: p.y,
      w: el.offsetWidth,
      h: el.offsetHeight,
    });
  }
  measured.sort((a, b) => b.area - a.area);

  for (const item of measured) {
    const outside =
      item.x + item.w / 2 < 0 ||
      item.x - item.w / 2 > size.x ||
      item.y + item.h / 2 < 0 ||
      item.y - item.h / 2 > size.y;
    const box: LabelBox = {
      left: item.x - item.w / 2 - 2,
      top: item.y - item.h / 2 - 2,
      right: item.x + item.w / 2 + 2,
      bottom: item.y + item.h / 2 + 2,
    };
    if (outside || placed.some((other) => overlaps(other, box))) {
      item.el.style.display = 'none';
    } else {
      placed.push(box);
    }
  }
}

function scheduleLabelLayout() {
  if (layoutScheduled) {
    return;
  }
  layoutScheduled = true;
  window.requestAnimationFrame(() => {
    layoutScheduled = false;
    layoutCountyLabels();
  });
}

/** 常显标注随缩放放大：缩略视野保持原字号，放大后县名仍清晰可读。 */
function updateLabelScale() {
  if (!map) {
    return;
  }
  const zoom = map.getZoom();
  const countyScale = Math.max(0, zoom - 5);
  const prefectureScale = Math.max(0, zoom - 6);
  const detailed = zoom >= 8;
  const root = map.getContainer();
  root.style.setProperty('--qh-pref-label-size', `${(12 + prefectureScale * 1.7).toFixed(1)}px`);
  root.style.setProperty('--qh-county-label-size', `${(9 + countyScale * 1.4).toFixed(1)}px`);
  root.style.setProperty('--qh-county-label-color', detailed ? '#4b6470' : '#607986');
  root.style.setProperty('--qh-county-label-weight', detailed ? '500' : '400');
  root.style.setProperty('--qh-county-label-opacity', detailed ? '0.92' : '0.82');
}

/** 全国视野下隐藏青海的标注与汇总点，只留色块；放大后恢复。 */
function updateOverlayVisibility() {
  if (!map) {
    return;
  }
  const visible = map.getZoom() >= OVERLAY_MIN_ZOOM;
  const toggle = (group: L.LayerGroup | null, show: boolean) => {
    if (!group) {
      return;
    }
    if (show && !map!.hasLayer(group)) {
      group.addTo(map!);
    } else if (!show && map!.hasLayer(group)) {
      group.remove();
    }
  };
  toggle(markerGroup, visible);
  toggle(prefectureLabelGroup, visible);
  toggle(countyLabelGroup, visible);
  if (visible) {
    scheduleLabelLayout();
  }
}

/** 单层底图：青海省市 / 州 + 县两级行政区划，不再叠加卫星 / 地形瓦片。 */
async function renderAdminDivisions() {
  if (!map) {
    return;
  }
  const [prefRes, provinceRes, countyRes, chinaRes, outlineRes, worldRes] = await Promise.all([
    fetch('/geo/qinghai-prefectures.json'),
    fetch('/geo/qinghai-province.json'),
    fetch('/geo/qinghai-counties.json'),
    fetch('/geo/china-provinces.json'),
    fetch('/geo/china-outline.json'),
    fetch('/geo/world-countries.json'),
  ]);
  if (
    !prefRes.ok ||
    !provinceRes.ok ||
    !countyRes.ok ||
    !chinaRes.ok ||
    !outlineRes.ok ||
    !worldRes.ok
  ) {
    throw new Error('行政区划数据加载失败');
  }
  const prefecturesGeo = (await prefRes.json()) as Parameters<typeof L.geoJSON>[0];
  const province = (await provinceRes.json()) as Parameters<typeof L.geoJSON>[0];
  provinceGeoRef = province;
  const counties = (await countyRes.json()) as Parameters<typeof L.geoJSON>[0];
  const otherProvinces = (await chinaRes.json()) as Parameters<typeof L.geoJSON>[0];
  chinaGeoRef = (await outlineRes.json()) as Parameters<typeof L.geoJSON>[0];
  const worldRaw = (await worldRes.json()) as { features?: Record<string, unknown>[] };
  // ECharts world.json 的 features 缺 type: Feature，补成标准 GeoJSON 再交给 Leaflet
  const worldCountries = {
    type: 'FeatureCollection',
    features: (worldRaw.features ?? []).map((feature) => ({ ...feature, type: 'Feature' })),
  } as Parameters<typeof L.geoJSON>[0];

  // 周边国家底衬：放在瓦片图层下方，卫星只在中国境内覆盖它
  if (!map.getPane('neighborPane')) {
    const pane = map.createPane('neighborPane');
    pane.style.zIndex = '150';
  }
  neighborLayer = L.geoJSON(worldCountries, {
    pane: 'neighborPane',
    style: {
      color: '#bcc9d0',
      weight: 0.6,
      opacity: 0.8,
      fillColor: '#e9eef1',
      fillOpacity: 0.85,
    },
    interactive: false,
    smoothFactor: 0,
  } as L.GeoJSONOptions & L.PolylineOptions);

  // smoothFactor=0：关闭 Leaflet 默认折线简化，保留 GeoJSON 的完整轮廓细节
  const geoRenderer = L.svg({ padding: 0.5 });
  const pathOptions = { smoothFactor: 0, renderer: geoRenderer } as L.GeoJSONOptions &
    L.PolylineOptions;

  // 全国其它省级行政区仅作地理上下文：极淡填充 + 细线，不加标注、不参与高亮
  contextLayerRef = L.geoJSON(otherProvinces, {
    style: {
      color: '#bcc9d0',
      weight: 0.6,
      opacity: 0.8,
      fillColor: '#e9eef1',
      fillOpacity: 0.6,
    },
    interactive: false,
    ...pathOptions,
  }).addTo(map);

  const prefLayer = L.geoJSON(prefecturesGeo, {
    style: prefectureStyle,
    ...pathOptions,
    onEachFeature(feature, layer) {
      const path = layer as L.Path;
      path.on('mouseover', () => {
        path.setStyle(
          overviewMode.value === 'satellite'
            ? { weight: 1.8, color: '#a5f3fc', fillOpacity: 0.08 }
            : overviewMode.value === 'terrain'
              ? { weight: 2, color: '#e0f7ff', fillOpacity: 0.08 }
              : { weight: 1.6, color: '#4f6f7c', fillOpacity: 1 },
        );
      });
      path.on('mouseout', () => {
        path.setStyle(prefectureStyle(feature));
      });
    },
  }).addTo(map);
  prefLayerRef = prefLayer;

  // 县界只画线不填充，鼠标事件穿透到下层市/州面，保留市/州悬停高亮
  countyLayerRef = L.geoJSON(counties, {
    style: { color: '#b6c4cb', weight: 0.45, opacity: 0.75, fill: false },
    interactive: false,
    ...pathOptions,
  }).addTo(map);

  provinceLayerRef = L.geoJSON(province, {
    style: { color: '#5f7c88', weight: 1.4, fill: false },
    interactive: false,
    ...pathOptions,
  }).addTo(map);

  const prefectureFeatures =
    (prefecturesGeo as { features?: AdminFeature[] })?.features ?? [];
  /** 县级 adcode 前四位与地级 adcode 前四位一致，如 630102 → 630100。 */
  const prefByPrefix = new Map<string, string>();
  prefectureCenters = [];
  prefectureLabelGroup = L.layerGroup().addTo(map);
  for (const feature of prefectureFeatures) {
    const info = feature.properties ?? {};
    // 汇总点放在几何中心（centroid）而非行政中心：东部三州的驻地彼此太近，
    // 省级视野下圆点会叠在一起；几何中心还能让点远离边界线。
    const anchor = info.centroid ?? info.center;
    if (!info.name || !anchor) {
      continue;
    }
    const center: [number, number] = [anchor[1], anchor[0]];
    const name = shortName(info.name);
    if (info.adcode) {
      prefByPrefix.set(String(info.adcode).slice(0, 4), name);
    }
    prefectureCenters.push({ name, fullName: info.name, center });
    L.tooltip({
      permanent: true,
      direction: 'top',
      offset: [0, -16],
      className: 'qh-map-label',
      interactive: false,
    })
      .setLatLng(center)
      .setContent(name)
      .addTo(prefectureLabelGroup);
  }

  // 县名常显但字号小、颜色淡；是否真正展示交给 layoutCountyLabels 做防重叠
  const countyFeatures = (counties as { features?: AdminFeature[] })?.features ?? [];
  countyLabelEntries = [];
  countiesByPrefecture = new Map();
  countyLabelGroup = L.layerGroup().addTo(map);
  for (const feature of countyFeatures) {
    const info = feature.properties ?? {};
    if (!info.name || !info.center) {
      continue;
    }
    const shortCounty = shortCountyName(info.name);
    const prefName = prefByPrefix.get(String(info.adcode ?? '').slice(0, 4));
    if (prefName) {
      const list = countiesByPrefecture.get(prefName) ?? [];
      list.push(shortCounty);
      countiesByPrefecture.set(prefName, list);
    }
    const bounds = L.geoJSON(feature as Parameters<typeof L.geoJSON>[0]).getBounds();
    const area =
      (bounds.getNorth() - bounds.getSouth()) * (bounds.getEast() - bounds.getWest());
    const tooltip = L.tooltip({
      permanent: true,
      direction: 'center',
      className: 'qh-map-county-label',
      interactive: false,
    })
      .setLatLng([info.center[1], info.center[0]])
      .setContent(shortCounty)
      .addTo(countyLabelGroup);
    countyLabelEntries.push({ tooltip, area });
  }

  // 以青海为主体，仅留少量邻省轮廓在边缘
  map.fitBounds(prefLayer.getBounds(), { padding: [12, 12] });
  map.setMinZoom(3);
  map.setMaxZoom(11);
  updateLabelScale();
  updateOverlayVisibility();
  scheduleLabelLayout();
  map.on('zoomend', () => {
    updateLabelScale();
    updateOverlayVisibility();
    scheduleLabelLayout();
  });
  map.on('moveend resize', scheduleLabelLayout);
  if (overviewMode.value !== 'admin') {
    applyOverviewMode();
  }
}

/** Web Mercator 投影：经纬度 → 指定 zoom 的全局像素坐标。 */
function projectToWorld(lng: number, lat: number, z: number): [number, number] {
  const size = 256 * 2 ** z;
  const sin = Math.sin((lat * Math.PI) / 180);
  return [
    ((lng + 180) / 360) * size,
    (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * size,
  ];
}

/** GeoJSON 所有外环（经纬度）。 */
function geoRings(geo: Parameters<typeof L.geoJSON>[0] | null): number[][][] {
  if (!geo) {
    return [];
  }
  const features =
    (geo as {
      features?: { geometry?: { type?: string; coordinates?: unknown } }[];
    })?.features ?? [];
  const rings: number[][][] = [];
  for (const feature of features) {
    const geom = feature.geometry;
    if (!geom) {
      continue;
    }
    const polygons =
      geom.type === 'Polygon'
        ? [geom.coordinates]
        : geom.type === 'MultiPolygon'
          ? geom.coordinates
          : [];
    for (const polygon of polygons as number[][][][]) {
      const ring = polygon[0];
      if (ring?.length) {
        rings.push(ring);
      }
    }
  }
  return rings;
}

/** 指定 zoom 下的裁剪路径（全局像素坐标），按几何对象分缓存。 */
function pathAtZoom(
  geo: Parameters<typeof L.geoJSON>[0] | null,
  cache: Map<number, Path2D>,
  z: number,
): Path2D | null {
  const cached = cache.get(z);
  if (cached) {
    return cached;
  }
  const rings = geoRings(geo);
  if (!rings.length) {
    return null;
  }
  const path = new Path2D();
  for (const ring of rings) {
    const [x0, y0] = projectToWorld(ring[0][0], ring[0][1], z);
    path.moveTo(x0, y0);
    for (let i = 1; i < ring.length; i += 1) {
      const [x, y] = projectToWorld(ring[i][0], ring[i][1], z);
      path.lineTo(x, y);
    }
    path.closePath();
  }
  cache.set(z, path);
  return path;
}

/** 瓦片级裁剪的中国卫星图层：只绘制中国国界内的像素，境外不请求、不渲染。 */
function createChinaSatelliteLayer(): L.GridLayer {
  const tileSize = 256;
  const layer = L.gridLayer({
    attribution: '卫星影像 © Esri, Maxar, Earthstar Geographics',
    maxZoom: 19,
    bounds: CHINA_BOUNDS,
    tileSize,
    updateWhenIdle: false,
  });

  const createTile = (coords: L.Coords, done: L.DoneCallback): HTMLElement => {
    const tile = document.createElement('canvas');
    tile.width = tileSize;
    tile.height = tileSize;
    const ctx = tile.getContext('2d');
    if (!ctx) {
      done(undefined, tile);
      return tile;
    }

    // 完全在中国外接矩形之外的瓦片：直接空白，不发起请求
    const n = 2 ** coords.z;
    const west = (coords.x / n) * 360 - 180;
    const east = ((coords.x + 1) / n) * 360 - 180;
    const north = (Math.atan(Math.sinh(Math.PI * (1 - (2 * coords.y) / n))) * 180) / Math.PI;
    const south =
      (Math.atan(Math.sinh(Math.PI * (1 - (2 * (coords.y + 1)) / n))) * 180) / Math.PI;
    if (east < 73 || west > 135.5 || north < 17.5 || south > 54.5) {
      done(undefined, tile);
      return tile;
    }

    const path = pathAtZoom(chinaGeoRef, chinaPathCache, coords.z);
    if (!path) {
      done(undefined, tile);
      return tile;
    }
    const originX = coords.x * tileSize;
    const originY = coords.y * tileSize;
    const img = new Image();
    img.onload = () => {
      ctx.save();
      ctx.translate(-originX, -originY);
      ctx.clip(path, 'evenodd');
      ctx.drawImage(img, originX, originY, tileSize, tileSize);
      ctx.restore();
      done(undefined, tile);
    };
    img.onerror = () => done(new Error('satellite tile load failed'));
    img.src = SATELLITE_URL.replace('{z}', String(coords.z))
      .replace('{x}', String(coords.x))
      .replace('{y}', String(coords.y));
    return tile;
  };

  (layer as unknown as { createTile: typeof createTile }).createTile = createTile;
  return layer;
}

/** 非写实 3D 艺术地形底图：16K 参考风格纹理。 */
function createQinghaiTerrainArtLayer(): L.GridLayer {
  const tileSize = 256;
  const layer = L.gridLayer({
    attribution: '地形：Esri 影像 + 晕渲，湖泊 © Natural Earth / OpenStreetMap',
    maxZoom: 19,
    bounds: TERRAIN_ART_BOUNDS.pad(0.15),
    tileSize,
    updateWhenIdle: false,
  });
  const createTile = (coords: L.Coords, done: L.DoneCallback): HTMLElement => {
    const tile = document.createElement('canvas');
    tile.width = tileSize;
    tile.height = tileSize;
    const ctx = tile.getContext('2d');
    if (!ctx) {
      done(undefined, tile);
      return tile;
    }
    const path = pathAtZoom(provinceGeoRef, provincePathCache, coords.z);
    if (!path) {
      done(undefined, tile);
      return tile;
    }
    const originX = coords.x * tileSize;
    const originY = coords.y * tileSize;
    void loadTerrainArt()
      .then((raster) => {
        const nw = L.CRS.EPSG3857.latLngToPoint(TERRAIN_ART_BOUNDS.getNorthWest(), coords.z);
        const se = L.CRS.EPSG3857.latLngToPoint(TERRAIN_ART_BOUNDS.getSouthEast(), coords.z);
        const vx0 = Math.max(nw.x, originX);
        const vy0 = Math.max(nw.y, originY);
        const vx1 = Math.min(se.x, originX + tileSize);
        const vy1 = Math.min(se.y, originY + tileSize);
        if (vx1 <= vx0 || vy1 <= vy0) {
          done(undefined, tile);
          return;
        }
        const sx = ((vx0 - nw.x) / (se.x - nw.x)) * raster.naturalWidth;
        const sy = ((vy0 - nw.y) / (se.y - nw.y)) * raster.naturalHeight;
        const sw = ((vx1 - vx0) / (se.x - nw.x)) * raster.naturalWidth;
        const sh = ((vy1 - vy0) / (se.y - nw.y)) * raster.naturalHeight;
        ctx.save();
        ctx.translate(-originX, -originY);
        ctx.clip(path, 'evenodd');
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(raster, sx, sy, sw, sh, vx0, vy0, vx1 - vx0, vy1 - vy0);
        ctx.restore();
        done(undefined, tile);
      })
      .catch((err: unknown) => done(err instanceof Error ? err : new Error(String(err))));
    return tile;
  };
  (layer as unknown as { createTile: typeof createTile }).createTile = createTile;
  return layer;
}

/** 行政区划 / 青海地形 / 中国卫星影像切换。 */
function applyOverviewMode() {
  if (!map || !prefLayerRef) {
    return;
  }
  const terrain = overviewMode.value === 'terrain';
  const satellite = overviewMode.value === 'satellite';
  map.getContainer().classList.toggle('map-canvas--satellite', satellite);
  map.getContainer().classList.toggle('map-canvas--terrain', terrain);

  if (!satellite && satelliteLayer) {
    map.removeLayer(satelliteLayer);
    satelliteLayer = null;
  }
  if (!terrain && terrainArtLayer) {
    map.removeLayer(terrainArtLayer);
    terrainArtLayer = null;
  }
  if (!satellite && neighborLayer && map.hasLayer(neighborLayer)) {
    map.removeLayer(neighborLayer);
  }

  if (satellite) {
    if (!satelliteLayer) {
      satelliteLayer = createChinaSatelliteLayer().addTo(map);
    } else if (!map.hasLayer(satelliteLayer)) {
      satelliteLayer.addTo(map);
    }
    if (neighborLayer && !map.hasLayer(neighborLayer)) {
      neighborLayer.addTo(map);
    }
    if (contextLayerRef) {
      if (!map.hasLayer(contextLayerRef)) {
        contextLayerRef.addTo(map);
      }
      contextLayerRef.bringToBack();
      contextLayerRef.setStyle({
        color: '#ffffff',
        weight: 0.45,
        opacity: 0.55,
        fillOpacity: 0,
      });
    }
    prefLayerRef.setStyle(prefectureStyle);
    countyLayerRef?.setStyle({ color: '#ffffff', weight: 0.5, opacity: 0.6, fill: false });
    // 青海省轮廓用白色粗线特别勾勒
    provinceLayerRef?.setStyle({ color: '#ffffff', weight: 2.6, opacity: 1, fill: false });
  } else if (terrain) {
    if (!terrainArtLayer) {
      terrainArtLayer = createQinghaiTerrainArtLayer().addTo(map);
      terrainArtLayer.getContainer()?.classList.add('terrain-satellite--shadow');
    } else if (!map.hasLayer(terrainArtLayer)) {
      terrainArtLayer.addTo(map);
    }
    if (!map.hasLayer(prefLayerRef)) {
      prefLayerRef.addTo(map);
    }
    prefLayerRef.setStyle(prefectureStyle);
    if (contextLayerRef) {
      if (!map.hasLayer(contextLayerRef)) {
        contextLayerRef.addTo(map);
      }
      contextLayerRef.bringToBack();
      contextLayerRef.setStyle({
        color: '#bcc9d0',
        weight: 0.6,
        opacity: 0.8,
        fillOpacity: 0,
      });
    }
    countyLayerRef?.setStyle({ color: '#ffffff', weight: 0.5, opacity: 0.65, fill: false });
    provinceLayerRef?.setStyle({ color: '#ffffff', weight: 2.4, opacity: 1, fill: false });
  } else {
    if (contextLayerRef) {
      if (!map.hasLayer(contextLayerRef)) {
        contextLayerRef.addTo(map);
      }
      contextLayerRef.bringToBack();
      contextLayerRef.setStyle({
        color: '#bcc9d0',
        weight: 0.6,
        opacity: 0.8,
        fillColor: '#e9eef1',
        fillOpacity: 0.6,
      });
    }
    prefLayerRef.setStyle(prefectureStyle);
    countyLayerRef?.setStyle({ color: '#b6c4cb', weight: 0.45, opacity: 0.75, fill: false });
    provinceLayerRef?.setStyle({ color: '#5f7c88', weight: 1.4, fill: false });
  }
  map.fitBounds(prefLayerRef.getBounds(), { padding: [12, 12] });
}

function setOverviewMode(mode: OverviewMode) {
  overviewMode.value = mode;
  overviewOpen.value = false;
  applyOverviewMode();
}

function toggleOverview() {
  if (activeTab.value !== 'overview') {
    activeTab.value = 'overview';
    overviewOpen.value = true;
    renderPrefectureMarkers();
    return;
  }
  overviewOpen.value = !overviewOpen.value;
}

function selectCulture() {
  overviewOpen.value = false;
  if (activeTab.value === 'culture') {
    return;
  }
  activeTab.value = 'culture';
  renderPrefectureMarkers();
}

function onDocumentClick(event: MouseEvent) {
  if (!overviewOpen.value) {
    return;
  }
  const el = overviewRef.value;
  if (el && !el.contains(event.target as Node)) {
    overviewOpen.value = false;
  }
}

/**
 * 汇总为每市/州一个点。全域总览显示下辖县级区划，文旅资源模式显示景点；
 * 各州景点名称一并缓存，供文旅资源弹窗使用。
 */
async function renderPrefecturePoints() {
  const data = await getMapPoints();
  const counts = new Map<string, number>();
  attractionsByPrefecture = new Map();
  for (const point of data.points) {
    counts.set(point.city, (counts.get(point.city) ?? 0) + 1);
    const list = attractionsByPrefecture.get(point.city) ?? [];
    list.push(point.name);
    attractionsByPrefecture.set(point.city, list);
  }
  prefectures.value = prefectureCenters.map((item) => ({
    ...item,
    countyCount: countiesByPrefecture.get(item.name)?.length ?? 0,
    count: counts.get(item.name) ?? 0,
  }));
  renderPrefectureMarkers();
}

/** 按当前主题重建州市点位：行政区划看县级区划，文旅资源看景点。 */
function renderPrefectureMarkers() {
  if (!markerGroup) {
    return;
  }
  const culture = activeTab.value === 'culture';
  markerGroup.clearLayers();
  markerRefs.clear();
  for (const item of sortedPrefectures.value) {
    const names = culture
      ? attractionsByPrefecture.get(item.name) ?? []
      : countiesByPrefecture.get(item.name) ?? [];
    const namesLine = names.length
      ? names.join('、')
      : culture
        ? '暂无景点数据'
        : '暂无县级数据';
    const value = culture ? item.count : item.countyCount;
    const countLabel = culture ? '个景点' : '个县级区划';
    const marker = L.marker(item.center, { icon: prefectureIcon(value) })
      .bindPopup(
        `<strong>${item.name}</strong><span class="qh-popup-count">${value} ${countLabel}</span>` +
          `<span class="qh-popup-counties">${namesLine}</span>` +
          (culture
            ? `<a class="qh-popup-link" href="/attractions?city=${encodeURIComponent(item.name)}">查看全部景点 →</a>`
            : ''),
        { maxWidth: 300 },
      )
      .addTo(markerGroup);
    marker.on('popupopen', () => {
      const link = marker
        .getPopup()
        ?.getElement()
        ?.querySelector<HTMLAnchorElement>('.qh-popup-link');
      if (!link) {
        return;
      }
      link.onclick = (event) => {
        event.preventDefault();
        router.push({ path: '/attractions', query: { city: item.name } });
      };
    });
    markerRefs.set(item.name, marker);
  }
  scheduleLabelLayout();
}

function focusPrefecture(item: PrefecturePoint) {
  map?.flyTo(item.center, 8, { duration: 0.6 });
  window.setTimeout(() => markerRefs.get(item.name)?.openPopup(), 700);
}

onMounted(() => document.addEventListener('click', onDocumentClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick));

onMounted(async () => {
  try {
    if (!mapEl.value) {
      return;
    }
    map = L.map(mapEl.value, {
      center: QINGHAI_CENTER,
      zoom: INITIAL_ZOOM,
      maxBounds: CHINA_BOUNDS,
      maxBoundsViscosity: 1,
    });
    map.attributionControl.setPrefix('');
    map.attributionControl.addAttribution('行政区划 © 阿里云 DataV.GeoAtlas');
    markerGroup = L.layerGroup().addTo(map);

    await renderAdminDivisions();
    await renderPrefecturePoints();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '地图加载失败';
  } finally {
    loading.value = false;
  }
});

onBeforeUnmount(() => {
  map?.remove();
  map = null;
  markerGroup = null;
  prefectureLabelGroup = null;
  countyLabelGroup = null;
  prefectureCenters = [];
  countyLabelEntries = [];
  prefLayerRef = null;
  countyLayerRef = null;
  provinceLayerRef = null;
  contextLayerRef = null;
  satelliteLayer = null;
  terrainArtLayer = null;
  neighborLayer = null;
  chinaGeoRef = null;
  chinaPathCache.clear();
  provincePathCache.clear();
});
</script>

<template>
  <header class="map-masthead">
    <div class="map-masthead__body">
      <p class="map-masthead__eyebrow">
        <span class="map-masthead__rule" aria-hidden="true"></span>
        QINGHAI PLATEAU · ATLAS
      </p>
      <h1 class="map-masthead__title">
        <span class="map-masthead__title-main">雪域高原</span>
        <span class="map-masthead__title-divider" aria-hidden="true"></span>
        <span class="map-masthead__title-sub">三层地图</span>
      </h1>
      <p class="map-masthead__desc">山河为卷，风物为章</p>
    </div>
    <div class="map-masthead__mascot" aria-hidden="true">
      <AiMascot variant="peek" class="map-masthead__mascot-svg" />
      <span class="map-masthead__cloud"></span>
      <span class="map-masthead__paw"></span>
    </div>
  </header>

  <nav class="map-tabs" aria-label="地图主题">
    <div class="map-tabs__row">
      <div ref="overviewRef" class="map-tabs__overview">
        <button
          type="button"
          class="map-tab"
          :class="{ 'map-tab--active': activeTab === 'overview' }"
          aria-haspopup="menu"
          :aria-expanded="overviewOpen"
          @click="toggleOverview"
        >
          <svg class="map-tab__icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M3 6.5 9 3l6 3.5L21 3v14.5L15 21l-6-3.5L3 21V6.5Z" />
            <path d="M9 3v14.5M15 6.5V21" />
          </svg>
          <span>全域总览</span>
          <svg
            class="map-tab__chevron"
            :class="{ 'map-tab__chevron--open': overviewOpen }"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
      </div>
      <button
        type="button"
        class="map-tab"
        :class="{ 'map-tab--active': activeTab === 'culture' }"
        @click="selectCulture"
      >
        <svg class="map-tab__icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 20 9 9l4 6 2.5-3.5L21 20H3Z" />
          <circle cx="17.5" cy="5.5" r="2.5" />
        </svg>
        <span>文旅资源</span>
      </button>
      <button type="button" class="map-tab">
        <svg class="map-tab__icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 4c-8 0-14 4.2-14 11a5 5 0 0 0 5 5c7 0 9-8 9-16Z" />
          <path d="M5 21c2.5-6 7-10 12-13" />
        </svg>
        <span>农副产品</span>
      </button>
      <button type="button" class="map-tab">
        <svg class="map-tab__icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20.8 5.6a5 5 0 0 0-7.1 0L12 7.3l-1.7-1.7a5 5 0 1 0-7.1 7.1L12 21l8.8-8.3a5 5 0 0 0 0-7.1Z" />
        </svg>
        <span>康养指导</span>
      </button>
    </div>
    <div v-if="overviewOpen" class="overview-menu" role="menu" aria-label="全域总览图层">
      <button
        type="button"
        role="menuitemradio"
        :aria-checked="overviewMode === 'admin'"
        class="overview-menu__item"
        :class="{ 'is-active': overviewMode === 'admin' }"
        @click="setOverviewMode('admin')"
      >
        <span class="overview-menu__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M3 6.5 9 3l6 3.5L21 3v14.5L15 21l-6-3.5L3 21V6.5Z" />
            <path d="M9 3v14.5M15 6.5V21" />
          </svg>
        </span>
        <span class="overview-menu__text">
          <strong>行政区划</strong>
          <small>四色政区与县界</small>
        </span>
        <svg class="overview-menu__check" viewBox="0 0 24 24" aria-hidden="true">
          <path d="m5 12 4 4L19 6" />
        </svg>
      </button>
      <button
        type="button"
        role="menuitemradio"
        :aria-checked="overviewMode === 'satellite'"
        class="overview-menu__item"
        :class="{ 'is-active': overviewMode === 'satellite' }"
        @click="setOverviewMode('satellite')"
      >
        <span class="overview-menu__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9" />
            <path d="M3 12h18M12 3c3 2.7 3 15.3 0 18M12 3c-3 2.7-3 15.3 0 18" />
          </svg>
        </span>
        <span class="overview-menu__text">
          <strong>卫星地图</strong>
          <small>中国范围卫星影像</small>
        </span>
        <svg class="overview-menu__check" viewBox="0 0 24 24" aria-hidden="true">
          <path d="m5 12 4 4L19 6" />
        </svg>
      </button>
      <button
        type="button"
        role="menuitemradio"
        :aria-checked="overviewMode === 'terrain'"
        class="overview-menu__item"
        :class="{ 'is-active': overviewMode === 'terrain' }"
        @click="setOverviewMode('terrain')"
      >
        <span class="overview-menu__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M3 19 8.5 9l3.5 5.5L15 10l6 9H3Z" />
            <path d="M6.5 15.5c3-2 6-2 9 0" />
          </svg>
        </span>
        <span class="overview-menu__text">
          <strong>地形图</strong>
          <small>地形晕渲与州市界</small>
        </span>
        <svg class="overview-menu__check" viewBox="0 0 24 24" aria-hidden="true">
          <path d="m5 12 4 4L19 6" />
        </svg>
      </button>
    </div>
  </nav>

  <p v-if="error" class="state state--error">{{ error }}</p>

  <div class="map-layout">
    <div class="map-panel">
      <div ref="mapEl" class="map-canvas"></div>
            <p v-if="loading" class="state">地图加载中…</p>
    </div>

    <aside class="map-side">
      <QhCard class="map-side__card">
        <template #header>
          <template v-if="activeTab === 'culture'">
            文旅资源（{{ totalAttractions }} 个景点）
          </template>
          <template v-else>市 / 州（{{ prefectures.length }}）</template>
        </template>
        <QhEmpty v-if="prefectures.length === 0" text="暂无市 / 州数据" />
        <ul v-else class="point-list">
          <li v-for="item in sortedPrefectures" :key="item.name" class="point-list__item">
            <button class="point-list__main" type="button" @click="focusPrefecture(item)">
              <strong>{{ item.name }}</strong>
              <QhTag tone="default">
                {{
                  activeTab === 'culture'
                    ? `${item.count} 个景点`
                    : `${item.countyCount} 个县级区划`
                }}
              </QhTag>
            </button>
            <RouterLink
              v-if="activeTab === 'culture'"
              class="point-list__link"
              :to="{ path: '/attractions', query: { city: item.name } }"
            >
              景点 →
            </RouterLink>
          </li>
        </ul>
      </QhCard>
    </aside>
  </div>
</template>

<style scoped>
.map-masthead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-6);
  padding-top: var(--qh-space-1);
}
.map-masthead__body {
  min-width: 0;
}
.map-masthead__eyebrow {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 12px;
  color: #0e7490;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.18em;
  line-height: 1;
}
.map-masthead__rule {
  flex: none;
  width: 30px;
  height: 1px;
  background: var(--tourist-sand, #d6b27a);
}
.map-masthead__title {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 16px;
  margin: 0;
  font-family: var(--tourist-serif, 'Songti SC', SimSun, 'STSong', serif);
  font-size: clamp(26px, 5.2vw, 40px);
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.15;
  white-space: nowrap;
}
.map-masthead__title-main,
.map-masthead__title-sub {
  color: var(--tourist-ink, #0b1220);
}
.map-masthead__title-divider {
  flex: none;
  width: 2px;
  height: 0.72em;
  border-radius: 1px;
  background: #d6b27a;
}
.map-masthead__desc {
  margin: 12px 0 0;
  color: var(--tourist-muted, #6b7280);
  font-size: var(--qh-fs-md);
  line-height: 1.7;
  letter-spacing: 0.02em;
}
.map-masthead__mascot {
  position: relative;
  flex: none;
  width: 172px;
}
.map-masthead__mascot-svg {
  position: relative;
  z-index: 1;
  width: 100%;
  animation: map-mascot-bob 3.2s ease-in-out infinite;
  transform-origin: 50% 100%;
}
.map-masthead__cloud {
  position: absolute;
  left: -6%;
  right: -6%;
  bottom: -2px;
  z-index: 2;
  height: 30px;
  border-radius: 50% 50% 0 0 / 100% 100% 0 0;
  background: linear-gradient(180deg, #ffffff, #eef6ff);
  box-shadow: 0 -8px 20px -12px rgba(147, 197, 253, 0.55);
}
.map-masthead__paw {
  position: absolute;
  left: 27%;
  bottom: 20px;
  z-index: 4;
  width: 12%;
  aspect-ratio: 1.4;
  border: 1px solid #162c49;
  border-radius: 50%;
  background: #35608f;
  box-shadow: 0 2px 4px rgba(15, 29, 51, 0.16);
  transform: rotate(-14deg);
}
.map-masthead__paw::after {
  content: '';
  position: absolute;
  top: 18%;
  left: 14%;
  width: 45%;
  height: 28%;
  border-radius: 50%;
  background: #6b93bd;
  opacity: 0.55;
}
@keyframes map-mascot-bob {
  0%,
  100% {
    transform: rotate(-3deg) translateY(0);
  }
  50% {
    transform: rotate(-3deg) translateY(-4px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .map-masthead__mascot-svg {
    animation: none;
  }
}
.map-tabs {
  display: flex;
  flex-direction: column;
  width: min(100%, 560px);
  margin-top: var(--qh-space-6);
  margin-bottom: var(--qh-space-5);
  padding: 4px;
  border: 1px solid var(--qh-border);
  border-radius: 14px;
  background: var(--qh-surface);
  box-shadow: 0 8px 20px -18px rgba(15, 23, 42, 0.45);
}
.map-tabs__row {
  display: flex;
  align-items: stretch;
  gap: 4px;
}
.map-tabs__overview {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 0;
}
.map-tabs__overview .map-tab {
  width: 100%;
}
.map-tab {
  display: inline-flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-width: 0;
  padding: 9px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--qh-muted);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}
.map-tab:not(.map-tab--active) {
  background: #f4f6f7;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.04);
}
.map-tab:hover {
  background: rgba(8, 145, 178, 0.08);
  color: var(--qh-primary);
}
.map-tab:not(.map-tab--active):hover {
  background: #eaf3f5;
}
.map-tab--active,
.map-tab--active:hover {
  background: linear-gradient(135deg, #0e7490, #0891b2);
  color: #fff;
  box-shadow: 0 4px 12px -7px rgba(8, 145, 178, 0.6);
}
.map-tab__icon {
  width: 16px;
  height: 16px;
  flex: none;
}
.map-tab__chevron {
  width: 13px;
  height: 13px;
  flex: none;
  opacity: 0.85;
  transition: transform 0.18s ease;
}
.map-tab__chevron--open {
  transform: rotate(180deg);
}
.map-tab__icon,
.map-tab__chevron,
.overview-menu__icon svg,
.overview-menu__check {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.overview-menu {
  display: flex;
  gap: 8px;
  width: 100%;
  margin-top: 4px;
  padding: 8px 4px 4px;
  border-top: 1px solid var(--qh-border);
  animation: overview-menu-in 0.18s ease;
}
.overview-menu__item {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 9px 10px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--qh-ink-2);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease;
}
@keyframes overview-menu-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.overview-menu__item:hover {
  background: rgba(8, 145, 178, 0.06);
}
.overview-menu__item:disabled {
  cursor: default;
  opacity: 0.5;
}
.overview-menu__item:disabled:hover {
  background: transparent;
}
.overview-menu__item.is-active {
  background: rgba(8, 145, 178, 0.09);
}
.overview-menu__icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: 8px;
  background: rgba(8, 145, 178, 0.08);
  color: var(--qh-primary);
}
.overview-menu__icon svg {
  width: 16px;
  height: 16px;
}
.overview-menu__text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.overview-menu__text strong {
  color: var(--qh-ink);
  font-size: 13px;
  font-weight: 600;
}
.overview-menu__text small {
  color: var(--qh-muted);
  font-size: 11px;
}
.overview-menu__check {
  width: 15px;
  height: 15px;
  flex: none;
  margin-left: auto;
  color: var(--qh-primary);
  opacity: 0;
}
.overview-menu__item.is-active .overview-menu__check {
  opacity: 1;
}
@media (max-width: 460px) {
  .map-tab {
    gap: 5px;
    padding: 8px 6px;
    font-size: 12px;
  }
  .map-tab__icon {
    width: 14px;
    height: 14px;
  }
  .map-tab__chevron {
    display: none;
  }
  .overview-menu {
    flex-direction: column;
  }
}
.map-layout {
  --map-height: 560px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: var(--qh-space-4);
}
.map-panel {
  position: relative;
  overflow: hidden;
  z-index: 0; /* 隔离 Leaflet 的高 z-index，避免滚动时盖住 sticky 顶栏 */
  align-self: start;
  border: 1px solid var(--qh-border);
  border-radius: var(--qh-radius-lg);
  background: var(--qh-surface);
  box-shadow: var(--qh-shadow-sm);
  overflow: hidden;
}
.map-canvas {
  height: var(--map-height);
  width: 100%;
  background: #eef4f7;
}
.map-canvas.map-canvas--satellite {
  background: #e8eaeb;
}
.map-canvas.map-canvas--terrain {
  background: #eef4f7;
}
.map-side {
  height: calc(var(--map-height) + 2px);
  min-height: 0;
}
.map-side__card {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.point-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 0;
}
.point-list__item {
  display: flex;
  align-items: center;
  gap: var(--qh-space-2);
  padding: var(--qh-space-3) 0;
  border-bottom: 1px solid var(--qh-border);
}
.point-list__item:last-child {
  border-bottom: none;
}
.point-list__main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--qh-space-2);
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: var(--qh-ink);
  cursor: pointer;
  text-align: left;
}
.point-list__main:hover strong {
  color: var(--qh-primary);
}
.point-list__link {
  font-size: var(--qh-fs-sm);
  white-space: nowrap;
}
.state {
  color: var(--qh-muted);
  font-size: var(--qh-fs-sm);
  padding: var(--qh-space-3) 0;
}
.state--error {
  color: var(--qh-danger);
}
@media (max-width: 720px) {
  .map-masthead {
    gap: var(--qh-space-4);
  }
  .map-masthead__mascot {
    width: 136px;
  }
  .map-masthead__cloud {
    height: 24px;
  }
  .map-masthead__paw {
    bottom: 17px;
    left: 28%;
  }
  .map-masthead__eyebrow {
    margin-bottom: 10px;
    font-size: 10px;
  }
  .map-masthead__desc {
    margin-top: 10px;
    font-size: var(--qh-fs-sm);
  }
}
@media (max-width: 460px) {
  .map-masthead {
    gap: 12px;
  }
  .map-masthead__mascot {
    width: 90px;
  }
  .map-masthead__cloud {
    height: 18px;
  }
  .map-masthead__paw {
    bottom: 13px;
    left: 24%;
  }
  .map-masthead__title {
    gap: 12px;
    letter-spacing: 0.02em;
  }
  .map-masthead__title-divider {
    height: 0.7em;
  }
}
@media (max-width: 900px) {
  .map-layout {
    grid-template-columns: 1fr;
  }
  .map-side {
    height: auto;
  }
  .map-side__card {
    height: auto;
  }
  .point-list {
    overflow: visible;
  }
}
</style>

<!-- 全局样式：divIcon / tooltip 注入的元素不在组件 scoped 作用域内；Leaflet 控件做 C 风格微调 -->
<style>
.terrain-satellite--shadow {
  filter: drop-shadow(8px 12px 10px rgba(8, 17, 31, 0.3));
}
.qh-map-prefecture-dot span {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--qh-primary);
  border: 3px solid #fff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.35);
  color: #fff;
  font-family: var(--qh-font);
  font-size: 12px;
  font-weight: 700;
}
.qh-map-prefecture-dot span:hover {
  background: var(--qh-accent);
}
.leaflet-tooltip.qh-map-label {
  padding: 2px 8px;
  border: none;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.18);
  color: #24505c;
  font-family: var(--qh-font);
  font-size: var(--qh-pref-label-size, 12px);
  font-weight: 600;
  letter-spacing: 0.06em;
}
.leaflet-tooltip.qh-map-label::before {
  display: none;
}
/* 县名：极淡底衬遮住穿过的县界线，字号与颜色仍弱于市/州 */
.leaflet-tooltip.qh-map-county-label {
  padding: 0 3px;
  border: none;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: none;
  color: var(--qh-county-label-color, #607986);
  font-family: var(--qh-font);
  font-size: var(--qh-county-label-size, 9px);
  font-weight: var(--qh-county-label-weight, 400);
  letter-spacing: 0.02em;
  opacity: var(--qh-county-label-opacity, 0.82);
}
.leaflet-tooltip.qh-map-county-label::before {
  display: none;
}
.leaflet-container {
  font-family: var(--qh-font);
}
.leaflet-overlay-pane svg {
  shape-rendering: geometricPrecision;
}
.leaflet-popup-content {
  line-height: 1.6;
  font-size: 13px;
}
.qh-popup-count {
  display: inline-block;
  margin-left: 6px;
  color: #7b909a;
  font-size: 11px;
  font-weight: 400;
}
.qh-popup-counties {
  display: block;
  max-width: 260px;
  margin-top: 4px;
  color: #4b6470;
  font-size: 12px;
  line-height: 1.7;
}
.qh-popup-link {
  display: inline-block;
  margin-top: 8px;
  color: var(--qh-primary);
  font-size: 12px;
  font-weight: 600;
}
.qh-popup-link:hover {
  text-decoration: underline;
}
.leaflet-container a.leaflet-popup-close-button {
  color: var(--qh-muted);
}
</style>
