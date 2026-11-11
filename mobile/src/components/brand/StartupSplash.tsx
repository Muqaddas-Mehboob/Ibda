import { ActivityIndicator, StyleSheet, View } from "react-native";
import { IbdaLogo } from "./IbdaLogo";
import { StudioText } from "../ui/StudioText";

// Presentation only; the existing auth gate decides when this is displayed.
export function StartupSplash() {
  return (
    <View style={styles.screen}>
      <View style={styles.content}>
        <View style={styles.logoFrame}><IbdaLogo size={72} wordmark={false} /></View>
        <StudioText variant="display" tone="charcoal" style={styles.wordmark}>ibda<StudioText tone="coral">.</StudioText></StudioText>
        <View style={styles.loading} accessibilityRole="progressbar" accessibilityLabel="Loading your workspace" accessibilityState={{ busy: true }}>
          <ActivityIndicator size="small" color="#C24A3C" />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#FAF8F4", padding: 24, overflow: "hidden" },
  content: { width: "100%", maxWidth: 360, alignItems: "center" },
  logoFrame: { marginBottom: 16 },
  wordmark: { fontSize: 28, lineHeight: 36, letterSpacing: -1 },
  loading: { marginTop: 24 },
});
