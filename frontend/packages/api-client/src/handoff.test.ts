import { beforeEach, describe, expect, it, vi } from 'vitest';

import { buildTokenHandoffUrl, consumeTokenHandoff, parseTokenHandoff } from './handoff';
import { clearTokens, getDeviceId, getToken, setDeviceId, setTokens } from './http';

function resetStorage(): void {
  clearTokens();
  localStorage.clear();
  sessionStorage.clear();
}

describe('parseTokenHandoff', () => {
  it('解析完整的 hash', () => {
    expect(
      parseTokenHandoff('#access_token=a&refresh_token=b&remember=1&device_id=dev-1'),
    ).toEqual({
      accessToken: 'a',
      refreshToken: 'b',
      remember: true,
      deviceId: 'dev-1',
    });
  });

  it('缺少 access_token 时返回 null', () => {
    expect(parseTokenHandoff('#refresh_token=b')).toBeNull();
    expect(parseTokenHandoff('')).toBeNull();
  });

  it('remember 缺省为 false', () => {
    expect(parseTokenHandoff('#access_token=a')?.remember).toBe(false);
  });
});

describe('buildTokenHandoffUrl', () => {
  beforeEach(resetStorage);

  it('把当前令牌、remember 与设备标识拼到目标地址', () => {
    setDeviceId('dev-1');
    setTokens('access-1', 'refresh-1', true);
    expect(buildTokenHandoffUrl('http://localhost:5173/')).toBe(
      'http://localhost:5173/#access_token=access-1&refresh_token=refresh-1&remember=1&device_id=dev-1',
    );
  });

  it('没有令牌时原样返回目标地址', () => {
    expect(buildTokenHandoffUrl('http://localhost:5174/')).toBe('http://localhost:5174/');
  });
});

describe('consumeTokenHandoff', () => {
  beforeEach(resetStorage);

  it('写入令牌并按 remember 选择存储，同时清掉 hash', () => {
    const replaceState = vi.fn();
    const consumed = consumeTokenHandoff(
      {
        hash: '#access_token=x&refresh_token=y&remember=0&device_id=dev-2',
        pathname: '/',
        search: '?a=1',
      },
      { replaceState },
    );

    expect(consumed).toBe(true);
    expect(getToken()).toBe('x');
    expect(getDeviceId()).toBe('dev-2');
    expect(sessionStorage.getItem('qh_access_token')).toBe('x');
    expect(localStorage.getItem('qh_access_token')).toBeNull();
    expect(replaceState).toHaveBeenCalledWith(null, '', '/?a=1');
  });

  it('没有交接 hash 时不动存储', () => {
    const replaceState = vi.fn();
    expect(
      consumeTokenHandoff(
        { hash: '', pathname: '/b2b', search: '' },
        { replaceState },
      ),
    ).toBe(false);
    expect(getToken()).toBeNull();
    expect(replaceState).not.toHaveBeenCalled();
  });
});
