import { forwardRef, type ComponentRef } from "react";
import { Platform, Text, type TextProps, type TextStyle } from "react-native";

const sans = Platform.select({ ios: "System", android: "sans-serif", default: "system-ui" });
const serif = Platform.select({ ios: "Georgia", android: "serif", default: "Georgia, serif" });

const typography = {
  display: { fontFamily: serif, fontSize: 35, lineHeight: 43, fontWeight: "400", letterSpacing: -0.9 },
  page: { fontFamily: serif, fontSize: 32, lineHeight: 40, fontWeight: "400", letterSpacing: -0.6 },
  section: { fontSize: 21, lineHeight: 28, fontWeight: "600", letterSpacing: -0.4 },
  cardTitle: { fontSize: 18, lineHeight: 25, fontWeight: "600", letterSpacing: -0.2 },
  controlTitle: { fontSize: 16, lineHeight: 23, fontWeight: "600" },
  body: { fontSize: 15, lineHeight: 23 },
  label: { fontSize: 14, lineHeight: 21, fontWeight: "600" },
  caption: { fontSize: 12, lineHeight: 18, fontWeight: "500" },
  eyebrow: { fontSize: 11, lineHeight: 17, fontWeight: "700", letterSpacing: 1.8 },
  button: { fontSize: 15, lineHeight: 22, fontWeight: "600", letterSpacing: 0.1 },
  metric: { fontSize: 28, lineHeight: 35, fontWeight: "600", letterSpacing: -0.7, fontVariant: ["tabular-nums"] },
} satisfies Record<string, TextStyle>;

const tones = {
  charcoal: "#292724", secondary: "#716A64", coral: "#C24A3C",
  olive: "#4A523E", plum: "#51445F", mauve: "#826C8B", white: "#FFFFFF",
};

type StudioTextProps = TextProps & {
  className?: string;
  variant?: keyof typeof typography;
  tone?: keyof typeof tones;
};

// A typographic skin only: text, selection, accessibility and callbacks pass through.
export const StudioText = forwardRef<ComponentRef<typeof Text>, StudioTextProps>(
  function StudioText({ variant, tone, style, ...props }, ref) {
    return (
      <Text
        {...props}
        ref={ref}
        style={[{ fontFamily: sans }, variant && typography[variant], style, tone && { color: tones[tone] }]}
      />
    );
  },
);
