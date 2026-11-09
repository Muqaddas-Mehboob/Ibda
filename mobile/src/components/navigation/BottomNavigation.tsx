import { StudioPressable as Pressable, StudioHighlight } from "../ui/StudioControls";
import { StudioIcon } from "../ui/StudioIcon";

import { View, Text, StyleSheet } from "react-native";
import { usePathname, useRouter } from "expo-router";

const tabs = [
  { label: "Home", route: "/dashboard", icon: "home", ink: "#C24A3C", wash: "#F1E9DF" },
  { label: "Brand", route: "/brand-memory", icon: "brand", ink: "#4A523E", wash: "#E5EDE3" },
  { label: "Studio", route: "/content-studio", icon: "spark", ink: "#C24A3C", wash: "#F1E9DF" },
  { label: "Approvals", route: "/approvals", icon: "check", ink: "#C24A3C", wash: "#F1E9DF" },
  { label: "Calendar", route: "/calendar", icon: "calendar", ink: "#292724", wash: "#F7EACF" },
  { label: "Analytics", route: "/analytics", icon: "chart", ink: "#51445F", wash: "#EEE7F1" },
//   { label: "Profile", route: "/profile", icon: "○" },
] as const;

export function BottomNavigation() {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <View className="mx-3 mb-2 mt-2 flex-row rounded-[24px] border border-[#E9E2DA] bg-white p-1.5" style={styles.bar}>
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
            <StudioIcon name={tab.icon} size={22} color={active ? tab.ink : "#716A64"} />
            <Text
              numberOfLines={1}
              className={`text-[11px] ${
                active
                  ? "font-bold text-[#292724]"
                  : "text-[#716A64]"
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
    shadowColor: "#292724",
    shadowOpacity: 0.07,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
});
