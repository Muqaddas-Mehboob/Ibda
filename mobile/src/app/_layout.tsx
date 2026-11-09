import "../global.css";

import { Stack } from "expo-router";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { AuthProvider } from "../features/auth/providers/AuthProvider";
import { AuthGate } from "../features/auth/components/AuthGate";
import { StudioMotionProvider } from "../components/ui/StudioControls";
import { StudioFonts } from "../components/ui/StudioFonts";

export default function RootLayout() {
  return (
    <StudioMotionProvider>
      <SafeAreaProvider>
        <SafeAreaView
          edges={["top", "right", "bottom", "left"]}
          style={{ flex: 1, backgroundColor: "#FAF8F4" }}
        >
          <StudioFonts>
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
          </StudioFonts>
        </SafeAreaView>
      </SafeAreaProvider>
    </StudioMotionProvider>
  );
}
