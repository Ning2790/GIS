/** 商城列表页（游客端）组件测试：有图渲染图片、无图回退风格化封面、空态与失败提示。 */

import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', () => ({
  listHotKeywords: vi.fn(),
  listProducts: vi.fn(),
}));

import { listHotKeywords, listProducts } from '@qh/api-client';

import Products from './Products.vue';

const mockedList = vi.mocked(listProducts);
const mockedHot = vi.mocked(listHotKeywords);

function product(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    merchant_id: 9,
    name: '祁连山牦牛肉干',
    description: '风干工艺',
    price: 138,
    stock: 10,
    status: 'on_sale',
    image_url: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const GLOBAL = {
  // Products 用了 RouterLink / QhPagination 的 router-link，测试里用桩替换
  stubs: { RouterLink: { template: '<a><slot /></a>' } },
  components: {},
};

describe('商城列表页', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  mockedHot.mockResolvedValue([]);
  });

  it('有主图：渲染 <img> 且 src 指向平台文件地址', async () => {
    mockedList.mockResolvedValue({
      items: [product({ image_url: '/api/v1/files/17' })],
      total: 1,
      page: 1,
      page_size: 12,
    });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    const img = wrapper.find('img.product__img');
    expect(img.exists()).toBe(true);
    expect(img.attributes('src')).toBe('/api/v1/files/17');
    // 有图时不显示风格化封面文字
    expect(wrapper.find('.product__cover-name').exists()).toBe(false);
  });

  it('列表优先用缩略图（无缩略图字段时回退原图地址）', async () => {
    mockedList.mockResolvedValue({
      items: [
        product({
          image_url: '/api/v1/files/17',
          image_thumbnail_url: '/api/v1/files/17?variant=thumb',
        }),
        product({ id: 2, image_url: '/api/v1/files/18' }), // 老数据：没有缩略图字段
      ],
      total: 2,
      page: 1,
      page_size: 12,
    });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    const srcs = wrapper.findAll('img.product__img').map((img) => img.attributes('src'));
    expect(srcs).toEqual(['/api/v1/files/17?variant=thumb', '/api/v1/files/18']);
  });

  it('无主图：回退风格化封面（显示商品名）', async () => {
    mockedList.mockResolvedValue({
      items: [product({ image_url: null })],
      total: 1,
      page: 1,
      page_size: 12,
    });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.find('img.product__img').exists()).toBe(false);
    expect(wrapper.find('.product__cover-name').text()).toContain('祁连山牦牛肉干');
  });

  it('空列表：显示空态提示', async () => {
    mockedList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 12 });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('没有找到符合条件的商品');
  });

  it('请求失败：显示错误信息（不白屏）', async () => {
    mockedList.mockRejectedValue(new Error('后端连接失败'));
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('后端连接失败');
  });

  it('价格与库存展示正确（缺货标记）', async () => {
    mockedList.mockResolvedValue({
      items: [product({ price: 88.5, stock: 0 })],
      total: 1,
      page: 1,
      page_size: 12,
    });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.text()).toContain('￥88.5');
    expect(wrapper.text()).toContain('库存 0');
  });

  it('热门搜索：渲染热词并可点击直接搜索', async () => {
    mockedHot.mockResolvedValue([
      { keyword: '牦牛肉干', count: 5 },
      { keyword: '黑枸杞', count: 3 },
    ]);
    mockedList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 12 });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    expect(mockedHot).toHaveBeenCalledWith(8);
    const chips = wrapper.findAll('button.hot__item');
    expect(chips.map((chip) => chip.text())).toEqual(['牦牛肉干', '黑枸杞']);

    // 点热词 → 填入搜索框并按该关键词重新查询
    await chips[1].trigger('click');
    await flushPromises();
    expect(mockedList).toHaveBeenLastCalledWith({
      keyword: '黑枸杞',
      page: 1,
      page_size: 12,
    });
  });

  it('热词接口失败：不渲染热词行（不影响商品列表）', async () => {
    mockedHot.mockRejectedValue(new Error('boom'));
    mockedList.mockResolvedValue({ items: [product()], total: 1, page: 1, page_size: 12 });
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    expect(wrapper.findAll('button.hot__item')).toHaveLength(0);
    expect(wrapper.text()).toContain('祁连山牦牛肉干');
  });
});

describe('商城列表页 · 排序与价格筛选', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedList.mockResolvedValue({ items: [product()], total: 1, page: 1, page_size: 12 } as never);
  });

  it('默认不传 sort，选「价格从低到高」后带上 sort=price_asc', async () => {
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort: undefined }),
    );

    await wrapper.find('select[aria-label="排序方式"]').setValue('price_asc');
    await flushPromises();
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort: 'price_asc', page: 1 }),
    );
  });

  it('填价格区间并筛选：带上 min_price / max_price；重置后清空', async () => {
    const wrapper = mount(Products, { global: GLOBAL });
    await flushPromises();

    await wrapper.find('input[aria-label="最低价"]').setValue(50);
    await wrapper.find('input[aria-label="最高价"]').setValue(150);
    const filter = wrapper.findAll('button').find((b) => b.text().includes('筛选'));
    await filter!.trigger('click');
    await flushPromises();
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ min_price: 50, max_price: 150, page: 1 }),
    );

    const reset = wrapper.findAll('button').find((b) => b.text().includes('重置'));
    await reset!.trigger('click');
    await flushPromises();
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ min_price: undefined, max_price: undefined, sort: undefined }),
    );
  });
});
