import "react-native-get-random-values";

import Constants from "expo-constants";
import { Platform } from "react-native";
import { supabase } from "../../../lib/supabase";
import type {
  BillingInterval,
  PlanId,
  PricingPlan,
} from "../data/planCatalog";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);
let loggedLocalApiResolution = false;

function getApiUrl(): string {
  const url = new URL(API_URL);
  if (Platform.OS === "web" || !LOOPBACK_HOSTS.has(url.hostname)) {
    return url.toString().replace(/\/+$/, "");
  }

  if (!__DEV__) {
    throw new Error(
      "The billing API is configured to use this device as its own server. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }

  const hostUri = Constants.expoConfig?.hostUri;
  if (!hostUri) {
    throw new Error(
      "Unable to find the Expo development host for the billing API. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }

  let developmentHost: string;
  try {
    developmentHost = new URL(`http://${hostUri}`).hostname;
  } catch {
    throw new Error(
      "Unable to resolve the Expo development host for the billing API. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }
  if (!developmentHost || LOOPBACK_HOSTS.has(developmentHost)) {
    throw new Error(
      "The Expo development host is not reachable by this device. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }

  url.hostname = developmentHost;
  if (!loggedLocalApiResolution) {
    console.info(
      "[subscription] Using the Expo development host for the local billing API."
    );
    loggedLocalApiResolution = true;
  }
  return url.toString().replace(/\/+$/, "");
}

export type SubscriptionPlan = PricingPlan;

export type SubscriptionPlansResponse = {
  plans: SubscriptionPlan[];
  provider_configured: boolean;
  checkout_available: boolean;
  missing_configuration: string[];
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

export type SubscriptionCheckoutResponse = {
  checkout_url: string;
  session_id: string;
};

export class SubscriptionApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
    this.name = "SubscriptionApiError";
  }
}

export class SubscriptionSessionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SubscriptionSessionError";
  }
}

export class SubscriptionFetchError extends Error {
  constructor(
    readonly category: string,
    message: string
  ) {
    super(message);
    this.name = "SubscriptionFetchError";
  }
}

function throwFetchError(
  path: string,
  method: string,
  error: unknown,
  afterRefresh = false
): never {
  const errorName = error instanceof Error ? error.name : "UnknownError";
  const errorMessage =
    error instanceof Error ? error.message : "Unknown fetch error.";
  const category =
    errorName === "AbortError"
      ? "aborted"
      : Platform.OS === "web" && errorName === "TypeError"
        ? "browser_fetch_failed"
        : errorName === "TypeError"
          ? "network"
          : "fetch_exception";
  console.warn(
    `[subscription] API request failed: method=${method} endpoint=${path} category=${category}${afterRefresh ? "_after_refresh" : ""} error_name=${errorName} error_message=${errorMessage}`
  );
  throw new SubscriptionFetchError(
    category,
    `Billing request failed (${category}): ${errorMessage}`
  );
}

function createIdempotencyKey(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");

  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    throw new SubscriptionSessionError(
      `Unable to read your session. Please sign in again. ${sessionError.message}`
    );
  }
  if (!session?.access_token) {
    throw new SubscriptionSessionError(
      "You are signed out. Please sign in to continue."
    );
  }

  const apiUrl = getApiUrl();
  const method = (options.method ?? "GET").toUpperCase();
  const send = (accessToken: string) => {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", "Bearer " + accessToken);
    if (options.body) headers.set("Content-Type", "application/json");
    return fetch(`${apiUrl}${path}`, { ...options, headers });
  };

  let response: Response;
  try {
    response = await send(session.access_token);
  } catch (error) {
    throwFetchError(path, method, error);
  }
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
        throw new SubscriptionSessionError(
          `Your session could not be refreshed${refreshError ? `: ${refreshError.message}` : ""}. ` +
            `Please sign in again. Unable to clear the saved session: ${signOutError.message}`
        );
      }
      throw new SubscriptionSessionError(
        `Your session could not be refreshed${refreshError ? `: ${refreshError.message}` : ""}. ` +
          "Please sign in again."
      );
    }
    try {
      response = await send(refreshedSession.access_token);
    } catch (error) {
      throwFetchError(path, method, error, true);
    }
  }

  if (response.status === 401) {
    const { error: signOutError } = await supabase.auth.signOut({
      scope: "local",
    });
    throw new SubscriptionSessionError(
      signOutError
        ? `Your session is no longer valid. Please sign in again. Unable to clear the saved session: ${signOutError.message}`
        : "Your session is no longer valid. Please sign in again."
    );
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const category =
      response.status === 401 || response.status === 403
        ? "authentication"
        : response.status === 409
          ? "conflict"
          : response.status === 503
            ? "unavailable"
            : response.status >= 500
              ? "server"
              : "request";
    console.warn(
      `[subscription] API request failed: method=${method} endpoint=${path} status=${response.status} category=${category}`
    );
    const detail =
      data?.detail ||
      data?.message ||
      (data ? JSON.stringify(data) : response.statusText);
    throw new SubscriptionApiError(
      `API error ${response.status}: ${detail || "Request failed."}`,
      response.status
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

export function startSubscriptionCheckout(
  planId: PlanId,
  billingInterval: BillingInterval
): Promise<SubscriptionCheckoutResponse> {
  return request("/subscription/checkout/", {
    method: "POST",
    headers: {
      "Idempotency-Key": createIdempotencyKey(),
    },
    body: JSON.stringify({
      plan_id: planId,
      billing_interval: billingInterval,
    }),
  });
}
