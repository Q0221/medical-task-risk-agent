import { del, get, patch, post } from "./http";

// ── 通知渠道配置 ──────────────────────────────────────────────────────────────
export function getNotifyChannels() {
  return get("/admin/notify-channels");
}

export function updateNotifyChannel(configKey, body) {
  return patch(`/admin/notify-channels/${configKey}`, body);
}

export function testNotifyChannel(configKey, body) {
  return post(`/admin/notify-channels/${configKey}/test`, body);
}

// ── 业务字典 ──────────────────────────────────────────────────────────────────
export function getDictItems(params = {}) {
  return get("/admin/dict-items", params);
}

export function createDictItem(body) {
  return post("/admin/dict-items", body);
}

export function updateDictItem(itemId, body) {
  return patch(`/admin/dict-items/${itemId}`, body);
}

export function deleteDictItem(itemId) {
  return del(`/admin/dict-items/${itemId}`);
}

// ── 人员权限 ──────────────────────────────────────────────────────────────────
export function getAdminUsers(params = {}) {
  return get("/admin/users", params);
}

export function updateAdminUser(userId, body) {
  return patch(`/admin/users/${userId}`, body);
}
