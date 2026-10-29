import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type SocialPlatform =
  | "instagram"
  | "facebook"
  | "linkedin"
  | "tiktok"
  | "x"
  | "other";

export type ContentType =
  | "caption"
  | "promotional"
  | "educational"
  | "announcement";

export type GenerateContentInput = {
  brand_id: string;
  platform: SocialPlatform;
  content_type: ContentType;
  topic: string;
  tone: string;
  language: string;
  keywords: string[];
  call_to_action: string;
};

export type GeneratedContent = Pick<
  GenerateContentInput,
  "brand_id" | "platform" | "content_type"
> & {
  content: string;
};
export type GEOOptimizeInput = {
  brand_id: string;
  platform: SocialPlatform;
  content: string;
};

export type GEOOptimizeResult = {
  improvements: string[];
  optimized_content: string;
};
export type ContentPost = {
  id: string;
  brand_name: string;
  title: string;
  body: string;
  platform: SocialPlatform;
  content_type: ContentType;
  status: string;
  ai_generated: boolean;
  created_at: string;
  updated_at: string;
};

export type SaveContentInput = Pick<
  GenerateContentInput,
  "brand_id" | "platform" | "content_type"
> & {
  title: string;
  body: string;
};

export type SubmittedApproval = {
  id: string;
  status: "pending" | "approved" | "rejected";
  post: { id: string };
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
    headers.set("Content-Type", "application/json");
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

export function generateContent(
  input: GenerateContentInput
): Promise<GeneratedContent> {
  return request<GeneratedContent>("/content/generate/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
export function optimizeContentForGEO(
  input: GEOOptimizeInput
): Promise<GEOOptimizeResult> {
  return request<GEOOptimizeResult>("/content/geo/analyze/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function saveContent(input: SaveContentInput): Promise<ContentPost> {
  return request<ContentPost>("/content/posts/", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateContent(
  postId: string,
  input: Pick<SaveContentInput, "title" | "body" | "platform" | "content_type">
): Promise<ContentPost> {
  return request<ContentPost>(
    `/content/posts/${encodeURIComponent(postId)}/`,
    { method: "PATCH", body: JSON.stringify(input) }
  );
}

export function submitForApproval(
  postId: string
): Promise<SubmittedApproval> {
  return request<SubmittedApproval>(
    `/content/posts/${encodeURIComponent(postId)}/submit-for-approval/`,
    { method: "POST" }
  );
}

