import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import { SettingsScreen } from "../SettingsScreen";
import { supabase } from "../../../../lib/supabase";

const mockReplace = jest.fn<(path: string) => void>();
const mockPush = jest.fn<(path: string) => void>();
const mockConfirm = jest.fn<() => Promise<boolean>>();
const mockDeleteAccount = jest.fn<() => Promise<{ error: string | null }>>();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

jest.mock("../../../../lib/confirm", () => ({
  confirmAsync: () => mockConfirm(),
}));

jest.mock("../../../auth/services/auth.service", () => ({
  deleteAccount: () => mockDeleteAccount(),
  signOut: jest.fn(),
}));

jest.mock("../../../../lib/supabase", () => ({
  supabase: { auth: { getUser: jest.fn() } },
}));

jest.mock("../../../../components/navigation/BottomNavigation", () => ({
  BottomNavigation: () => null,
}));

const getUserMock = jest.mocked(supabase.auth.getUser);
const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});

describe("SettingsScreen account deletion", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockConfirm.mockResolvedValue(true);
    getUserMock.mockResolvedValue({
      data: { user: null },
      error: null,
    } as never);
  });

  it("redirects to the public landing page only after confirmed deletion", async () => {
    mockDeleteAccount.mockResolvedValue({ error: null });
    const { getByLabelText } = await render(<SettingsScreen />);

    fireEvent.press(getByLabelText(/^Delete account\./));

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/");
    });
    expect(mockDeleteAccount).toHaveBeenCalledTimes(1);
    expect(alertSpy).toHaveBeenCalledWith(
      "Account deleted",
      expect.stringContaining("permanently deleted")
    );
  });

  it("shows the backend error and stays put when deletion fails", async () => {
    const detail =
      "Your subscription could not be cancelled, so your account was not deleted.";
    mockDeleteAccount.mockResolvedValue({ error: detail });
    const { getByLabelText } = await render(<SettingsScreen />);

    fireEvent.press(getByLabelText(/^Delete account\./));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith("Couldn’t delete account", detail);
    });
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("does nothing when the confirmation dialog is dismissed", async () => {
    mockConfirm.mockResolvedValue(false);
    const { getByLabelText } = await render(<SettingsScreen />);

    fireEvent.press(getByLabelText(/^Delete account\./));

    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalled();
    });
    expect(mockDeleteAccount).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
