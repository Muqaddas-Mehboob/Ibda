import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type SocialPlatform =
  | "instagram"
  | "facebook_pages"
  | "linkedin"
  | "tiktok";

export type SocialProvider = {
  platform: SocialPlatform;
  name: string;
  configured: boolean;
  reason: string;
};

export type SocialAccount = {
  id: string;
  platform: SocialPlatform;
  platform_account_id: string;
  display_name: string;
  status: "connected" | "expired" | "disconnected";
  token_expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ConnectedAccountsResponse = {
  providers: SocialProvider[];
  accounts: SocialAccount[];
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

export function getConnectedAccounts(): Promise<ConnectedAccountsResponse> {
  return request<ConnectedAccountsResponse>("/social/accounts/");
}

export function startSocialConnection(
  platform: SocialPlatform
): Promise<{ authorization_url: string }> {
  return request(`/social/accounts/${platform}/connect/`, { method: "POST" });
}

export function disconnectSocialAccount(accountId: string): Promise<void> {
  return request<void>(
    `/social/accounts/${encodeURIComponent(accountId)}/`,
    { method: "DELETE" }
  );
}
