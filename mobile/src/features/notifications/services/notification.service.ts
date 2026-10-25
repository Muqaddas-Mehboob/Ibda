import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type NotificationDestination = "approval" | "calendar" | "";

export type AppNotification = {
  id: string;
  notification_type: string;
  title: string;
  message: string;
  related_object_id: string | null;
  destination: NotificationDestination;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
};

export type NotificationListResponse = {
  results: AppNotification[];
  unread_count: number;
};

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    throw new Error(`Unable to read your session: ${sessionError.message}`);
  }
  if (!session?.access_token) {
    throw new Error("Please sign in again to continue.");
  }

  const send = (accessToken: string) => {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${accessToken}`);
    if (options.body) headers.set("Content-Type", "application/json");
    return fetch(`${API_URL}${path}`, { ...options, headers });
  };

  let response = await send(session.access_token);
  if (response.status === 401) {
    const {
      data: { session: refreshedSession },
      error: refreshError,
    } = await supabase.auth.refreshSession();

    if (refreshError || !refreshedSession?.access_token) {
      const { error: signOutError } = await supabase.auth.signOut({
        scope: "local",
      });
      if (signOutError) {
        throw new Error(
          `Your session could not be refreshed${refreshError ? `: ${refreshError.message}` : ""}. ` +
            `Please sign in again. Unable to clear the saved session: ${signOutError.message}`
        );
      }
      throw new Error(
        `Your session could not be refreshed${refreshError ? `: ${refreshError.message}` : ""}. ` +
          "You have been signed out. Please sign in again."
      );
    }
    response = await send(refreshedSession.access_token);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      data?.detail ||
      data?.message ||
      (data ? JSON.stringify(data) : response.statusText);
    throw new Error(
      `API error ${response.status}: ${detail || "Request failed."}`
    );
  }
  return data as T;
}

export function getNotifications(): Promise<NotificationListResponse> {
  return request<NotificationListResponse>("/notifications/");
}

export async function getUnreadNotificationCount(): Promise<number> {
  const response = await request<{ unread_count: number }>(
    "/notifications/unread-count/"
  );
  return response.unread_count;
}

export function markNotificationRead(
  notificationId: string
): Promise<AppNotification> {
  return request<AppNotification>(
    `/notifications/${encodeURIComponent(notificationId)}/read/`,
    { method: "PATCH" }
  );
}

export function markAllNotificationsRead(): Promise<{
  updated_count: number;
  unread_count: number;
}> {
  return request("/notifications/read-all/", { method: "POST" });
}
