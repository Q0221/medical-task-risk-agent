import { get, post } from "./http";

/**
 * 自然语言对话（LangGraph 全流程）
 * @param {{ user_input: string, user_id?: number, session_id?: string }} params
 */
export function chatWithAgent({ user_input, user_id, session_id, trace_id } = {}) {
  const headers = trace_id ? { "X-Trace-Id": trace_id } : undefined;
  return post("/agent/chat", { user_input, user_id, session_id }, headers);
}

/**
 * 草稿确认（跳过 LLM，直接从已解析草稿落库）
 * @param {object} payload DraftConfirmRequest
 */
export function confirmDraft(payload) {
  return post("/agent/confirm-draft", payload);
}

/**
 * 模糊搜索候选项
 * @param {"user"|"hospital"|"product"} entity_type
 * @param {string} name 搜索关键词
 * @param {number} limit 最多返回数量
 */
export function searchCandidates({ entity_type, name, limit = 8 } = {}) {
  return get("/agent/candidates", { entity_type, name, limit });
}

/**
 * 取回指定会话的历史消息
 * @param {string} sessionId
 */
export function getSessionHistory(sessionId) {
  return get(`/agent/history/${sessionId}`);
}

/**
 * 按 trace_id 获取单次对话的思考过程
 * @param {string} traceId
 */
export function getThinkingTrace(traceId) {
  return get(`/agent/thinking/${traceId}`);
}
