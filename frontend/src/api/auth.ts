import { request } from "@/api/client";

export type UserRole = "doctor" | "admin";
export type Permission =
  | "case:read"
  | "case:write"
  | "case:review"
  | "knowledge:read"
  | "knowledge:write"
  | "system:read"
  | "system:manage"
  | "integration:read"
  | "integration:manage"
  | "user:read"
  | "user:manage"
  | "audit:read";

export type User = {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  is_root: boolean;
  permissions: Permission[];
};

export type Session = {
  id: string;
  current: boolean;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip_address: string;
  user_agent: string;
};

export type AuthAuditEvent = {
  id: number;
  event: string;
  outcome: string;
  username: string;
  user_id: string | null;
  actor_id: string | null;
  ip_address: string;
  user_agent: string;
  detail: string;
  created_at: string;
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

export function adminLogin(input: {
  username: string;
  password: string;
}): Promise<{ user: User; expires_at: string }> {
  return request("/api/v1/auth/admin/login", {
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

export function listSessions(): Promise<Session[]> {
  return request("/api/v1/auth/sessions");
}

export function revokeSession(sessionId: string): Promise<void> {
  return request(`/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function revokeOtherSessions(): Promise<void> {
  return request("/api/v1/auth/sessions/revoke-others", { method: "POST" });
}

export function changePassword(input: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  return request("/api/v1/auth/password", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listUsers(): Promise<User[]> {
  return request("/api/v1/admin/users");
}

export function createUser(input: {
  username: string;
  display_name: string;
  password: string;
}): Promise<User> {
  return request("/api/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateUser(
  userId: string,
  input: Partial<Pick<User, "display_name" | "is_active">>,
): Promise<User> {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  return request(`/api/v1/admin/users/${encodeURIComponent(userId)}/password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

export function listAuthAuditEvents(limit = 100): Promise<AuthAuditEvent[]> {
  return request(`/api/v1/admin/audit-events?limit=${limit}`);
}
