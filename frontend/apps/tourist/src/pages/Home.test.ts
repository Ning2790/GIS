/** 首页：4 颗功能星与玻璃卡片交互。 */

import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import { nextTick } from 'vue';

import Home from './Home.vue';

const GLOBAL = {
  stubs: {
    RouterLink: {
      props: ['to'],
      template: '<a :href="to"><slot /></a>',
    },
  },
};

afterEach(() => {
  document.body.innerHTML = '';
  document.body.style.overflow = '';
});

describe('首页功能星', () => {
  it('渲染星河标题和 4 颗主星', () => {
    const wrapper = mount(Home, { global: GLOBAL, attachTo: document.body });

    expect(wrapper.text()).toContain('每一个入口，');
    expect(wrapper.text()).toContain('都是一颗星。');
    expect(wrapper.text()).toContain('点击星体，查看它通往的那一页。');

    const stars = wrapper.findAll('button.sky-star');
    expect(stars).toHaveLength(4);
    expect(stars.map((star) => star.text())).toEqual([
      expect.stringContaining('地图'),
      expect.stringContaining('景点概览'),
      expect.stringContaining('精选路线'),
      expect.stringContaining('特产商城'),
    ]);

    wrapper.unmount();
  });

  it('点击星体打开半透明卡片，CTA 指向对应页面', async () => {
    const wrapper = mount(Home, { global: GLOBAL, attachTo: document.body });
    await wrapper.findAll('button.sky-star')[0].trigger('click');
    await nextTick();

    const modal = document.body.querySelector('.star-modal');
    expect(modal).not.toBeNull();
    expect(modal?.textContent).toContain('地图');
    expect(modal?.textContent).toContain('进入地图');
    expect(modal?.querySelector('.star-modal__cta')?.getAttribute('href')).toBe('/map');
    expect(document.body.style.overflow).toBe('hidden');

    wrapper.unmount();
  });

  it('Esc 关闭卡片并恢复页面滚动', async () => {
    const wrapper = mount(Home, { global: GLOBAL, attachTo: document.body });
    await wrapper.findAll('button.sky-star')[2].trigger('click');
    await nextTick();
    expect(document.body.querySelector('.star-modal')).not.toBeNull();

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await nextTick();
    expect(document.body.querySelector('.star-modal')).toBeNull();
    expect(document.body.style.overflow).toBe('');

    wrapper.unmount();
  });
});
