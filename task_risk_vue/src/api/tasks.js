import { del, get, patch, post } from "./http";

export function getTasks(params = {}) {
  return get("/tasks", params);
}

export function getTaskById(taskId) {
  return get(`/tasks/${taskId}`);
}

export function getPendingReviewTasks(params = {}) {
  return get("/tasks/pending-review", params);
}

export function reviewTask(taskId, body) {
  return post(`/tasks/${taskId}/review`, body);
}

export function setTaskReminder(taskId, body) {
  return post(`/tasks/${taskId}/remind`, body);
}

export function cancelTaskReminder(taskId) {
  return del(`/tasks/${taskId}/remind`);
}

export function completeTask(taskId, body = {}) {
  return patch(`/tasks/${taskId}/complete`, body);
}

export function cancelTask(taskId, body = {}) {
  return patch(`/tasks/${taskId}/cancel`, body);
}

export function assignTask(taskId, body = {}) {
  return patch(`/tasks/${taskId}/assign`, body);
}

// ── 时间线 ──────────────────────────────────────────────────────────────────

export function getTaskTimeline(taskId) {
  return get(`/tasks/${taskId}/timeline`);
}

// ── 评论 ────────────────────────────────────────────────────────────────────

export function addTaskComment(taskId, body) {
  return post(`/tasks/${taskId}/comments`, body);
}

// ── 附件 ────────────────────────────────────────────────────────────────────

export function addTaskAttachment(taskId, body) {
  return post(`/tasks/${taskId}/attachments`, body);
}

// ── 协作者 ──────────────────────────────────────────────────────────────────

export function updateTaskCollaborators(taskId, body) {
  return patch(`/tasks/${taskId}/collaborators`, body);
}

// ── 批量操作 ─────────────────────────────────────────────────────────────────

export function batchCompleteTasks(body) {
  return post("/tasks/batch/complete", body);
}

export function batchCancelTasks(body) {
  return post("/tasks/batch/cancel", body);
}

export function batchAssignTasks(body) {
  return post("/tasks/batch/assign", body);
}
