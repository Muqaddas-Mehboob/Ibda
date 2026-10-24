
import { View, Text, Pressable } from "react-native";
import { usePathname, useRouter } from "expo-router";

const tabs = [
  { label: "Home", route: "/dashboard", icon: "⌂" },
  { label: "Brand", route: "/brand-memory", icon: "◇" },
  { label: "Studio", route: "/content-studio", icon: "✦" },
  { label: "Approvals", route: "/approvals", icon: "✓" },
  { label: "Calendar", route: "/calendar", icon: "▦" },
  { label: "Analytics", route: "/analytics", icon: "↗" },
//   { label: "Profile", route: "/profile", icon: "○" },
] as const;

export function BottomNavigation() {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <View className="flex-row border-t border-[#EAE4DC] bg-white px-1 pb-2 pt-3">
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
            className="flex-1 items-center justify-center gap-1 py-1"
          >
            <Text
              className={`text-xl ${
                active ? "text-[#FF6B5F]" : "text-[#827970]"
              }`}
            >
              {tab.icon}
            </Text>
            <Text
              numberOfLines={1}
              className={`text-[10px] ${
                active
                  ? "font-bold text-[#24221F]"
                  : "text-[#827970]"
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
