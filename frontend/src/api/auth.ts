import { request } from "@/api/client";

export type UserRole = "doctor" | "admin";

export type User = {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
};

export function login(input: {
  username: string;
  password: string;
}): Promise<{ user: User; expires_at: string }> {
  return request("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getCurrentUser(): Promise<User> {
  return request("/api/v1/auth/me");
}

export function logout(): Promise<void> {
  return request("/api/v1/auth/logout", { method: "POST" });
}
