import { get, patch, post } from "./http";

export function getNotifications(params = {}) {
  return get("/notifications", params);
}

export function getUnreadCount() {
  return get("/notifications/unread-count");
}

/** 标记单条通知已读 */
export function markNotificationRead(notifId) {
  return patch(`/notifications/${notifId}/read`);
}

/** 批量已读：ids 为空时标记当前用户所有未读 */
export function markBatchRead(ids = null) {
  return post("/notifications/batch-read", { ids });
}

export function retryNotification(notifId) {
  return post(`/notifications/${notifId}/retry`, {});
}
