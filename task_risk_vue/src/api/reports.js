import { getAuthToken } from "../store/app.js";
import { get } from "./http";

const BASE = "/api/v1";

export function getChartTrend(days = 14) {
  return get("/reports/charts/trend", { days });
}

export function getChartType(params = {}) {
  return get("/reports/charts/type", params);
}

export function getChartRisk(params = {}) {
  return get("/reports/charts/risk", params);
}

export function getChartAssignee(params = {}) {
  return get("/reports/charts/assignee", params);
}

export function getReportHistory(params = {}) {
  return get("/reports/history", params);
}

export function getReportDetail(reportId) {
  return get(`/reports/history/${reportId}`);
}

/**
 * 触发文件下载（Word/PDF），携带 Bearer token 鉴权。
 * @param {number} reportId
 * @param {'word'|'pdf'} format
 */
export async function downloadReport(reportId, format = "word") {
  const token = getAuthToken();
  const url = `${BASE}/reports/export/${format}/${reportId}`;

  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!res.ok) {
    let errorText = `HTTP ${res.status}`;
    try {
      const payload = await res.json();
      errorText = payload?.message || payload?.detail || errorText;
    } catch {
      try {
        errorText = (await res.text()).slice(0, 200) || errorText;
      } catch {
        // 保持默认错误文本
      }
    }
    throw new Error(`下载失败：${errorText}`);
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);

  // 从 Content-Disposition 解析文件名，降级为默认名
  const disposition = res.headers.get("Content-Disposition") || "";
  const nameMatch = disposition.match(/filename\*?=(?:UTF-8'')?([^;]+)/i);
  const rawName = nameMatch ? decodeURIComponent(nameMatch[1].replace(/['"]/g, "")) : `report_${reportId}.${format === "word" ? "docx" : "pdf"}`;

  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = rawName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(objectUrl);
}
