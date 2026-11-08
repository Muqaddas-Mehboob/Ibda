import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type ScheduledStatus =
  | "pending"
  | "publishing"
  | "published"
  | "failed"
  | "blocked"
  | "cancelled";

export type ScheduledContent = {
  id: string;
  brand_id: string;
  brand_name: string;
  title: string;
  body: string;
  platform: string;
  status: string;
};

export type ScheduledPostAccount = {
  id: string;
  platform: string;
  platform_account_id: string;
  display_name: string;
};

export type ScheduledPost = {
  id: string;
  post: ScheduledContent;
  platform: string;
  social_account: ScheduledPostAccount | null;
  scheduled_for: string;
  timezone_name: string;
  status: ScheduledStatus;
  attempts: number;
  last_attempt_at: string | null;
  error_message: string;
  external_post_id: string;
  published_at: string | null;
  publishing_available: boolean;
  created_at: string;
  updated_at: string;
};

export type PublishingCapability = {
  platform: string;
  label: string;
  available: boolean;
  reason: string;
};

export type ScheduleInput = {
  post_id: string;
  platforms: string[];
  scheduled_for: string;
  timezone_name: string;
  social_account_id?: string;
  social_account_ids?: Record<string, string>;
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
    if (options.body) headers.set("Content-Type", "application/json");
    headers.set("Authorization", `Bearer ${accessToken}`);
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

export function getScheduledPosts(
  start: Date,
  end: Date
): Promise<ScheduledPost[]> {
  const query = new URLSearchParams({
    start: start.toISOString(),
    end: end.toISOString(),
  });
  return request<ScheduledPost[]>(
    `/calendar/scheduled-posts/?${query.toString()}`
  );
}

export function getPublishingPlatforms(): Promise<{
  platforms: PublishingCapability[];
}> {
  return request<{ platforms: PublishingCapability[] }>("/calendar/platforms/");
}

export function schedulePost(input: ScheduleInput): Promise<ScheduledPost[]> {
  return request<ScheduledPost[]>("/calendar/scheduled-posts/create/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function rescheduleScheduledPost(
  scheduledId: string,
  input: {
    scheduled_for?: string;
    timezone_name?: string;
    social_account_id?: string;
  }
): Promise<ScheduledPost> {
  return request<ScheduledPost>(
    `/calendar/scheduled-posts/${encodeURIComponent(scheduledId)}/`,
    { method: "PATCH", body: JSON.stringify(input) }
  );
}

export function cancelScheduledPost(
  scheduledId: string
): Promise<ScheduledPost> {
  return request<ScheduledPost>(
    `/calendar/scheduled-posts/${encodeURIComponent(scheduledId)}/`,
    { method: "DELETE" }
  );
}

export function getDeviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** Parse a `YYYY-MM-DDTHH:mm` value typed by the user as device-local time. */
export function parseLocalDateTimeInput(value: string): Date | null {
  const match = value
    .trim()
    .match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})$/);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match;
  const date = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    0,
    0
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Render a UTC timestamp as the `YYYY-MM-DDTHH:mm` local input value. */
export function toLocalDateTimeInput(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
