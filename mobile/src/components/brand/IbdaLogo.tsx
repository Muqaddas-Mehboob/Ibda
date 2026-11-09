import { Image } from "expo-image";
import { StyleSheet, Text, View } from "react-native";

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
        <Text style={[styles.wordmark, { fontSize: size * 0.65 }]}>ibda<Text style={styles.dot}>.</Text></Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  lockup: { flexDirection: "row", alignItems: "center", gap: 10, flexShrink: 0 },
  wordmark: { color: "#292724", fontWeight: "700", letterSpacing: -1.1 },
  dot: { color: "#C24A3C" },
});
