import { Alert, Platform, type AlertButton } from "react-native";

export type ConfirmOptions = {
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
  /** Text shown by window.confirm() on web; defaults to title + message. */
  webPrompt?: string;
};

/**
 * Asks the user to confirm an action on every platform.
 *
 * React Native Web renders Alert.alert as a no-op, so web falls back to
 * window.confirm(). Resolves false when the user cancels or no dialog can be
 * shown, so callers can perform the action only on an explicit confirmation.
 */
export function confirmAsync(
  title: string,
  message: string,
  options: ConfirmOptions = {}
): Promise<boolean> {
  const {
    confirmText = "Confirm",
    cancelText = "Cancel",
    destructive = false,
    webPrompt,
  } = options;

  if (Platform.OS === "web") {
    if (typeof window === "undefined" || typeof window.confirm !== "function") {
      return Promise.resolve(false);
    }
    return Promise.resolve(
      window.confirm(webPrompt ?? `${title}\n\n${message}`)
    );
  }

  return new Promise<boolean>((resolve) => {
    const buttons: AlertButton[] = [
      { text: cancelText, style: "cancel", onPress: () => resolve(false) },
      {
        text: confirmText,
        style: destructive ? "destructive" : "default",
        onPress: () => resolve(true),
      },
    ];
    Alert.alert(title, message, buttons);
  });
}
