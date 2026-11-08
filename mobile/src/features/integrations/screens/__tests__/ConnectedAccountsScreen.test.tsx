import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import { ConnectedAccountsScreen } from "../ConnectedAccountsScreen";
import type {
  ConnectedAccountsResponse,
  SocialAccount,
} from "../../services/socialAccount.service";

const mockConfirm = jest.fn<() => Promise<boolean>>();
const mockGetConnectedAccounts = jest.fn<() => Promise<ConnectedAccountsResponse>>();
const mockDisconnectSocialAccount = jest.fn<(id: string) => Promise<void>>();

jest.mock("../../../../lib/confirm", () => ({
  confirmAsync: () => mockConfirm(),
}));

jest.mock("../../services/socialAccount.service", () => ({
  getConnectedAccounts: () => mockGetConnectedAccounts(),
  disconnectSocialAccount: (id: string) => mockDisconnectSocialAccount(id),
  startSocialConnection: jest.fn(),
}));

jest.mock("expo-linking", () => ({}));

jest.mock("expo-web-browser", () => ({
  openAuthSessionAsync: jest.fn(),
}));

jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual("react") as typeof import("react");
  return {
    useFocusEffect: (effect: () => void | (() => void)) => {
      useEffect(effect, [effect]);
    },
    router: { back: jest.fn(), replace: jest.fn(), canGoBack: () => true },
  };
});

jest.mock("../../../../components/navigation/BottomNavigation", () => ({
  BottomNavigation: () => null,
}));

const account: SocialAccount = {
  id: "0f7b1c2e-3f7d-4d1c-9a63-3f6b0d9a1c11",
  platform: "facebook_pages",
  platform_account_id: "1234567890",
  display_name: "Acme Page",
  status: "connected",
  token_expires_at: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

const providers: ConnectedAccountsResponse["providers"] = [
  {
    platform: "facebook_pages",
    name: "Facebook Pages",
    configured: true,
    reason: "",
  },
  {
    platform: "instagram",
    name: "Instagram",
    configured: false,
    reason: "Not available yet.",
  },
];

const accountsResponse = (
  accounts: SocialAccount[]
): ConnectedAccountsResponse => ({ providers, accounts });

const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});

const disconnectButton = (getByLabelText: (label: string) => unknown) =>
  getByLabelText("Disconnect Acme Page");

describe("ConnectedAccountsScreen disconnect", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetConnectedAccounts.mockResolvedValue(accountsResponse([account]));
  });

  it("confirms without Alert.alert and does nothing when cancelled", async () => {
    mockConfirm.mockResolvedValue(false);
    const { getByLabelText, queryByText } = await render(
      <ConnectedAccountsScreen />
    );

    await waitFor(() => expect(queryByText("Acme Page")).toBeTruthy());
    fireEvent.press(disconnectButton(getByLabelText) as never);

    await waitFor(() => expect(mockConfirm).toHaveBeenCalledTimes(1));
    expect(mockDisconnectSocialAccount).not.toHaveBeenCalled();
    expect(alertSpy).not.toHaveBeenCalled();
    expect(queryByText(/was disconnected/)).toBeNull();
  });

  it("disconnects the account, refreshes the list, and shows success", async () => {
    mockConfirm.mockResolvedValue(true);
    mockDisconnectSocialAccount.mockResolvedValue(undefined);
    mockGetConnectedAccounts
      .mockResolvedValueOnce(accountsResponse([account]))
      .mockResolvedValueOnce(
        accountsResponse([{ ...account, status: "disconnected" }])
      );

    const { getByLabelText, getByText } = await render(
      <ConnectedAccountsScreen />
    );

    await waitFor(() => expect(getByText("Connected")).toBeTruthy());
    fireEvent.press(disconnectButton(getByLabelText) as never);

    await waitFor(() => {
      expect(mockDisconnectSocialAccount).toHaveBeenCalledWith(account.id);
    });
    await waitFor(() => {
      expect(getByText("Acme Page was disconnected.")).toBeTruthy();
    });
    expect(mockGetConnectedAccounts).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(getByText("Disconnected")).toBeTruthy());
  });

  it("surfaces a failed disconnect instead of swallowing the error", async () => {
    mockConfirm.mockResolvedValue(true);
    mockDisconnectSocialAccount.mockRejectedValue(
      new Error("API error 500: Unable to disconnect this account.")
    );

    const { getByLabelText, getByText, queryByText } = await render(
      <ConnectedAccountsScreen />
    );

    await waitFor(() => expect(getByText("Connected")).toBeTruthy());
    fireEvent.press(disconnectButton(getByLabelText) as never);

    await waitFor(() => {
      expect(
        getByText("API error 500: Unable to disconnect this account.")
      ).toBeTruthy();
    });
    expect(mockGetConnectedAccounts).toHaveBeenCalledTimes(1);
    expect(queryByText(/was disconnected/)).toBeNull();
  });
});
