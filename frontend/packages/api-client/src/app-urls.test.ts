import { describe, expect, it } from 'vitest';

import { safeRedirectPath } from './app-urls';

describe('safeRedirectPath', () => {
  it('接受站内绝对路径', () => {
    expect(safeRedirectPath('/orders')).toBe('/orders');
    expect(safeRedirectPath('/orders?tab=1')).toBe('/orders?tab=1');
  });

  it('拒绝外部地址和协议跳转', () => {
    expect(safeRedirectPath('//evil.example')).toBe('');
    expect(safeRedirectPath('https://evil.example')).toBe('');
    expect(safeRedirectPath('javascript:alert(1)')).toBe('');
  });

  it('拒绝反斜杠和空值', () => {
    expect(safeRedirectPath('/a\\b')).toBe('');
    expect(safeRedirectPath(null)).toBe('');
    expect(safeRedirectPath(undefined)).toBe('');
    expect(safeRedirectPath(['/orders'])).toBe('');
  });
});
