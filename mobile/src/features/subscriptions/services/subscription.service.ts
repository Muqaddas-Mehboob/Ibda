import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type SubscriptionPlan = {
  id: "free" | "premium";
  name: string;
  price_minor: number | null;
  currency: string | null;
  billing_intervals: Array<"monthly" | "annual">;
  checkout_available: boolean;
};

export type SubscriptionPlansResponse = {
  plans: SubscriptionPlan[];
  provider_configured: boolean;
  message: string;
};

export type UserSubscription = {
  id: string;
  plan_id: string;
  billing_interval: "monthly" | "annual" | "none";
  status: "pending" | "active" | "past_due" | "canceled" | "expired" | "failed";
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  created_at: string;
};

export type PaymentTransaction = {
  id: string;
  status: "pending" | "succeeded" | "failed" | "refunded";
  amount_minor: number | null;
  currency: string;
  occurred_at: string | null;
  created_at: string;
};

export type UserSubscriptionResponse = {
  subscription: UserSubscription | null;
  plan_id: string;
  entitlements: Record<string, number | null>;
  transactions: PaymentTransaction[];
  checkout_available: boolean;
  manage_available: boolean;
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
    headers.set("Authorization", "Bearer " + accessToken);
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

export function getSubscriptionPlans(): Promise<SubscriptionPlansResponse> {
  return request("/subscription/plans/");
}

export function getUserSubscription(): Promise<UserSubscriptionResponse> {
  return request("/subscription/me/");
}
