import { get } from "./http";

export function getHealth() {
  return get("/healthz");
}

export function getReady() {
  return get("/readyz");
}
