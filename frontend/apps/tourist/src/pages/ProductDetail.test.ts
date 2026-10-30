/** 商品详情页测试：收藏切换（登录后加 / 取消）与收藏数展示。 */

import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '7' }, fullPath: '/products/7' }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  addFavorite: vi.fn(),
  getProductDetail: vi.fn(),
  hasSession: vi.fn(() => true),
  removeFavorite: vi.fn(),
}));

import { addFavorite, getProductDetail, removeFavorite } from '@qh/api-client';

import ProductDetail from './ProductDetail.vue';

const mockedDetail = vi.mocked(getProductDetail);
const mockedAdd = vi.mocked(addFavorite);
const mockedRemove = vi.mocked(removeFavorite);

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    merchant_id: 9,
    name: '柴达木黑枸杞',
    description: '花青素含量高',
    price: 168,
    stock: 20,
    status: 'on_sale',
    image_url: null,
    image_thumbnail_url: null,
    is_favorited: false,
    favorite_count: 3,
    created_at: '2026-10-01T00:00:00Z',
    ...overrides,
  } as never;
}

function mountDetail() {
  const pinia = createPinia();
  setActivePinia(pinia);
  return mount(ProductDetail, {
    global: {
      plugins: [pinia],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedDetail.mockResolvedValue(detail());
});

describe('商品详情页 · 收藏', () => {
  it('未收藏时显示「收藏」与全站收藏数', async () => {
    const wrapper = mountDetail();
    await flushPromises();

    expect(wrapper.text()).toContain('♡ 收藏')
    expect(wrapper.text()).toContain('3 人收藏');
  });

  it('点击收藏：调用接口、按服务端返回的权威计数显示', async () => {
    mockedAdd.mockResolvedValue({ product_id: 7, is_favorited: true, favorite_count: 4 });
    const wrapper = mountDetail();
    await flushPromises();

    const button = wrapper.findAll('button').find((btn) => btn.text().includes('收藏'));
    await button?.trigger('click');
    await flushPromises();

    expect(mockedAdd).toHaveBeenCalledWith(7);
    expect(wrapper.text()).toContain('♥ 已收藏');
    expect(wrapper.text()).toContain('4 人收藏');
    expect(wrapper.text()).toContain('已收藏');
  });

  it('已收藏时点击取消：收藏数按服务端返回更新', async () => {
    mockedDetail.mockResolvedValue(detail({ is_favorited: true, favorite_count: 4 }));
    mockedRemove.mockResolvedValue({ product_id: 7, is_favorited: false, favorite_count: 3 });
    const wrapper = mountDetail();
    await flushPromises();

    const button = wrapper.findAll('button').find((btn) => btn.text().includes('已收藏'));
    await button?.trigger('click');
    await flushPromises();

    expect(mockedRemove).toHaveBeenCalledWith(7);
    expect(wrapper.text()).toContain('♡ 收藏');
    expect(wrapper.text()).toContain('3 人收藏');
  });

  it('收藏失败：提示错误且状态不变', async () => {
    mockedAdd.mockRejectedValue(new Error('登录已过期'));
    const wrapper = mountDetail();
    await flushPromises();

    const button = wrapper.findAll('button').find((btn) => btn.text().includes('收藏'));
    await button?.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('登录已过期');
    expect(wrapper.text()).toContain('♡ 收藏');
  });
});
