import { router } from "expo-router";
import { Alert, Platform, Pressable, Text, View } from "react-native";
import { signOut } from "../features/auth/services/auth.service";
import { useAuth } from "../features/auth/providers/AuthProvider";
import { useState } from "react";

export default function OnboardingRoute() {
  const { session } = useAuth();
  const [loading, setLoading] = useState(false);

  async function handleSignOut() {
    setLoading(true);

    try {
      const result = await signOut();

      if (result.error) {
        if (Platform.OS === "web") {
          window.alert(result.error);
        } else {
          Alert.alert("Sign out failed", result.error);
        }
        return;
      }

      router.replace("/");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View className="flex-1 items-center justify-center bg-ibda-background px-6">
      <Text className="text-3xl font-bold text-ibda-charcoal">
        Welcome to Ibda
      </Text>

      <Text className="mt-3 text-center text-base leading-6 text-ibda-brown">
        You're signed in as {session?.user.email ?? "an Ibda user"}.
        {"\n"}Let's set up your brand.
      </Text>

      <Pressable
        onPress={() => router.push("/brand-setup")}
        className="mt-7 min-h-14 w-full items-center justify-center rounded-full bg-ibda-coral"
      >
        <Text className="font-bold text-white">Set up my brand</Text>
      </Pressable>

      <Pressable
        onPress={handleSignOut}
        disabled={loading}
        className="mt-4 rounded-full px-6 py-3"
      >
        <Text className="font-semibold text-ibda-brown">
          {loading ? "Signing out..." : "Sign out"}
        </Text>
      </Pressable>
    </View>
  );
}