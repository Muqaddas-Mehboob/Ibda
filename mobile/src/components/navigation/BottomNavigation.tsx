import { StudioPressable as Pressable, StudioHighlight } from "../ui/StudioControls";
import { StudioIcon } from "../ui/StudioIcon";

import { View, StyleSheet } from "react-native";
import { StudioText as Text } from "../ui/StudioText";
import { usePathname, useRouter } from "expo-router";

const tabs = [
  { label: "Home", route: "/dashboard", icon: "home", ink: "#C24A3C", wash: "#F4F0EA" },
  { label: "Brand", route: "/brand-memory", icon: "brand", ink: "#C24A3C", wash: "#F4F0EA" },
  { label: "Studio", route: "/content-studio", icon: "spark", ink: "#C24A3C", wash: "#F4F0EA" },
  { label: "Approvals", route: "/approvals", icon: "check", ink: "#C24A3C", wash: "#F4F0EA" },
  { label: "Calendar", route: "/calendar", icon: "calendar", ink: "#C24A3C", wash: "#F4F0EA" },
  { label: "Analytics", route: "/analytics", icon: "chart", ink: "#C24A3C", wash: "#F4F0EA" },
//   { label: "Profile", route: "/profile", icon: "○" },
] as const;

export function BottomNavigation() {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <View className="mx-3 mb-2 mt-2 flex-row rounded-[24px] border border-[#E2D9CF] bg-[#FAF8F4] p-1.5" style={styles.bar}>
      {tabs.map((tab) => {
        const active =
          pathname === tab.route ||
          ((tab.route === "/brand-memory" ||
            tab.route === "/content-studio" ||
            tab.route === "/approvals") &&
            pathname.startsWith(`${tab.route}/`));

        return (
          <Pressable
            key={tab.route}
            accessibilityRole="button"
            accessibilityLabel={tab.label}
            onPress={() => router.navigate(tab.route as never)}
            className="relative min-h-[60px] flex-1 items-center justify-center gap-1 rounded-[18px] py-2"
          >
            <StudioHighlight selected={active} color={tab.wash} />
            <StudioIcon name={tab.icon} size={22} color={active ? tab.ink : "#25221F"} />
            <Text
              numberOfLines={1}
              className={`text-[11px] ${
                active
                  ? "font-bold text-[#C24A3C]"
                  : "text-[#25221F]"
              }`}
            >
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    shadowColor: "#25221F",
    shadowOpacity: 0.07,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
});
