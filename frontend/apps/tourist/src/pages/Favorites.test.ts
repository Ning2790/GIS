/** 收藏 / 浏览历史页测试：列表渲染、空态、清空历史、错误提示。 */

import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  listFavorites: vi.fn(),
  listHistory: vi.fn(),
  clearHistory: vi.fn(),
}));

import { clearHistory, listFavorites, listHistory } from '@qh/api-client';

import Favorites from './Favorites.vue';
import History from './History.vue';

const mockedFavorites = vi.mocked(listFavorites);
const mockedHistory = vi.mocked(listHistory);
const mockedClear = vi.mocked(clearHistory);

function product(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    merchant_id: 9,
    name: '柴达木黑枸杞',
    description: '花青素含量高',
    price: 168,
    stock: 20,
    status: 'on_sale',
    image_url: null,
    created_at: '2026-10-01T00:00:00Z',
    ...overrides,
  };
}

function page(items: unknown[], total?: number) {
  return { items, total: total ?? items.length, page: 1, page_size: 12 } as never;
}

const GLOBAL = { stubs: { RouterLink: { template: '<a><slot /></a>' } } };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('我的收藏页', () => {
  it('渲染收藏商品与总数（下架商品标注）', async () => {
    mockedFavorites.mockResolvedValue(
      page([product(), product({ id: 8, name: '已下架的雪菊', status: 'off_shelf' })], 2),
    );
    const wrapper = mount(Favorites, { global: GLOBAL });
    await flushPromises();

    expect(mockedFavorites).toHaveBeenCalledWith(1, 12);
    expect(wrapper.text()).toContain('柴达木黑枸杞');
    expect(wrapper.text()).toContain('￥168');
    expect(wrapper.text()).toContain('共 2 件');
    expect(wrapper.text()).toContain('已下架');
  });

  it('空收藏：显示空态与去商城入口', async () => {
    mockedFavorites.mockResolvedValue(page([], 0));
    const wrapper = mount(Favorites, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('还没有收藏');
    expect(wrapper.text()).toContain('去商城');
  });

  it('分页：超过一页时出现分页控件并能翻页', async () => {
    mockedFavorites.mockResolvedValue(page([product()], 30));
    const wrapper = mount(Favorites, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('1 / 3 页'); // 30 条 / 每页 12
    const next = wrapper.findAll('button').find((btn) => btn.text().includes('下一页'));
    await next?.trigger('click');
    await flushPromises();
    expect(mockedFavorites).toHaveBeenLastCalledWith(2, 12);
  });

  it('加载失败：显示错误与重试', async () => {
    mockedFavorites.mockRejectedValue(new Error('网络错误'));
    const wrapper = mount(Favorites, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('网络错误');
    expect(wrapper.text()).toContain('重试');
  });
});

describe('浏览历史页', () => {
  it('渲染历史商品并支持清空', async () => {
    mockedHistory.mockResolvedValue(page([product({ name: '青海雪菊' })], 1));
    mockedClear.mockResolvedValue({ deleted: 1 });
    const wrapper = mount(History, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('青海雪菊');
    const clearButton = wrapper.findAll('button').find((btn) => btn.text().includes('清空历史'));
    expect(clearButton).toBeTruthy();

    await clearButton?.trigger('click');
    await flushPromises();

    expect(mockedClear).toHaveBeenCalled();
    expect(wrapper.text()).toContain('已清空 1 条浏览记录');
    expect(wrapper.text()).toContain('还没有浏览记录');
  });

  it('历史为空：不显示清空按钮', async () => {
    mockedHistory.mockResolvedValue(page([], 0));
    const wrapper = mount(History, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('还没有浏览记录');
    expect(wrapper.text()).not.toContain('清空历史');
  });
});
