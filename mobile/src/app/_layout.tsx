import "../global.css";

import { Stack } from "expo-router";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider } from "../features/auth/providers/AuthProvider";
import { AuthGate } from "../features/auth/components/AuthGate";
import { StudioMotionProvider } from "../components/ui/StudioControls";

export default function RootLayout() {
  return (
    <StudioMotionProvider>
    <SafeAreaProvider>
      <AuthProvider>
        <AuthGate>
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: "#FAF8F4" },
              animation: "fade",
            }}
          />
        </AuthGate>
      </AuthProvider>
    </SafeAreaProvider>
    </StudioMotionProvider>
  );
}
