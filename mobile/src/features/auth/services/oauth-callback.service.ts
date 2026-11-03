import type { Session } from "@supabase/supabase-js";
import { supabase } from "../../../lib/supabase";

export type OAuthCallbackParams = {
  code?: string;
  error?: string;
  errorDescription?: string;
};

export type OAuthCallbackResult = { session: Session } | { error: string };

export const OAUTH_CALLBACK_MESSAGES = {
  consentDenied:
    "Google sign-in was cancelled before access was granted. Please try again.",
  unavailable:
    "Google sign-in is temporarily unavailable. Please try again in a moment.",
  missingCode:
    "This sign-in link is missing its authorization code. Please sign in with Google again.",
  expired:
    "This sign-in link has expired or was already used. Please sign in with Google again.",
  noSession:
    "Google sign-in did not persist a session. Please sign in with Google again.",
  unknown: "We couldn’t complete Google sign-in. Please try again.",
} as const;

/** Maps the OAuth error parameters Google/Supabase return to a user-facing message. */
export function describeOAuthCallbackError(
  errorCode: string,
  errorDescription: string
): string {
  if (errorCode === "access_denied") {
    return OAUTH_CALLBACK_MESSAGES.consentDenied;
  }
  if (
    errorCode === "server_error" ||
    errorCode === "temporarily_unavailable"
  ) {
    return OAUTH_CALLBACK_MESSAGES.unavailable;
  }
  if (errorDescription) {
    return errorDescription;
  }
  return OAUTH_CALLBACK_MESSAGES.unknown;
}

/**
 * Completes a Google OAuth callback.
 *
 * On web, supabase-js (detectSessionInUrl) usually exchanges the code while the
 * client initializes, so the existing-session check runs first and waits for
 * that initialization. On native the deep-link route performs the exchange.
 */
export async function completeOAuthCallback({
  code,
  error,
  errorDescription,
}: OAuthCallbackParams): Promise<OAuthCallbackResult> {
  if (error || errorDescription) {
    return {
      error: describeOAuthCallbackError(error ?? "", errorDescription ?? ""),
    };
  }

  try {
    const {
      data: { session },
      error: sessionError,
    } = await supabase.auth.getSession();

    if (sessionError) {
      return { error: `Unable to read your session: ${sessionError.message}` };
    }

    if (session) {
      return { session };
    }

    if (!code) {
      return { error: OAUTH_CALLBACK_MESSAGES.missingCode };
    }

    const { data, error: exchangeError } =
      await supabase.auth.exchangeCodeForSession(code);

    if (exchangeError) {
      return { error: OAUTH_CALLBACK_MESSAGES.expired };
    }

    if (!data.session) {
      return { error: OAUTH_CALLBACK_MESSAGES.noSession };
    }

    return { session: data.session };
  } catch (unexpectedError) {
    return {
      error:
        unexpectedError instanceof Error
          ? unexpectedError.message
          : OAUTH_CALLBACK_MESSAGES.unknown,
    };
  }
}
