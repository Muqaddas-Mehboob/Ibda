import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { deleteAccount } from "../auth.service";
import { supabase } from "../../../../lib/supabase";

jest.mock("../../../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: jest.fn(),
      signOut: jest.fn(),
    },
  },
}));

const getSessionMock = jest.mocked(supabase.auth.getSession);
const signOutMock = jest.mocked(supabase.auth.signOut);
const fetchMock = jest.fn<
  (url: string, init?: RequestInit) => Promise<unknown>
>();

function signedInSession(accessToken = "access-token") {
  return {
    data: { session: { access_token: accessToken } },
    error: null,
  } as never;
}

function jsonResponse(
  body: unknown,
  ok = true,
  statusCode = 200,
  statusText = "OK"
) {
  return {
    ok,
    status: statusCode,
    statusText,
    json: async () => body,
  };
}

describe("deleteAccount", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    getSessionMock.mockResolvedValue(signedInSession());
    signOutMock.mockResolvedValue({ error: null } as never);
  });

  it("clears the local session only after the backend confirms deletion", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ deleted: true }));

    const result = await deleteAccount();

    expect(result).toEqual({ error: null });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/me/delete-account/");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>).Authorization).toBe(
      "Bearer access-token"
    );
    expect(signOutMock).toHaveBeenCalledWith({ scope: "local" });
  });

  it("keeps the session and shows the backend error when deletion fails", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          code: "stripe_cancellation_failed",
          detail:
            "Your subscription could not be cancelled, so your account was not deleted.",
        },
        false,
        502,
        "Bad Gateway"
      )
    );

    const result = await deleteAccount();

    expect(result.error).toBe(
      "Your subscription could not be cancelled, so your account was not deleted."
    );
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it("does not clear the session when the backend does not confirm deletion", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));

    const result = await deleteAccount();

    expect(result.error).toMatch(/did not confirm/i);
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it("reports a network failure without clearing the session", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));

    const result = await deleteAccount();

    expect(result.error).toMatch(/couldn’t reach Ibda/i);
    expect(signOutMock).not.toHaveBeenCalled();
  });

  it("reports when the deleted account’s local session cannot be cleared", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ deleted: true }));
    signOutMock.mockResolvedValue({
      error: { message: "storage unavailable" },
    } as never);

    const result = await deleteAccount();

    expect(result.error).toMatch(/could not be cleared/);
  });
});
