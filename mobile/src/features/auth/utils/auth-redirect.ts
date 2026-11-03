import type { Session } from "@supabase/supabase-js";

export const SIGN_IN_ROUTE = "/sign-in";
export const AUTHENTICATED_ROUTE = "/onboarding";

export type AuthRedirectTarget =
  | typeof SIGN_IN_ROUTE
  | typeof AUTHENTICATED_ROUTE;

/**
 * Single destination resolver for authentication outcomes.
 *
 * Every authenticated user currently enters through the onboarding welcome,
 * which is the only post-auth destination the app defines. Unauthenticated
 * users are sent to sign-in.
 */
export function resolveAuthRedirect(
  session: Session | null
): AuthRedirectTarget {
  return session ? AUTHENTICATED_ROUTE : SIGN_IN_ROUTE;
}
