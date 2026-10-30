/** 收货地址簿（需求 2.3 交付环节；个人中心维护，下单选它时快照进订单）。 */

import { apiDelete, apiGet, apiPost, apiPut } from './http';
import type { AddressPayload, AddressPublic } from './types';

/** 我的收货地址（默认在前）。 */
export function listAddresses(): Promise<AddressPublic[]> {
  return apiGet<AddressPublic[]>('/api/v1/users/addresses');
}

/** 新增收货地址（首个自动为默认）。 */
export function createAddress(payload: AddressPayload): Promise<AddressPublic> {
  return apiPost<AddressPublic>('/api/v1/users/addresses', payload);
}

/** 更新收货地址（全量字段）。 */
export function updateAddress(id: number, payload: AddressPayload): Promise<AddressPublic> {
  return apiPut<AddressPublic>(`/api/v1/users/addresses/${id}`, payload);
}

/** 设为默认地址。 */
export function setDefaultAddress(id: number): Promise<AddressPublic> {
  return apiPost<AddressPublic>(`/api/v1/users/addresses/${id}/default`);
}

/** 删除收货地址（删默认时系统自动补一个新的默认）。 */
export function deleteAddress(id: number): Promise<null> {
  return apiDelete<null>(`/api/v1/users/addresses/${id}`);
}
