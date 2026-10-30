/** 认证相关接口（注册 / 登录 / 退出 / 当前用户 / 已登录设备）。 */

import {
  apiGet,
  apiPost,
  apiPut,
  clearTokens,
  getDeviceId,
  getDeviceLabel,
  getRefreshToken,
  isRemembered,
  setTokens,
} from './http';
import type { DevicePublic, TokenResponse, UserPublic } from './types';

/** 游客注册（注册成功即可登录）。 */
export function registerTourist(
  phone: string,
  password: string,
  nickname?: string,
): Promise<UserPublic> {
  return apiPost<UserPublic>('/api/v1/auth/register/tourist', { phone, password, nickname });
}

/** 商户 / 企业注册（需资质，注册后待审核）。 */
export function registerEnterprise(payload: {
  phone: string;
  password: string;
  license_no: string;
  license_file?: string;
  nickname?: string;
  role?: 'enterprise' | 'merchant';
}): Promise<UserPublic> {
  return apiPost<UserPublic>('/api/v1/auth/register/enterprise', payload);
}

/** 更新个人资料（当前仅昵称）。 */
export function updateProfile(nickname: string): Promise<UserPublic> {
  return apiPut<UserPublic>('/api/v1/users/me', { nickname });
}

/** 修改密码：撤销其他设备登录，用返回的新令牌对续期当前端。 */
export async function changePassword(
  oldPassword: string,
  newPassword: string,
): Promise<void> {
  const data = await apiPost<{
    access_token: string;
    refresh_token: string;
    refresh_expires_in: number;
  }>('/api/v1/auth/password', {
    old_password: oldPassword,
    new_password: newPassword,
    remember: isRemembered(),
  });
  setTokens(data.access_token, data.refresh_token);
}

/** 登录并保存令牌对（access + refresh）。
 *
 * 默认「记住我」：令牌存 localStorage（30 天免密续期）；remember=false 时存 sessionStorage
 * （关浏览器即失效，适合公共电脑）。同时上报设备标识（需求量 4.2 的设备绑定）。
 */
export async function login(
  phone: string,
  password: string,
  options: { remember?: boolean } = {},
): Promise<TokenResponse> {
  const remember = options.remember ?? true;
  const data = await apiPost<TokenResponse>('/api/v1/auth/login', {
    phone,
    password,
    device_id: getDeviceId(),
    device_label: getDeviceLabel(),
    remember,
  });
  setTokens(data.access_token, data.refresh_token, remember);
  return data;
}

/** 已登录设备列表（含当前设备标记；需求量 4.2）。 */
export function listDevices(): Promise<DevicePublic[]> {
  return apiGet<DevicePublic[]>('/api/v1/auth/devices');
}

/** 移除一台已登录设备：撤销其名下全部会话（该设备需重新登录）。 */
export function revokeDevice(bindingId: number): Promise<DevicePublic> {
  return apiPost<DevicePublic>(`/api/v1/auth/devices/${bindingId}/revoke`);
}

/** 退出登录：撤销刷新令牌（幂等）并清空本地令牌。 */
export async function logout(): Promise<void> {
  const refreshToken = getRefreshToken();
  try {
    if (refreshToken) {
      await apiPost<null>('/api/v1/auth/logout', { refresh_token: refreshToken });
    }
  } finally {
    clearTokens();
  }
}

/** 获取当前登录用户。 */
export function fetchMe(): Promise<UserPublic> {
  return apiGet<UserPublic>('/api/v1/users/me');
}
