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
  surface: "#FAF8F4",
  text: "#25221F",
  muted: "#25221F",
  border: "#E2D9CF",
  coral: "#C24A3C",
  green: "#25221F",
  greenLight: "#F4F0EA",
  peach: "#F4F0EA",
  lavender: "#F4F0EA",
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
      <Text className="text-[14px] font-bold" style={{ color: COLORS.text }} variant="section">
        {title}
      </Text>
      {action ? (
        <Pressable onPress={onAction} hitSlop={8}>
          <Text className="text-[14px] leading-[22px] font-semibold" style={{ color: COLORS.coral }} variant="button">
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
 <View className="min-w-0 flex-1 items-center px-2 py-1">
  <View className="mb-3 h-8 w-8 items-center justify-center rounded-xl bg-[#9BAE9F]/20"><View style={{ opacity: 1 }}><StudioIcon name={icon} size={18} color="#4A523E" /></View></View>
  <Text variant="metric" numberOfLines={1} adjustsFontSizeToFit style={{ fontSize: 20, lineHeight: 28, textAlign: "center", color: "#4A523E" }}>{value}</Text>
  <Text variant="caption" className="mt-1 text-center" style={{ color: "#4A523E" }}>{label}</Text>
  <Text variant="caption" className="mt-2 text-center" style={{ color: "#4A523E" }}>{change}</Text>
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
   <View className="flex-row items-center justify-between px-6 pb-3 pt-3">
    <IbdaLogo size={40} />
    <View className="flex-row items-center gap-3">
     <Pressable onPress={() => router.push("/notifications")} className="relative h-11 w-11 items-center justify-center rounded-2xl border border-[#E2D9CF]/30 bg-[#E2D9CF]/20" style={{ backgroundColor: "#F4F0EA" }} accessibilityLabel="Notifications">
      <StudioIcon name="bell" size={21} color="#25221F" />
      {unreadNotificationCount > 0 ? (
       <View className="absolute -right-1 -top-1 min-h-5 min-w-5 items-center justify-center rounded-full bg-[#C24A3C] px-1"><Text variant="caption" tone="white" style={{ fontSize: 11, lineHeight: 16 }}>{unreadNotificationCount > 9 ? "9+" : unreadNotificationCount}</Text></View>
      ) : null}
     </Pressable>
     <Pressable onPress={() => router.push("/settings")} className="h-11 w-11 items-center justify-center rounded-2xl bg-[#F4F0EA]" accessibilityLabel="Profile"><StudioIcon name="user" color="#C24A3C" size={21} /></Pressable>
    </View>
   </View>
   <View className="w-full max-w-[900px] self-center px-6 pt-2">
    <View className="flex-row flex-wrap items-center justify-between gap-x-3 gap-y-1">
     <Text variant="page" tone="charcoal" style={{ fontSize: 22, lineHeight: 30 }}>{greeting},{" "}there</Text>
     <Text variant="caption" tone="secondary" className="ml-auto text-right">{dateLabel}</Text>
    </View>
    <Text variant="body" tone="secondary" className="mt-2">Your content is on track. Two posts are ready for your review today.</Text>
    <StudioCard className="mt-4 flex-row rounded-[24px] border border-[#E2D9CF]/30 bg-[#F4F0EA] p-3" style={{ backgroundColor: "#F4F0EA", borderColor: "#E2D9CF" }}>
     <MetricCard icon="reach" value="124.5k" label="Reach" change="+18.4%" />
     <MetricCard icon="chart" value="4.6%" label="Engagement" change="+1.2%" />
     <MetricCard icon="link" value="3,428" label="Link Clicks" change="+9.1%" />
    </StudioCard>
    <Text variant="caption" tone="secondary" className="mt-3">Sample metrics — connect analytics to show your live data.</Text>
    <StudioCard className="mt-5 rounded-[24px] bg-[#F4F0EA] p-5" style={{ backgroundColor: "#F4F0EA" }}>
     <View className="mb-4 flex-row items-center gap-3">
      <View className="h-9 w-9 items-center justify-center rounded-2xl bg-[#9BAE9F]/20"><StudioIcon name="wand" color="#4A523E" size={19} /></View>
      <View className="flex-1"><Text variant="eyebrow" tone="coral">CONTENT STUDIO</Text><Text variant="page" tone="charcoal" style={{ fontSize: 18, lineHeight: 26 }}>Create with AI</Text></View>
     </View>
     <Text variant="body" tone="secondary" className="mb-4">Create with your brand voice. Start with a simple idea.</Text>
     <TextInput value={prompt} onChangeText={setPrompt} placeholder="Prompt idea (e.g. Design tips...)" placeholderTextColor="#25221F" className="rounded-[18px]" style={{ backgroundColor: "#FAF8F4" }} returnKeyType="done" accessibilityLabel="Content idea prompt" />
     <Pressable onPress={handleGenerate} className="mt-3 min-h-[48px] flex-row items-center justify-center gap-2 rounded-[18px] bg-[#C24A3C] active:bg-[#A63F32] px-5"><StudioIcon name="spark" color="#FAF8F4" size={18} /><Text variant="button" tone="white">Generate</Text><StudioIcon name="arrow" color="#FAF8F4" size={18} /></Pressable>
    </StudioCard>
    <View className="mb-2 mt-5">
     <SectionTitle title="Content Rhythm" action="This Week  ›" onAction={() => router.push("/calendar")} />
     <StudioCard className="flex-row justify-between rounded-[24px] border border-[#F4F0EA] bg-[#F4F0EA] p-3" style={{ backgroundColor: "#F4F0EA", borderColor: "#F4F0EA" }}>
      {weekDays.map((day, index) => {
       const selected = activeDay === day.weekday;
       const hasContent = [1, 2, 3, 4].includes(index);
       return (
        <Pressable key={`${day.date}-${index}`} onPress={() => setActiveDay(day.weekday)} className="min-w-0 flex-1 items-center rounded-[16px] py-3" style={{ backgroundColor: selected ? "#C24A3C" : "transparent", transform: [{ scale: selected ? 1.02 : 1 }] }}>
         <Text variant="caption" style={{ color: selected ? "#FAF8F4" : COLORS.muted }}>{day.day}</Text>
         <Text variant="cardTitle" className="mt-2" style={{ color: selected ? "#FAF8F4" : COLORS.text }}>{day.date}</Text>
         <View className="mt-2 h-1.5 w-1.5 rounded-full" style={{ backgroundColor: hasContent ? selected ? "#F4F0EA" : "#25221F" : selected ? "#F4F0EA" : "#E2D9CF" }} />
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
