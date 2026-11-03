import { Alert, Platform } from "react-native";
import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { confirmAsync } from "../confirm";

const originalPlatform = Platform.OS;

function setPlatform(os: typeof originalPlatform) {
  Object.defineProperty(Platform, "OS", { configurable: true, value: os });
}

type WindowGlobal = {
  window?: { confirm: (message?: string) => boolean };
};

function setWindow(value: WindowGlobal["window"]) {
  if (value) {
    (globalThis as WindowGlobal).window = value;
  } else {
    delete (globalThis as WindowGlobal).window;
  }
}

describe("confirmAsync", () => {
  beforeEach(() => {
    setPlatform(originalPlatform);
    setWindow(undefined);
  });

  afterEach(() => {
    setPlatform(originalPlatform);
    setWindow(undefined);
    jest.restoreAllMocks();
  });

  it("uses window.confirm on web and resolves true when confirmed", async () => {
    setPlatform("web");
    const confirm = jest.fn<(message?: string) => boolean>(() => true);
    setWindow({ confirm });

    await expect(
      confirmAsync("Sign out?", "You’ll need to sign in again to access Ibda.", {
        confirmText: "Sign out",
        destructive: true,
      })
    ).resolves.toBe(true);
    expect(confirm).toHaveBeenCalledWith(
      "Sign out?\n\nYou’ll need to sign in again to access Ibda."
    );
  });

  it("resolves false on web when the user dismisses the dialog", async () => {
    setPlatform("web");
    const confirm = jest.fn<(message?: string) => boolean>(() => false);
    setWindow({ confirm });

    await expect(confirmAsync("Delete your account?", "This is permanent.")).resolves.toBe(
      false
    );
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("uses the web prompt override when one is provided", async () => {
    setPlatform("web");
    const confirm = jest.fn<(message?: string) => boolean>(() => true);
    setWindow({ confirm });

    await confirmAsync("Confirm plan change", "Switch to Pro?", {
      webPrompt: "Switch to Pro?",
    });

    expect(confirm).toHaveBeenCalledWith("Switch to Pro?");
  });

  it("resolves false on native when the user cancels", async () => {
    setPlatform("android");
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const result = confirmAsync("Delete your account?", "This is permanent.", {
      confirmText: "Delete account",
      cancelText: "Close",
      destructive: true,
    });

    const buttons = alertSpy.mock.calls[0]?.[2];
    buttons?.[0]?.onPress?.();

    await expect(result).resolves.toBe(false);
    expect(buttons?.[0]?.text).toBe("Close");
    expect(buttons?.[1]?.text).toBe("Delete account");
    expect(buttons?.[1]?.style).toBe("destructive");
  });

  it("resolves true on native when the user confirms", async () => {
    setPlatform("ios");
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    const result = confirmAsync("Sign out?", "You’ll need to sign in again.", {
      confirmText: "Sign out",
      cancelText: "Cancel",
      destructive: true,
    });

    const buttons = alertSpy.mock.calls[0]?.[2];
    buttons?.[1]?.onPress?.();

    await expect(result).resolves.toBe(true);
    expect(alertSpy).toHaveBeenCalledWith(
      "Sign out?",
      "You’ll need to sign in again.",
      expect.any(Array)
    );
  });

  it("resolves false when no web dialog is available", async () => {
    setPlatform("web");
    setWindow(undefined);

    await expect(confirmAsync("Sign out?", "Are you sure?")).resolves.toBe(false);
  });
});
