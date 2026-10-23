import { useEffect, type ReactNode } from "react";
import { ActivityIndicator, View } from "react-native";
import { useSegments, useRouter } from "expo-router";
import { useAuth } from "../providers/AuthProvider";

export function AuthGate({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  const currentRoute = segments[0];
  const isAuthRoute =
    currentRoute === "sign-in" ||
    currentRoute === "sign-up" ||
    currentRoute === "forgot-password";

  const isPublicRoute =
    currentRoute === undefined ||
    isAuthRoute;

  useEffect(() => {
    if (loading) return;

    if (!session && !isPublicRoute) {
      router.replace("/");
      return;
    }

    if (session && isPublicRoute) {
      router.replace("/onboarding");
    }
  }, [loading, session, isPublicRoute, router]);

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