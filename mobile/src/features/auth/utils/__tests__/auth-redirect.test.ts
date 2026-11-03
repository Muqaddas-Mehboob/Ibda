import type { Session } from "@supabase/supabase-js";
import { describe, expect, it } from "@jest/globals";
import {
  AUTHENTICATED_ROUTE,
  resolveAuthRedirect,
  SIGN_IN_ROUTE,
} from "../auth-redirect";

describe("resolveAuthRedirect", () => {
  it("sends an authenticated user to onboarding", () => {
    const session = { access_token: "token" } as unknown as Session;

    expect(resolveAuthRedirect(session)).toBe(AUTHENTICATED_ROUTE);
    expect(AUTHENTICATED_ROUTE).toBe("/onboarding");
  });

  it("sends a user without a session to sign-in", () => {
    expect(resolveAuthRedirect(null)).toBe(SIGN_IN_ROUTE);
    expect(SIGN_IN_ROUTE).toBe("/sign-in");
  });
});
