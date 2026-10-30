/** 控制台登录态 store 测试：登录 / 恢复 / 登出与角色判定。 */

import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@qh/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@qh/api-client')>()),
  fetchMe: vi.fn(),
  hasSession: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));

import { fetchMe, hasSession, login, logout } from '@qh/api-client';

import { useAuthStore } from './auth';

const mockedLogin = vi.mocked(login);
const mockedLogout = vi.mocked(logout);
const mockedFetchMe = vi.mocked(fetchMe);
const mockedHasSession = vi.mocked(hasSession);

function user(overrides: Record<string, unknown> = {}) {
  return {
    id: 9,
    phone: '13900000000',
    role: 'merchant',
    status: 'active',
    nickname: '青海农牧合作社',
    license_no: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function tokenResponse(overrides: Record<string, unknown> = {}) {
  return {
    access_token: 'access-1',
    token_type: 'bearer',
    refresh_token: 'refresh-1',
    refresh_expires_in: 3600,
    user: user(),
    ...overrides,
  };
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe('auth store（控制台）', () => {
  it('登录成功后写入用户，并透传「记住我」选项', async () => {
    mockedLogin.mockResolvedValue(tokenResponse() as never);
    const auth = useAuthStore();

    await auth.login('13900000000', 'secret123', { remember: false });

    expect(mockedLogin).toHaveBeenCalledWith('13900000000', 'secret123', { remember: false });
    expect(auth.user?.phone).toBe('13900000000');
    expect(auth.isLoggedIn).toBe(true);
  });

  it('登录失败时不写入用户并原样抛出', async () => {
    mockedLogin.mockRejectedValue(new Error('手机号或密码错误'));
    const auth = useAuthStore();

    await expect(auth.login('13900000000', 'bad')).rejects.toThrow('手机号或密码错误');
    expect(auth.user).toBeNull();
  });

  it('restore：无会话时不请求用户信息', async () => {
    mockedHasSession.mockReturnValue(false);
    const auth = useAuthStore();

    await auth.restore();

    expect(mockedFetchMe).not.toHaveBeenCalled();
    expect(auth.user).toBeNull();
  });

  it('restore：有会话时恢复当前用户', async () => {
    mockedHasSession.mockReturnValue(true);
    mockedFetchMe.mockResolvedValue(user({ nickname: '马师傅' }) as never);
    const auth = useAuthStore();

    await auth.restore();

    expect(auth.user?.nickname).toBe('马师傅');
  });

  it('restore：请求失败时静默（不抛错，用户置空）', async () => {
    mockedHasSession.mockReturnValue(true);
    mockedFetchMe.mockRejectedValue(new Error('401'));
    const auth = useAuthStore();

    await expect(auth.restore()).resolves.toBeUndefined();
    expect(auth.user).toBeNull();
  });

  it('fetchUser 主动拉取并返回用户', async () => {
    mockedFetchMe.mockResolvedValue(user({ role: 'admin' }) as never);
    const auth = useAuthStore();

    const result = await auth.fetchUser();

    expect(result.role).toBe('admin');
    expect(auth.user?.role).toBe('admin');
  });

  it('登出调用接口并清空用户', async () => {
    mockedLogout.mockResolvedValue(undefined as never);
    const auth = useAuthStore();
    auth.user = user() as never;

    await auth.logout();

    expect(mockedLogout).toHaveBeenCalled();
    expect(auth.user).toBeNull();
  });

  it('角色判定与展示名（昵称优先，否则手机号）', () => {
    const auth = useAuthStore();

    auth.user = user({ role: 'admin', nickname: null }) as never;
    expect(auth.isAdmin).toBe(true);
    expect(auth.isMerchant).toBe(false);
    expect(auth.displayName).toBe('13900000000');

    auth.user = user({ role: 'enterprise', nickname: '某某合作社' }) as never;
    expect(auth.isMerchant).toBe(true);
    expect(auth.isAdmin).toBe(false);
    expect(auth.displayName).toBe('某某合作社');
  });
});
