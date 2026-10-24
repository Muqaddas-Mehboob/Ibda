import { supabase } from "../../../lib/supabase";
import type { Brand } from "../../brand/services/brand.service";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type BrandVoice = {
  id?: string;
  brand: string;
  tone: string;
  target_audience: string;
  language: string;
  writing_guidelines: string;
  example_content: string;
  created_at?: string;
  updated_at?: string;
};

export type BrandMemoryProfile = Brand & {
  voice: BrandVoice | null;
};

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) throw new Error(sessionError.message);
  if (!session?.access_token) {
    throw new Error("Please sign in again to continue.");
  }

  let response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
      ...options.headers,
    },
  });

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

    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("Content-Type", "application/json");
    headers.set("Authorization", `Bearer ${refreshedSession.access_token}`);
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      data?.detail ||
        data?.message ||
        "Unable to complete the request. Please try again."
    );
  }

  return data as T;
}

export function getMemoryBrands() {
  return request<BrandMemoryProfile[]>("/brands/");
}

export function getBrandVoice(brandId: string) {
  return request<BrandVoice>(`/brands/${brandId}/voice/`);
}

export function saveBrandVoice(
  brandId: string,
  input: Omit<BrandVoice, "id" | "brand" | "created_at" | "updated_at">
) {
  return request<BrandVoice>(`/brands/${brandId}/voice/`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}