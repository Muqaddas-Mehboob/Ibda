import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type AnalyticsDays = 7 | 30 | 90;

export type AnalyticsSummary = {
  content_posts: number;
  pending_approvals: number;
  approved_content: number;
  rejected_content: number;
  scheduled_posts: number;
};

export type AnalyticsActivity = {
  date: string;
  content_posts: number;
};

export type AnalyticsBrand = {
  brand_id: string;
  brand_name: string;
  content_posts: number;
};

export type AnalyticsResponse = {
  range: {
    days: number;
    start: string;
    end: string;
  };
  summary: AnalyticsSummary;
  activity_granularity: "day" | "week";
  activity: AnalyticsActivity[];
  brands: AnalyticsBrand[];
};

async function request<T>(path: string): Promise<T> {
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

  const send = (accessToken: string) =>
    fetch(`${API_URL}${path}`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
    });

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
  if (!data || typeof data !== "object" || !data.summary) {
    throw new Error("The analytics API returned an unexpected response.");
  }
  return data as T;
}

export function getAnalytics(days: AnalyticsDays): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>(`/analytics/?days=${days}`);
}
