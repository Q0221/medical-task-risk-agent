import { del, get, patch, post } from "./http";

// ── 统计 ─────────────────────────────────────────────────────────────────────
export function getRiskStats() {
  return get("/risk/stats");
}

// ── 风险记录 ──────────────────────────────────────────────────────────────────
export function getRiskRecords(params = {}) {
  return get("/risk/records", params);
}

export function getRiskRecordById(recordId) {
  return get(`/risk/records/${recordId}`);
}

export function getTaskRiskRecords(taskId) {
  return get(`/risk/records/task/${taskId}`);
}

// ── 风险工单 ──────────────────────────────────────────────────────────────────
export function getRiskTickets(params = {}) {
  return get("/risk/tickets", params);
}

// ── 风险规则 ──────────────────────────────────────────────────────────────────
export function getRiskRules(params = {}) {
  return get("/risk/rules", params);
}

export function createRiskRule(body) {
  return post("/risk/rules", body);
}

export function updateRiskRule(ruleId, body) {
  return patch(`/risk/rules/${ruleId}`, body);
}

export function deleteRiskRule(ruleId) {
  return del(`/risk/rules/${ruleId}`);
}
