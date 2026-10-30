import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  login: vi.fn(),
  registerTourist: vi.fn(),
  registerEnterprise: vi.fn(),
  clearTokens: vi.fn(),
  buildTokenHandoffUrl: vi.fn((url: string) => url),
}));

import { login, registerEnterprise, registerTourist } from '@qh/api-client';

import App from './App.vue';

const mockedLogin = vi.mocked(login);
const mockedRegisterTourist = vi.mocked(registerTourist);
const mockedRegisterEnterprise = vi.mocked(registerEnterprise);

async function fill(
  wrapper: VueWrapper,
  phone = '13900001111',
  password = 'test123456',
): Promise<void> {
  await wrapper.get('[data-testid="phone"]').setValue(phone);
  await wrapper.get('[data-testid="password"]').setValue(password);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedRegisterTourist.mockResolvedValue({} as never);
  mockedRegisterEnterprise.mockResolvedValue({} as never);
});

describe('统一登录门户', () => {
  it('默认游客登录态，不显示营业执照号', () => {
    const wrapper = mount(App);
    expect(wrapper.text()).toContain('天境源康');
    expect(wrapper.text()).toContain('游客登录后回到游客端');
    expect(wrapper.find('[data-testid="license-no"]').exists()).toBe(false);
  });

  it('切换企业 + 注册后显示营业执照号', async () => {
    const wrapper = mount(App);
    await wrapper.get('[data-testid="identity-enterprise"]').trigger('click');
    await wrapper.get('[data-testid="mode-register"]').trigger('click');

    expect(wrapper.find('[data-testid="license-no"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('商户 / 企业注册需营业执照号');
  });

  it('游客注册调用游客接口并切回登录态', async () => {
    const wrapper = mount(App);
    await wrapper.get('[data-testid="mode-register"]').trigger('click');
    await fill(wrapper);
    await wrapper.get('[data-testid="nickname"]').setValue('测试游客');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mockedRegisterTourist).toHaveBeenCalledWith('13900001111', 'test123456', '测试游客');
    expect(wrapper.text()).toContain('注册成功，请登录');
  });

  it('商户注册调用商户接口并带营业执照号', async () => {
    const wrapper = mount(App);
    await wrapper.get('[data-testid="identity-merchant"]').trigger('click');
    await wrapper.get('[data-testid="mode-register"]').trigger('click');
    await fill(wrapper, '13800000088', 'Demo123456');
    await wrapper.get('[data-testid="license-no"]').setValue('91630000TEST');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mockedRegisterEnterprise).toHaveBeenCalledWith({
      phone: '13800000088',
      password: 'Demo123456',
      nickname: undefined,
      license_no: '91630000TEST',
      role: 'merchant',
    });
    expect(wrapper.text()).toContain('注册成功，资质审核中');
  });

  it('商户注册缺营业执照号时拦截', async () => {
    const wrapper = mount(App);
    await wrapper.get('[data-testid="identity-merchant"]').trigger('click');
    await wrapper.get('[data-testid="mode-register"]').trigger('click');
    await fill(wrapper);
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(mockedRegisterEnterprise).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('请填写营业执照号');
  });

  it('游客身份登录商户账号时提示切换身份', async () => {
    mockedLogin.mockResolvedValue({ user: { role: 'merchant' } } as never);
    const wrapper = mount(App);
    await fill(wrapper);
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(wrapper.text()).toContain('该账号不是游客账号');
  });
});
