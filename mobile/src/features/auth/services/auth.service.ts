import { supabase } from "../../../lib/supabase";

const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000/api"
).replace(/\/+$/, "");

export type AuthResult = {
  error: string | null;
};

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}

export async function signIn(
  email: string,
  password: string
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim().toLowerCase(),
      password,
    });

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function signUp(
  name: string,
  email: string,
  password: string
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.signUp({
      email: email.trim().toLowerCase(),
      password,
      options: {
        data: {
          full_name: name.trim(),
        },
      },
    });

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function resetPassword(
  email: string
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.resetPasswordForEmail(
      email.trim().toLowerCase()
    );

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function signOut(
  scope: "local" | "global" = "global"
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.signOut({ scope });

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function deleteAccount(): Promise<AuthResult> {
  try {
    const {
      data: { session },
      error: sessionError,
    } = await supabase.auth.getSession();

    if (sessionError) {
      return { error: `Unable to load your session: ${sessionError.message}` };
    }

    if (!session?.access_token) {
      return { error: "Please sign in again to continue." };
    }

    const response = await fetch(`${API_URL}/me/delete-account/`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
    });

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail =
        data?.detail || data?.message || response.statusText || "Request failed.";
      return { error: `API error ${response.status}: ${detail}` };
    }

    const { error: signOutError } = await supabase.auth.signOut({
      scope: "global",
    });

    if (signOutError) {
      return {
        error: `Your account was deleted, but the local session could not be cleared: ${signOutError.message}`,
      };
    }

    return { error: null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}