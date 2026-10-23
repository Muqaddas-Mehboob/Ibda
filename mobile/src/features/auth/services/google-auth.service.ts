import { Platform } from "react-native";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { supabase } from "../../../lib/supabase";

WebBrowser.maybeCompleteAuthSession();

export async function signInWithGoogle(): Promise<string | null> {
  try {
    const redirectTo = Linking.createURL("/");

    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo,
        skipBrowserRedirect: Platform.OS !== "web",
      },
    });

    if (error) return error.message;
    if (!data.url) return "Unable to start Google sign-in.";

    if (Platform.OS === "web") {
      window.location.assign(data.url);
      return null;
    }

    const result = await WebBrowser.openAuthSessionAsync(
      data.url,
      redirectTo
    );

    if (result.type !== "success") {
      return result.type === "cancel"
        ? "Google sign-in was cancelled."
        : "Google sign-in did not complete.";
    }

    const params = Linking.parse(result.url).queryParams ?? {};

    if (typeof params.error_description === "string") {
      return params.error_description;
    }

    if (typeof params.code === "string") {
      const { error: exchangeError } =
        await supabase.auth.exchangeCodeForSession(params.code);

      return exchangeError?.message ?? null;
    }

    return "No authentication code was returned. Please try again.";
  } catch (error) {
    return error instanceof Error
      ? error.message
      : "Unable to sign in with Google.";
  }
}