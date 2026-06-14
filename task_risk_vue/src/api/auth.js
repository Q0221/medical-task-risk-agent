import { get, post } from "./http";

export function login({ username, password, role }) {
  return post("/auth/login", { username, password, role });
}

export function getMe() {
  return get("/auth/me");
}
