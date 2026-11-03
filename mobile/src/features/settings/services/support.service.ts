import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type SupportRequestInput = {
  contact_email: string;
  subject: string;
  message: string;
};

export type SupportRequestReceipt = {
  id: string;
  status: "new" | "in_progress" | "resolved";
  created_at: string;
};

export async function submitSupportRequest(
  input: SupportRequestInput
): Promise<SupportRequestReceipt> {
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();
  if (sessionError) {
    throw new Error(`Unable to read your session: ${sessionError.message}`);
  }
  if (!session?.access_token) {
    throw new Error("Please sign in again to send a support request.");
  }

  const send = (accessToken: string) =>
    fetch(`${API_URL}/support/requests/`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(input),
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
      data?.contact_email?.[0] ||
      data?.subject?.[0] ||
      data?.message?.[0] ||
      (data ? JSON.stringify(data) : response.statusText);
    throw new Error(
      `Could not send your support request: ${detail || "Please try again."}`
    );
  }

  return data as SupportRequestReceipt;
}
