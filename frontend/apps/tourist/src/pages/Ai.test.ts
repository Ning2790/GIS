/** AI 会话管理测试：列表渲染、重命名（行内输入）、删除（二次确认）。 */

import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  askStream: vi.fn(),
  deleteConversation: vi.fn(),
  getConversationDetail: vi.fn(),
  listConversations: vi.fn(),
  renameConversation: vi.fn(),
}));

import {
  askStream,
  deleteConversation,
  getConversationDetail,
  listConversations,
  renameConversation,
} from '@qh/api-client';

import Ai from './Ai.vue';

const mockedList = vi.mocked(listConversations);
const mockedDetail = vi.mocked(getConversationDetail);
const mockedRename = vi.mocked(renameConversation);
const mockedDelete = vi.mocked(deleteConversation);
const mockedAsk = vi.mocked(askStream);

function conversation(id: number, title: string) {
  return { id, title, created_at: '2026-10-01T00:00:00Z' };
}

function mountAi() {
  return mount(Ai, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedList.mockResolvedValue({
    items: [conversation(2, '青海湖行程咨询'), conversation(1, '高原反应预防')],
    total: 2,
    page: 1,
    page_size: 20,
  } as never);
  mockedDetail.mockResolvedValue({ id: 2, title: 'x', messages: [] } as never);
});

describe('AI 助手 · 会话管理', () => {
  it('渲染会话列表并可打开会话', async () => {
    const wrapper = mountAi();
    await flushPromises();

    const titles = wrapper.findAll('button.sessions__title').map((btn) => btn.text());
    expect(titles).toEqual(['青海湖行程咨询', '高原反应预防']);

    await wrapper.findAll('button.sessions__title')[1].trigger('click');
    await flushPromises();
    expect(mockedDetail).toHaveBeenCalledWith(1);
  });

  it('重命名：行内输入保存后调用接口并就地更新标题', async () => {
    mockedRename.mockResolvedValue(conversation(2, '环湖三日行') as never);
    const wrapper = mountAi();
    await flushPromises();

    const renameButton = wrapper
      .findAll('button')
      .find((btn) => btn.text() === '重命名');
    await renameButton?.trigger('click');

    const input = wrapper.find('input.sessions__rename');
    expect(input.exists()).toBe(true);
    await input.setValue('  环湖三日行  ');

    const saveButton = wrapper.findAll('button').find((btn) => btn.text() === '保存');
    await saveButton?.trigger('click');
    await flushPromises();

    expect(mockedRename).toHaveBeenCalledWith(2, '环湖三日行'); // 首尾空白已在提交前去除
    expect(wrapper.findAll('button.sessions__title')[0].text()).toBe('环湖三日行');
    expect(wrapper.find('input.sessions__rename').exists()).toBe(false); // 退出编辑态
  });

  it('重命名：空标题不提交并提示', async () => {
    const wrapper = mountAi();
    await flushPromises();

    await wrapper.findAll('button').find((btn) => btn.text() === '重命名')?.trigger('click');
    await wrapper.find('input.sessions__rename').setValue('   ');
    await wrapper.findAll('button').find((btn) => btn.text() === '保存')?.trigger('click');
    await flushPromises();

    expect(mockedRename).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('标题不能为空');
  });

  it('删除：确认后调用接口并从列表移除', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockedDelete.mockResolvedValue({ deleted_messages: 4 });
    const wrapper = mountAi();
    await flushPromises();

    await wrapper.findAll('button').find((btn) => btn.text() === '删除')?.trigger('click');
    await flushPromises();

    expect(confirmSpy).toHaveBeenCalled();
    expect(mockedDelete).toHaveBeenCalledWith(2);
    expect(wrapper.findAll('button.sessions__title').map((btn) => btn.text())).toEqual([
      '高原反应预防',
    ]);
    expect(wrapper.text()).toContain('已删除会话');
    confirmSpy.mockRestore();
  });

  it('删除：用户取消则不发请求', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const wrapper = mountAi();
    await flushPromises();

    await wrapper.findAll('button').find((btn) => btn.text() === '删除')?.trigger('click');
    await flushPromises();

    expect(mockedDelete).not.toHaveBeenCalled();
    expect(wrapper.findAll('button.sessions__title')).toHaveLength(2);
    confirmSpy.mockRestore();
  });

  it('回答生成中：删除与重命名被拦下（后端会 404，且问题白问）', async () => {
    // 让提问一直挂着，模拟"模型正在思考"
    mockedAsk.mockImplementation(() => new Promise<void>(() => undefined));
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const wrapper = mountAi();
    await flushPromises();

    const input = wrapper.find('input');
    await input.setValue('青海湖怎么玩？');
    await wrapper.findAll('button').find((btn) => btn.text().includes('发送'))?.trigger('click');
    await flushPromises();

    await wrapper.findAll('button').find((btn) => btn.text() === '删除')?.trigger('click');
    await flushPromises();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(mockedDelete).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('正在生成回答，请稍候再删除');

    await wrapper.findAll('button').find((btn) => btn.text() === '重命名')?.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('正在生成回答，请稍候再改名');
    expect(wrapper.find('input.sessions__rename').exists()).toBe(false);
    confirmSpy.mockRestore();
  });
});
