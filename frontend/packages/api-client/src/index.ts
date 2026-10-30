/**
 * 后端 API 请求封装（@qh/api-client）。
 *
 * 统一处理后端 {code, msg, data} 响应信封：code !== 0 时抛出 ApiError，
 * 携带可直接展示的 message；401 时自动用 refresh_token 刷新并重放（见 http.ts）。
 *
 * 类型来源：
 * - 请求体：由 docs/api/openapi.json 生成（schema.d.ts）；
 * - 响应体：手写维护（types.ts，字段以后端 schemas.py 为准）。
 */

export { ApiError, apiDelete, apiGet, apiPost, apiPut, request, setBaseUrl } from './http';
export {
  clearToken,
  clearTokens,
  getRefreshToken,
  getToken,
  hasSession,
  setToken,
  setTokens,
} from './http';
export {
  buildTokenHandoffUrl,
  consumeTokenHandoff,
  parseTokenHandoff,
  type TokenHandoff,
} from './handoff';
export {
  consoleUrl,
  isLocalAppPort,
  portalUrl,
  safeRedirectPath,
  touristUrl,
} from './app-urls';
export {
  acceptAfterSale,
  applyAfterSale,
  getAfterSale,
  listAfterSales,
  postAfterSaleMessage,
  rejectAfterSale,
  resolveAfterSale,
  withdrawAfterSale,
} from './afterSales';
export {
  createAddress,
  deleteAddress,
  listAddresses,
  setDefaultAddress,
  updateAddress,
} from './addresses';
export {
  changePassword,
  fetchMe,
  listDevices,
  login,
  logout,
  registerEnterprise,
  registerTourist,
  revokeDevice,
  updateProfile,
} from './auth';
export {
  applyRoute,
  createRoute,
  deleteItinerary,
  deleteRoute,
  generateItinerary,
  getAttractionDetail,
  getItineraryDetail,
  getRouteDetail,
  listAttractions,
  listMyItineraries,
  listRoutes,
  replaceItineraryStops,
  updateRoute,
  type AttractionListParams,
  type RouteSavePayload,
} from './travel';
export { getDashboardSummary, getMetricsSummary } from './dashboard';
export { fileUrl, uploadFile } from './files';
export { getMapConfig, getMapPoints } from './map';
export { getGearAdvice } from './gear';
export { listDemands, listSupplies, type B2bListParams, type B2bCreatePayload, createSupply, createDemand, closeSupply, closeDemand, matchDemand, listDemandMatches } from './b2b';
export {
  askStream,
  deleteConversation,
  getConversationDetail,
  listConversations,
  renameConversation,
  type AskStreamHandlers,
} from './ai';
export type { KnowledgeSource } from './types';
export {
  closeCsSession,
  claimCsSession,
  createCsSession,
  listCsMessages,
  listCsQueue,
  listMyCsSessions,
  releaseCsSession,
  sendCsMessage,
  transferCsSession,
} from './cs';
export {
  approveReview,
  disableUser,
  enableUser,
  listAuditLogs,
  listPendingReviews,
  listUsers,
  rejectReview,
} from './admin';
export {
  addCartItem,
  addFavorite,
  cancelOrder,
  checkoutCart,
  clearHistory,
  createOrder,
  createPayment,
  createProduct,
  exportOrdersCsv,
  getCart,
  getOrderDetail,
  getProductDetail,
  listFavorites,
  listHistory,
  listHotKeywords,
  getSalesOverview,
  listMerchantOrders,
  listMyOrders,
  listMyProducts,
  listProducts,
  listRecommendations,
  newIdemKey,
  paymentCallback,
  refundPayment,
  removeCartItem,
  removeFavorite,
  setProductStatus,
  updateCartItem,
  updateProduct,
  type ExportedOrdersCsv,
  type FavoriteResult,
  type HotKeyword,
  type ProductListParams,
  deliverOrder,
  receiveOrder,
  shipOrder,
} from './shop';
export {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from './notifications';
export type {
  AddressPayload,
  AddressPublic,
  AfterSaleDetail,
  AfterSaleMessagePublic,
  AfterSalePublic,
  AiConversationDetail,
  AiConversationPublic,
  AiMessagePublic,
  ApiEnvelope,
  AttractionDetail,
  AttractionPublic,
  AuditLogPublic,
  B2bMatchItem,
  B2bMatchResult,
  B2bPostPublic,
  Cart,
  CartItemPublic,
  CsMessagePublic,
  CsSendResult,
  CsSessionPublic,
  DashboardSummary,
  DevicePublic,
  FilePublic,
  GearAdvice,
  ItineraryDetail,
  ItineraryPublic,
  ItineraryStopPublic,
  MapConfig,
  MapLayerPublic,
  MapPointPublic,
  MapPointsData,
  MetricsSummary,
  NotificationPublic,
  OrderDetail,
  OrderItemPublic,
  OrderPublic,
  PageData,
  PaymentPublic,
  ProductDetail,
  ProductPublic,
  RecommendationPage,
  RouteDetail,
  RoutePublic,
  SalesOverview,
  ReceiverPayload,
  RouteStopPublic,
  TicketPublic,
  TokenResponse,
  UserAdminPublic,
  UserPublic,
  UserRole,
  UserStatus,
  WeatherSnapshotPublic,
} from './types';
export type { components, paths } from './schema';
