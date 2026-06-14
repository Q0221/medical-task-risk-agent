import { get } from "./http";

export function getSummary(params = {}) {
  return get("/agent/summary", params);
}
