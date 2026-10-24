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

async function getAccessToken(refresh = false): Promise<string> {
  if (refresh) {
    const {
      data: { session },
      error,
    } = await supabase.auth.refreshSession();

    if (error || !session?.access_token) {
      const { error: signOutError } = await supabase.auth.signOut({
        scope: "local",
      });

      if (signOutError) {
        throw new Error(
          `Your session could not be refreshed${error ? `: ${error.message}` : ""}. ` +
            `Please sign in again. Unable to clear the saved session: ${signOutError.message}`
        );
      }

      throw new Error(
        `Your session could not be refreshed${error ? `: ${error.message}` : ""}. ` +
          "You have been signed out. Please sign in again."
      );
    }

    return session.access_token;
  }

  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();

  if (error) {
    throw new Error(`Unable to read your session: ${error.message}`);
  }

  if (!session?.access_token) {
    throw new Error(
      "No Supabase access token found. Please sign in again."
    );
  }

  return session.access_token;
}

async function fetchWithAuth(
  path: string,
  accessToken: string,
  options: RequestInit
): Promise<Response> {
  const sendRequest = (token: string) => {
    const headers = new Headers(options.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(`${API_URL}${path}`, { ...options, headers });
  };

  const response = await sendRequest(accessToken);
  if (response.status !== 401) {
    return response;
  }

  return sendRequest(await getAccessToken(true));
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

  const response = await fetchWithAuth("/brands/", accessToken, {
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

  const response = await fetchWithAuth("/brands/", accessToken, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
  });

  return parseResponse<Brand[]>(response);
}