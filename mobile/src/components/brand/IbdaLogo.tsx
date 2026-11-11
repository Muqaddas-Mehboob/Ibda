import { Image } from "expo-image";
import { StyleSheet, View } from "react-native";
import { StudioText as Text } from "../ui/StudioText";

export function IbdaLogo({
  size = 44,
  wordmark = true,
}: {
  size?: number;
  wordmark?: boolean;
}) {
  return (
    <View accessible accessibilityLabel="Ibda creative studio" style={styles.lockup}>
      <Image
        source={require("../../../assets/images/ibda-mark.svg")}
        contentFit="contain"
        style={{ width: size, height: size }}
        accessible={false}
      />
      {wordmark && (
        <Text style={[styles.wordmark, { fontSize: size * 0.5 }]}>ibda<Text style={styles.dot}>.</Text></Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  lockup: { flexDirection: "row", alignItems: "center", gap: 10, flexShrink: 0 },
  wordmark: { color: "#25221F", fontWeight: "700", letterSpacing: -1.1 },
  dot: { color: "#C24A3C" },
});
