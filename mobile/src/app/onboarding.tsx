import { StudioText as Text } from "../components/ui/StudioText";
import { StudioPressable as Pressable } from "../components/ui/StudioControls";
import { router } from "expo-router";
import { Alert, Platform, View } from "react-native";
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
    <View className="flex-1 items-center justify-center bg-[#FAF8F4] px-6">
      <Text className="text-[30px] leading-[37px] tracking-[-0.6px] font-bold text-[#292724]" variant="metric">
        Welcome to Ibda
      </Text>

      <Text className="mt-3 text-center text-base leading-6 text-[#716A64]" variant="body">
        You're signed in as {session?.user.email ?? "an Ibda user"}.
        {"\n"}Let's set up your brand.
      </Text>

      <Pressable
        onPress={() => router.push("/brand-setup")}
        className="mt-7 min-h-[54px] w-full items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32]"
      >
        <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">Set up my brand</Text>
      </Pressable>

      <Pressable
        onPress={handleSignOut}
        disabled={loading}
        className="mt-4 rounded-2xl px-6 py-3"
      >
        <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="button">
          {loading ? "Signing out..." : "Sign out"}
        </Text>
      </Pressable>
    </View>
  );
}