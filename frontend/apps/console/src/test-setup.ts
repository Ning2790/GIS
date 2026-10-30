/** 控制台测试公共设置：桩掉 Element Plus 的命令式 API。
 *
 * 组件本身仍用真实 Element Plus 渲染（表格 / 弹窗 / 表单），只把
 * `ElMessage` / `ElMessageBox` 换成可断言的 vi.fn，避免真实弹层与副作用。
 */

import { vi } from 'vitest';

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>();
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    },
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue('confirm'),
      prompt: vi.fn().mockResolvedValue({ value: '' }),
      alert: vi.fn().mockResolvedValue('confirm'),
    },
  };
});
