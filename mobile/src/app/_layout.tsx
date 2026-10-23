import "../global.css";

import { Stack } from "expo-router";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider } from "../features/auth/providers/AuthProvider";
import { AuthGate } from "../features/auth/components/AuthGate";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AuthGate>
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: "#FCF9F4" },
              animation: "fade",
            }}
          />
        </AuthGate>
      </AuthProvider>
    </SafeAreaProvider>
  );
}