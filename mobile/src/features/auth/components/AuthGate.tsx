import { useEffect, type ReactNode } from "react";
import { ActivityIndicator, View } from "react-native";
import { useSegments, useRouter } from "expo-router";
import { useAuth } from "../providers/AuthProvider";
import {
  AUTHENTICATED_ROUTE,
  SIGN_IN_ROUTE,
} from "../utils/auth-redirect";

export function AuthGate({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  const currentRoute = segments[0];
  const isAuthRoute =
    currentRoute === "sign-in" ||
    currentRoute === "sign-up" ||
    currentRoute === "forgot-password";

  // The OAuth callback owns its own navigation: it must be able to wait for the
  // code exchange without AuthGate bouncing to /sign-in or /onboarding first.
  const isOAuthCallbackRoute =
    currentRoute === "auth" && segments[1] === "callback";

  const isPublicRoute =
    currentRoute === undefined ||
    isAuthRoute ||
    isOAuthCallbackRoute;

  useEffect(() => {
    if (loading || isOAuthCallbackRoute) return;

    if (!session && !isPublicRoute) {
      router.replace(SIGN_IN_ROUTE);
      return;
    }

    if (session && isPublicRoute) {
      router.replace(AUTHENTICATED_ROUTE);
    }
  }, [loading, session, isPublicRoute, isOAuthCallbackRoute, router]);

  if (isOAuthCallbackRoute) {
    return <>{children}</>;
  }

  if (loading) {
    return (
      <View className="flex-1 items-center justify-center bg-ibda-background">
        <ActivityIndicator size="large" color="#FF6B5F" />
      </View>
    );
  }

  if ((!session && !isPublicRoute) || (session && isPublicRoute)) {
    return (
      <View className="flex-1 items-center justify-center bg-ibda-background">
        <ActivityIndicator size="large" color="#FF6B5F" />
      </View>
    );
  }

  return <>{children}</>;
}