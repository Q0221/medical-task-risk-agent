import { get, patch, post } from "./http";

// ---------------------------------------------------------------------------
// RAG 知识问答（原有）
// ---------------------------------------------------------------------------
export function queryKnowledge(body) {
  return post("/agent/knowledge", body);
}

// ---------------------------------------------------------------------------
// 知识库统计
// ---------------------------------------------------------------------------
export function getKnowledgeStats() {
  return get("/knowledge/stats");
}

// ---------------------------------------------------------------------------
// SOP 文档
// ---------------------------------------------------------------------------
export function listSops(params = {}) {
  return get("/knowledge/sop", params);
}

export function getSopDetail(sopId) {
  return get(`/knowledge/sop/${sopId}`);
}

export function getSopCategories() {
  return get("/knowledge/sop/categories");
}

export function createSop(body) {
  return post("/knowledge/sop", body);
}

export function updateSop(sopId, body) {
  return patch(`/knowledge/sop/${sopId}`, body);
}

export function newSopVersion(sopId, body) {
  return post(`/knowledge/sop/${sopId}/version`, body);
}

export function archiveSop(sopId) {
  return post(`/knowledge/sop/${sopId}/archive`, {});
}

// ---------------------------------------------------------------------------
// 知识空缺任务
// ---------------------------------------------------------------------------
export function listGaps(params = {}) {
  return get("/knowledge/gaps", params);
}

export function getGapDetail(gapId) {
  return get(`/knowledge/gaps/${gapId}`);
}

export function processGap(gapId, body) {
  return patch(`/knowledge/gaps/${gapId}/process`, body);
}

export function reviewGap(gapId, body) {
  return patch(`/knowledge/gaps/${gapId}/review`, body);
}

export function archiveGap(gapId) {
  return post(`/knowledge/gaps/${gapId}/archive`, {});
}
