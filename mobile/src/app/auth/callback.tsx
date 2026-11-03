import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { completeOAuthCallback } from "../../features/auth/services/oauth-callback.service";
import {
  resolveAuthRedirect,
  SIGN_IN_ROUTE,
} from "../../features/auth/utils/auth-redirect";

function firstParam(value: string | string[] | undefined): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value[0] ?? "";
  return "";
}

export default function AuthCallbackRoute() {
  const params = useLocalSearchParams<{
    code?: string | string[];
    error?: string | string[];
    error_description?: string | string[];
  }>();
  const code = firstParam(params.code);
  const error = firstParam(params.error);
  const errorDescription = firstParam(params.error_description);
  const [message, setMessage] = useState("");
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    let active = true;

    async function finish() {
      const result = await completeOAuthCallback({
        code,
        error,
        errorDescription,
      });

      if (!active) return;

      if ("session" in result) {
        router.replace(resolveAuthRedirect(result.session));
        return;
      }

      setMessage(result.error);
    }

    void finish();

    return () => {
      active = false;
    };
  }, [code, error, errorDescription]);

  return (
    <View className="flex-1 items-center justify-center bg-ibda-background px-6">
      {message ? (
        <>
          <Text className="text-2xl font-bold text-ibda-charcoal">
            Google sign-in failed
          </Text>
          <Text
            accessibilityRole="alert"
            className="mt-3 text-center text-base leading-6 text-ibda-brown"
          >
            {message}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.replace(SIGN_IN_ROUTE)}
            className="mt-6 min-h-14 w-full items-center justify-center rounded-full bg-ibda-coral px-4"
          >
            <Text className="font-bold text-white">Back to sign in</Text>
          </Pressable>
        </>
      ) : (
        <>
          <ActivityIndicator size="large" color="#FF6B5F" />
          <Text className="mt-4 text-center text-base text-ibda-brown">
            Finishing Google sign-in...
          </Text>
        </>
      )}
    </View>
  );
}
