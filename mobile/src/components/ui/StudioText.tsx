import { forwardRef, type ComponentRef } from "react";
import { StyleSheet, Text, type TextProps, type TextStyle } from "react-native";
import { useStudioFont } from "./StudioFonts";

const typography = {
  display: { fontSize: 24, lineHeight: 32, fontWeight: "600", letterSpacing: -0.5 },
  page: { fontSize: 22, lineHeight: 30, fontWeight: "600", letterSpacing: -0.4 },
  section: { fontSize: 16, lineHeight: 23, fontWeight: "600", letterSpacing: -0.2 },
  cardTitle: { fontSize: 15, lineHeight: 22, fontWeight: "600", letterSpacing: -0.2 },
  controlTitle: { fontSize: 14, lineHeight: 21, fontWeight: "600" },
  body: { fontSize: 14, lineHeight: 21, fontWeight: "400" },
  label: { fontSize: 13, lineHeight: 20, fontWeight: "600" },
  caption: { fontSize: 12, lineHeight: 18, fontWeight: "500" },
  eyebrow: { fontSize: 11, lineHeight: 17, fontWeight: "700", letterSpacing: 1.8 },
  button: { fontSize: 14, lineHeight: 21, fontWeight: "600", letterSpacing: 0.1 },
  metric: { fontSize: 20, lineHeight: 28, fontWeight: "600", letterSpacing: -0.4, fontVariant: ["tabular-nums"] },
} satisfies Record<string, TextStyle>;

const tones = {
  charcoal: "#25221F", secondary: "#25221F", coral: "#C24A3C",
  olive: "#25221F", plum: "#25221F", mauve: "#25221F", white: "#FAF8F4",
};

type StudioTextProps = TextProps & {
  className?: string;
  variant?: keyof typeof typography;
  tone?: keyof typeof tones;
};

// A typographic skin only: text, selection, accessibility and callbacks pass through.
export const StudioText = forwardRef<ComponentRef<typeof Text>, StudioTextProps>(
  function StudioText({ variant, tone, style, ...props }, ref) {
    const base = StyleSheet.flatten([variant && typography[variant], style]);
    const classWeight = props.className?.includes("font-bold") ? "700"
      : props.className?.includes("font-semibold") ? "600"
        : props.className?.includes("font-medium") ? "500" : "400";
    const font = useStudioFont(base?.fontWeight ?? classWeight);
    return (
      <Text
        {...props}
        ref={ref}
        style={[variant && typography[variant], style, font, tone && { color: tones[tone] }]}
      />
    );
  },
);
