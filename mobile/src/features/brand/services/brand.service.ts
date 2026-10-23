import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type BrandInput = {
  name: string;
  industry: string;
  description: string;
  website: string;
};

export type Brand = BrandInput & {
  id: string;
  created_at: string;
  updated_at: string;
};

async function getAccessToken(): Promise<string> {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();

  if (error) {
    throw new Error(`Unable to read your session: ${error.message}`);
  }

  if (!session?.access_token) {
    throw new Error("Your session has expired. Please sign in again.");
  }

  return session.access_token;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const result = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      result?.detail ||
      result?.message ||
      (result ? JSON.stringify(result) : response.statusText);

    throw new Error(
      `API error ${response.status}: ${detail || "Request failed."}`
    );
  }

  return result as T;
}

export async function createBrand(input: BrandInput): Promise<Brand> {
  const accessToken = await getAccessToken();

  const response = await fetch(`${API_URL}/brands/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      name: input.name.trim(),
      industry: input.industry,
      description: input.description.trim(),
      website: input.website.trim(),
    }),
  });

  return parseResponse<Brand>(response);
}

export async function getBrands(): Promise<Brand[]> {
  const accessToken = await getAccessToken();

  const response = await fetch(`${API_URL}/brands/`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
  });

  return parseResponse<Brand[]>(response);
}