/** 基线组件（packages/ui）渲染与交互测试。 */

import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import QhButton from './QhButton.vue';
import QhCard from './QhCard.vue';
import QhEmpty from './QhEmpty.vue';
import QhInput from './QhInput.vue';
import QhPagination from './QhPagination.vue';
import QhTag from './QhTag.vue';

describe('QhButton', () => {
  it('默认主色按钮，渲染插槽内容', () => {
    const wrapper = mount(QhButton, { slots: { default: '提交' } });
    expect(wrapper.text()).toBe('提交');
    expect(wrapper.classes()).toContain('qh-btn--primary');
    expect(wrapper.classes()).toContain('qh-btn--md');
  });

  it('variant / size 映射样式类；disabled 透传到原生按钮', () => {
    const wrapper = mount(QhButton, {
      props: { variant: 'danger', size: 'sm', disabled: true },
      slots: { default: '删除' },
    });
    expect(wrapper.classes()).toContain('qh-btn--danger');
    expect(wrapper.classes()).toContain('qh-btn--sm');
    expect(wrapper.attributes('disabled')).toBeDefined();
  });

  it('点击触发原生 click 事件', async () => {
    const wrapper = mount(QhButton, { slots: { default: '点我' } });
    await wrapper.trigger('click');
    expect(wrapper.emitted('click')).toHaveLength(1);
  });
});

describe('QhPagination', () => {
  const base = { page: 2, pageSize: 10, total: 35 };

  it('展示页码信息并发出 change 事件', async () => {
    const wrapper = mount(QhPagination, { props: base });
    expect(wrapper.text()).toContain('2 / 4 页');
    expect(wrapper.text()).toContain('共 35 条');

    const buttons = wrapper.findAll('button');
    await buttons[1].trigger('click'); // 下一页
    expect(wrapper.emitted('change')?.[0]).toEqual([3]);
  });

  it('首页禁用上一页、末页禁用下一页', () => {
    const first = mount(QhPagination, { props: { ...base, page: 1 } });
    expect(first.findAll('button')[0].attributes('disabled')).toBeDefined();

    const last = mount(QhPagination, { props: { ...base, page: 4 } });
    expect(last.findAll('button')[1].attributes('disabled')).toBeDefined();
  });

  it('total 为 0 时总页数按 1 展示', () => {
    const wrapper = mount(QhPagination, { props: { page: 1, pageSize: 10, total: 0 } });
    expect(wrapper.text()).toContain('1 / 1 页');
  });
});

describe('QhInput', () => {
  it('v-model 双向绑定', async () => {
    const wrapper = mount(QhInput, { props: { modelValue: '旧值' } });
    const input = wrapper.find('input');
    expect(input.element.value).toBe('旧值');

    await input.setValue('新值');
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['新值']);
  });

  it('透传 type / placeholder / maxlength / disabled', () => {
    const wrapper = mount(QhInput, {
      props: { type: 'password', placeholder: '密码', maxlength: 8, disabled: true },
    });
    const input = wrapper.find('input');
    expect(input.attributes('type')).toBe('password');
    expect(input.attributes('placeholder')).toBe('密码');
    expect(input.attributes('maxlength')).toBe('8');
    expect(input.attributes('disabled')).toBeDefined();
  });
});

describe('QhTag / QhEmpty / QhCard', () => {
  it('QhTag：tone 映射样式类，默认 primary', () => {
    expect(mount(QhTag).classes()).toContain('qh-tag--primary');
    expect(mount(QhTag, { props: { tone: 'success' } }).classes()).toContain('qh-tag--success');
  });

  it('QhEmpty：默认文案与自定义文案', () => {
    expect(mount(QhEmpty).text()).toBe('暂无数据');
    expect(mount(QhEmpty, { props: { text: '还没有订单' } }).text()).toBe('还没有订单');
  });

  it('QhCard：有 header 插槽才渲染头部；padding 映射样式类', () => {
    const withHeader = mount(QhCard, {
      slots: { header: '商品明细', default: '内容' },
    });
    expect(withHeader.find('.qh-card__header').exists()).toBe(true);
    expect(withHeader.text()).toContain('商品明细');

    const noHeader = mount(QhCard, { slots: { default: '内容' } });
    expect(noHeader.find('.qh-card__header').exists()).toBe(false);
    expect(noHeader.classes()).toContain('qh-card--pad-md');

    expect(mount(QhCard, { props: { padding: 'none' } }).classes()).toContain('qh-card--pad-none');
  });
});
