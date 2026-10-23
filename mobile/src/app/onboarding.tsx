import { router } from "expo-router";
import { Pressable, Text, View } from "react-native";

export default function OnboardingRoute() {
  return (
    <View className="flex-1 items-center justify-center bg-ibda-background px-6">
      <Text className="text-3xl font-bold text-ibda-charcoal">
        Welcome to Ibda
      </Text>

      <Text className="mt-3 text-center text-base leading-6 text-ibda-brown">
        Your account is signed in. Let's set up your brand.
      </Text>

      <Pressable
        onPress={() => router.replace("/")}
        className="mt-7 rounded-full bg-ibda-coral px-8 py-4"
      >
        <Text className="font-bold text-white">Continue</Text>
      </Pressable>
    </View>
  );
}