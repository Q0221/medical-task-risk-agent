import { get } from "./http";

export function getAgentTraces(params = {}) {
  return get("/agent/traces", params);
}
