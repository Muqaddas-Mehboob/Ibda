import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type ApprovalStatus = "pending" | "approved" | "rejected";
export type ApprovalDecision = "approve" | "reject";

export type ApprovalPost = {
  id: string;
  brand_id: string;
  brand_name: string;
  title: string;
  body: string;
  platform: string;
  post_status: string;
  created_at: string;
};

export type Approval = {
  id: string;
  post: ApprovalPost;
  status: ApprovalStatus;
  feedback: string;
  reviewer_id: string | null;
  reviewed_at: string | null;
  created_at: string;
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

export function getApprovals(status: ApprovalStatus): Promise<Approval[]> {
  return request<Approval[]>(`/approvals/?status=${status}`);
}

export function getApproval(approvalId: string): Promise<Approval> {
  return request<Approval>(`/approvals/${encodeURIComponent(approvalId)}/`);
}

export function reviewApproval(
  approvalId: string,
  decision: ApprovalDecision
): Promise<Approval> {
  return request<Approval>(
    `/approvals/${encodeURIComponent(approvalId)}/${decision}/`,
    { method: "POST" }
  );
}
