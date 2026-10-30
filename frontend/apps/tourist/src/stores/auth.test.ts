/** 登录态 store 测试（令牌由 api-client 管理，这里只验证用户信息维护）。 */

import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', () => ({
  fetchMe: vi.fn(),
  hasSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  registerTourist: vi.fn(),
}));

import { fetchMe, hasSession, login, logout, registerTourist } from '@qh/api-client';
import type { UserPublic } from '@qh/api-client';

import { useAuthStore } from './auth';

const mockedFetchMe = vi.mocked(fetchMe);
const mockedHasSession = vi.mocked(hasSession);
const mockedLogin = vi.mocked(login);
const mockedLogout = vi.mocked(logout);
const mockedRegister = vi.mocked(registerTourist);

const USER: UserPublic = {
  id: 7,
  phone: '13900001111',
  role: 'tourist',
  status: 'active',
  nickname: '演示游客',
  license_no: null,
  created_at: '2026-01-01T00:00:00Z',
};

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it('无令牌时 restore 不请求用户信息', async () => {
    mockedHasSession.mockReturnValue(false);
    const auth = useAuthStore();

    await auth.restore();

    expect(mockedFetchMe).not.toHaveBeenCalled();
    expect(auth.user).toBeNull();
  });

  it('有令牌时 restore 拉取用户；失败静默置空', async () => {
    mockedHasSession.mockReturnValue(true);
    mockedFetchMe.mockResolvedValueOnce(USER);
    const auth = useAuthStore();
    await auth.restore();
    expect(auth.user?.nickname).toBe('演示游客');
    expect(auth.isLoggedIn).toBe(true);

    mockedFetchMe.mockRejectedValueOnce(new Error('401'));
    await auth.restore();
    expect(auth.user).toBeNull();
  });

  it('login 保存用户信息，displayName 优先昵称', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'a',
      token_type: 'bearer',
      refresh_token: 'r',
      refresh_expires_in: 100,
      user: USER,
    });
    const auth = useAuthStore();

    await auth.login('13900001111', 'secret123');

    expect(auth.displayName).toBe('演示游客');
  });

  it('无昵称时 displayName 回退手机号', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'a',
      token_type: 'bearer',
      refresh_token: 'r',
      refresh_expires_in: 100,
      user: { ...USER, nickname: null },
    });
    const auth = useAuthStore();
    await auth.login('13900001111', 'secret123');
    expect(auth.displayName).toBe('13900001111');
  });

  it('register 调用注册接口（注册后不自动登录）', async () => {
    mockedRegister.mockResolvedValue(USER);
    const auth = useAuthStore();

    await auth.register('13900001111', 'secret123', '昵称');

    expect(mockedRegister).toHaveBeenCalledWith('13900001111', 'secret123', '昵称');
    expect(auth.user).toBeNull();
  });

  it('logout 清空用户信息', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'a',
      token_type: 'bearer',
      refresh_token: 'r',
      refresh_expires_in: 100,
      user: USER,
    });
    mockedLogout.mockResolvedValue();
    const auth = useAuthStore();
    await auth.login('13900001111', 'secret123');

    await auth.logout();

    expect(mockedLogout).toHaveBeenCalledTimes(1);
    expect(auth.user).toBeNull();
    expect(auth.isLoggedIn).toBe(false);
  });

  it('fetchUser 失败向上抛错（供页面提示，不同于 restore 的静默）', async () => {
    mockedFetchMe.mockRejectedValue(new Error('网络错误'));
    const auth = useAuthStore();

    await expect(auth.fetchUser()).rejects.toThrow('网络错误');
  });
});
