import type { Session } from "@supabase/supabase-js";
import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import {
  completeOAuthCallback,
  describeOAuthCallbackError,
  OAUTH_CALLBACK_MESSAGES,
} from "../oauth-callback.service";
import { supabase } from "../../../../lib/supabase";

jest.mock("../../../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: jest.fn(),
      exchangeCodeForSession: jest.fn(),
    },
  },
}));

const getSessionMock = jest.mocked(supabase.auth.getSession);
const exchangeMock = jest.mocked(supabase.auth.exchangeCodeForSession);

function fakeSession(accessToken = "access-token"): Session {
  return { access_token: accessToken } as unknown as Session;
}

describe("completeOAuthCallback", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getSessionMock.mockResolvedValue({
      data: { session: null },
      error: null,
    } as never);
    exchangeMock.mockResolvedValue({
      data: { session: null, user: null },
      error: null,
    } as never);
  });

  it("reports denied consent without attempting a code exchange", async () => {
    const result = await completeOAuthCallback({
      error: "access_denied",
      errorDescription: "The user denied your request",
    });

    expect(result).toEqual({ error: OAUTH_CALLBACK_MESSAGES.consentDenied });
    expect(getSessionMock).not.toHaveBeenCalled();
    expect(exchangeMock).not.toHaveBeenCalled();
  });

  it("reports a missing authorization code gracefully", async () => {
    const result = await completeOAuthCallback({});

    expect(result).toEqual({ error: OAUTH_CALLBACK_MESSAGES.missingCode });
    expect(exchangeMock).not.toHaveBeenCalled();
  });

  it("reports an expired or already-used code instead of the raw Stripe-style error", async () => {
    exchangeMock.mockResolvedValue({
      data: { session: null, user: null },
      error: { message: "invalid request: code verifier missing" },
    } as never);

    const result = await completeOAuthCallback({ code: "expired-code" });

    expect(result).toEqual({ error: OAUTH_CALLBACK_MESSAGES.expired });
    expect(exchangeMock).toHaveBeenCalledWith("expired-code");
  });

  it("uses the session established by detectSessionInUrl without exchanging twice", async () => {
    const session = fakeSession();
    getSessionMock.mockResolvedValue({
      data: { session },
      error: null,
    } as never);

    const result = await completeOAuthCallback({ code: "web-code" });

    expect(result).toEqual({ session });
    expect(exchangeMock).not.toHaveBeenCalled();
  });

  it("exchanges the native deep-link code and returns the session", async () => {
    const session = fakeSession();
    exchangeMock.mockResolvedValue({
      data: { session, user: null },
      error: null,
    } as never);

    const result = await completeOAuthCallback({ code: "native-code" });

    expect(result).toEqual({ session });
    expect(exchangeMock).toHaveBeenCalledWith("native-code");
  });

  it("reports when the exchange does not persist a session", async () => {
    exchangeMock.mockResolvedValue({
      data: { session: null, user: null },
      error: null,
    } as never);

    const result = await completeOAuthCallback({ code: "no-session-code" });

    expect(result).toEqual({ error: OAUTH_CALLBACK_MESSAGES.noSession });
  });

  it("reports when the saved session cannot be read", async () => {
    getSessionMock.mockResolvedValue({
      data: { session: null },
      error: { message: "storage unavailable" },
    } as never);

    const result = await completeOAuthCallback({ code: "code" });

    expect(result).toEqual({
      error: "Unable to read your session: storage unavailable",
    });
    expect(exchangeMock).not.toHaveBeenCalled();
  });
});

describe("describeOAuthCallbackError", () => {
  it("maps temporary provider failures to a retry message", () => {
    expect(describeOAuthCallbackError("temporarily_unavailable", "")).toBe(
      OAUTH_CALLBACK_MESSAGES.unavailable
    );
  });

  it("keeps a provider description when there is no known code", () => {
    expect(describeOAuthCallbackError("", "Something specific")).toBe(
      "Something specific"
    );
  });

  it("falls back to a generic message", () => {
    expect(describeOAuthCallbackError("", "")).toBe(
      OAUTH_CALLBACK_MESSAGES.unknown
    );
  });
});
