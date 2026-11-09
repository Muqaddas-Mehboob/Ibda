import { StudioIcon, type StudioIconName } from "../../../components/ui/StudioIcon";
import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput, StudioCard } from "../../../components/ui/StudioControls";
import { IbdaLogo } from "../../../components/brand/IbdaLogo";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { useCallback, useMemo, useState } from "react";
import { Alert, ScrollView, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { getUnreadNotificationCount } from "../../notifications/services/notification.service";

const COLORS = {
  background: "#FAF8F4",
  surface: "#FFFFFF",
  text: "#292724",
  muted: "#716A64",
  border: "#E9E2DA",
  coral: "#C24A3C",
  green: "#009B72",
  greenLight: "#E9F9F2",
  peach: "#F1E9DF",
  lavender: "#F1E9DF",
};

function SectionTitle({
  title,
  action,
  onAction,
}: {
  title: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <View className="mb-3 flex-row items-center justify-between">
      <Text className="text-[20px] font-bold" style={{ color: COLORS.text }} variant="section">
        {title}
      </Text>
      {action ? (
        <Pressable onPress={onAction} hitSlop={8}>
          <Text className="text-[15px] leading-[24px] font-semibold" style={{ color: COLORS.coral }} variant="button">
            {action}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function MetricCard({
  icon,
  value,
  label,
  change,
}: {
  icon: StudioIconName;
  value: string;
  label: string;
  change: string;
}) {
  return (
 <View className="min-w-0 flex-1 px-2 py-1">
  <View className="mb-3 h-8 w-8 items-center justify-center rounded-xl bg-[#E5EDE3]"><StudioIcon name={icon} size={18} color="#4A523E" /></View>
  <Text variant="metric" numberOfLines={1} adjustsFontSizeToFit style={{ fontSize: 23, lineHeight: 30, color: COLORS.text }}>{value}</Text>
  <Text variant="caption" className="mt-1" tone="secondary">{label}</Text>
  <Text variant="caption" className="mt-2" tone="olive">{change}</Text>
 </View>
);
}



export default function DashboardScreen() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [activeDay, setActiveDay] = useState(new Date().getDay());
  const [approvedPosts, setApprovedPosts] = useState<string[]>(["1"]);
  const [unreadNotificationCount, setUnreadNotificationCount] = useState(0);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      getUnreadNotificationCount()
        .then((count) => {
          if (active) setUnreadNotificationCount(count);
        })
        .catch((error: unknown) => {
          if (active) {
            Alert.alert(
              "Notifications unavailable",
              error instanceof Error
                ? error.message
                : "Unable to load notification count."
            );
          }
        });

      return () => {
        active = false;
      };
    }, [])
  );

  const today = new Date();

  const greeting = useMemo(() => {
    const hour = today.getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }, []);

  const dateLabel = today
    .toLocaleDateString("en-US", {
      weekday: "long",
      month: "short",
      day: "numeric",
    })
    .toUpperCase();

  const weekDays = useMemo(() => {
    const start = new Date(today);
    start.setDate(today.getDate() - today.getDay() + 1);

    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      return {
        day: date.toLocaleDateString("en-US", { weekday: "short" }).charAt(0),
        date: date.getDate(),
        weekday: date.getDay(),
      };
    });
  }, []);

  const showComingSoon = (feature: string) => {
    Alert.alert(feature, "This section will be connected as we build the next screens.");
  };

  const handleGenerate = () => {
    if (!prompt.trim()) {
      Alert.alert(
        "What's your idea?",
        "Enter a topic or content idea first."
      );
      return;
    }

    router.push({
      pathname: "/content-studio",
      params: { topic: prompt.trim() },
    });
  };

  return (
 <View className="flex-1" style={{ backgroundColor: COLORS.background }}>
  <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 32 }} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
   <View className="flex-row items-center justify-between px-6 pb-3 pt-6">
    <IbdaLogo size={40} />
    <View className="flex-row items-center gap-3">
     <Pressable onPress={() => router.push("/notifications")} className="relative h-11 w-11 items-center justify-center rounded-2xl border border-[#E9E2DA] bg-white" accessibilityLabel="Notifications">
      <StudioIcon name="bell" size={21} color="#51445F" />
      {unreadNotificationCount > 0 ? (
       <View className="absolute -right-1 -top-1 min-h-5 min-w-5 items-center justify-center rounded-full bg-[#C24A3C] px-1"><Text variant="caption" tone="white" style={{ fontSize: 11, lineHeight: 16 }}>{unreadNotificationCount > 9 ? "9+" : unreadNotificationCount}</Text></View>
      ) : null}
     </Pressable>
     <Pressable onPress={() => router.push("/settings")} className="h-11 w-11 items-center justify-center rounded-2xl bg-[#E5EDE3]" accessibilityLabel="Profile"><StudioIcon name="user" color="#4A523E" size={21} /></Pressable>
    </View>
   </View>
   <View className="w-full max-w-[900px] self-center px-6 pt-5">
    <Text variant="eyebrow" tone="secondary">{dateLabel}</Text>
    <Text variant="display" tone="charcoal" className="mt-3">{greeting},{" "}there</Text>
    <Text variant="body" tone="secondary" className="mt-3">Your content is on track. Two posts are ready for your review today.</Text>
    <StudioCard className="mt-6 flex-row rounded-[24px] border border-[#E9E2DA] bg-white p-3">
     <MetricCard icon="reach" value="124.5k" label="Reach" change="+18.4%" />
     <MetricCard icon="chart" value="4.6%" label="Engagement" change="+1.2%" />
     <MetricCard icon="link" value="3,428" label="Link Clicks" change="+9.1%" />
    </StudioCard>
    <Text variant="caption" tone="secondary" className="mt-3">Sample metrics — connect analytics to show your live data.</Text>
    <StudioCard className="mt-7 rounded-[24px] bg-[#F1E9DF] p-5">
     <View className="mb-4 flex-row items-center gap-3">
      <View className="h-11 w-11 items-center justify-center rounded-2xl bg-white"><StudioIcon name="spark" color="#C24A3C" size={23} /></View>
      <View className="flex-1"><Text variant="eyebrow" tone="coral">CONTENT STUDIO</Text><Text variant="page" tone="charcoal" style={{ fontSize: 27, lineHeight: 35 }}>Create with AI</Text></View>
     </View>
     <Text variant="body" tone="secondary" className="mb-4">Create with your brand voice. Start with a simple idea.</Text>
     <TextInput value={prompt} onChangeText={setPrompt} placeholder="Prompt idea (e.g. Design tips...)" placeholderTextColor="#716A64" className="rounded-[18px]" style={{ backgroundColor: "#FFFFFF" }} returnKeyType="done" accessibilityLabel="Content idea prompt" />
     <Pressable onPress={handleGenerate} className="mt-3 min-h-[54px] flex-row items-center justify-center gap-2 rounded-[18px] bg-[#C24A3C] active:bg-[#A63F32] px-5"><StudioIcon name="spark" color="#FFFFFF" size={18} /><Text variant="button" tone="white">Generate</Text><StudioIcon name="arrow" color="#FFFFFF" size={18} /></Pressable>
    </StudioCard>
    <View className="mb-2 mt-7">
     <SectionTitle title="Content Rhythm" action="This Week  ›" onAction={() => router.push("/calendar")} />
     <StudioCard className="flex-row justify-between rounded-[24px] border border-[#E9E2DA] bg-white p-3">
      {weekDays.map((day, index) => {
       const selected = activeDay === day.weekday;
       const hasContent = [1, 2, 3, 4].includes(index);
       return (
        <Pressable key={`${day.date}-${index}`} onPress={() => setActiveDay(day.weekday)} className="min-w-0 flex-1 items-center rounded-[16px] py-3" style={{ backgroundColor: selected ? "#F7EACF" : "transparent", transform: [{ scale: selected ? 1.02 : 1 }] }}>
         <Text variant="caption" style={{ color: selected ? "#292724" : COLORS.muted }}>{day.day}</Text>
         <Text variant="cardTitle" className="mt-2" style={{ color: selected ? "#292724" : COLORS.text }}>{day.date}</Text>
         <View className="mt-2 h-1.5 w-1.5 rounded-full" style={{ backgroundColor: hasContent ? selected ? "#D69B48" : "#D69B48" : selected ? "#D69B48" : "#E9E2DA" }} />
        </Pressable>
       );
      })}
     </StudioCard>
    </View>
   </View>
  </ScrollView>
  <BottomNavigation />
 </View>
);
}
