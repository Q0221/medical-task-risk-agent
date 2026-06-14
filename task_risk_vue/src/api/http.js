import { getAuthToken, logout } from "../store/app.js";

const BASE = "/api/v1";
const AUTH_ERROR_CODES = new Set([4010, 4011, 4012]);

class ApiError extends Error {
  constructor(message, code, data) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

async function request(path, options = {}) {
  const { body, headers, ...rest } = options;
  const token = getAuthToken();
  const res = await fetch(BASE + path, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers || {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...rest,
  });

  let json;
  try {
    json = await res.json();
  } catch {
    throw new ApiError(`HTTP ${res.status}`, res.status);
  }

  if (json.code !== 0) {
    if (AUTH_ERROR_CODES.has(json.code)) {
      logout();
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        const redirect = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.assign(`/login?redirect=${redirect}`);
      }
    }
    throw new ApiError(json.message || "请求失败", json.code, json.data);
  }
  return json.data;
}

export function get(path, params) {
  const query = params
    ? "?" + new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ""))).toString()
    : "";
  return request(path + query);
}

export function post(path, body, headers) {
  return request(path, { method: "POST", body, headers });
}

export function patch(path, body) {
  return request(path, { method: "PATCH", body });
}

export function del(path) {
  return request(path, { method: "DELETE" });
}
