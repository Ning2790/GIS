/** files 模块接口：受控上传与读取（公开图片任何人可读，私有文件仅本人 / 管理员）。 */

import { getBaseUrl, requestForm } from './http';
import type { FilePublic } from './types';

/** 上传文件（登录用户）。public=true 仅对图片有效，表示公开可读（商品图等）。 */
export function uploadFile(file: File, opts: { public?: boolean } = {}): Promise<FilePublic> {
  const form = new FormData();
  form.append('file', file);
  if (opts.public) {
    form.append('public', 'true');
  }
  return requestForm<FilePublic>('POST', '/api/v1/files', form);
}

/** 由平台文件 id 拼读取地址（相对路径即可走 Vite / Nginx 同源代理）。 */
export function fileUrl(fileId: number): string {
  return `${getBaseUrl()}/api/v1/files/${fileId}`;
}
