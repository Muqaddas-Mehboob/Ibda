import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { useCallback, useMemo, useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { getUnreadNotificationCount } from "../../notifications/services/notification.service";

const COLORS = {
  background: "#FCF9F5",
  surface: "#FFFFFF",
  text: "#24221F",
  muted: "#766B64",
  border: "#E8E1DA",
  coral: "#FF6B5F",
  green: "#009B72",
  greenLight: "#E9F9F2",
  peach: "#FFF2E8",
  lavender: "#F0E7FA",
};

const POSTS = [
  {
    id: "1",
    platform: "INSTAGRAM",
    time: "2:15 PM",
    title: "Editorial Studio Walkthrough",
    type: "REEL",
    status: "Approved",
    approved: true,
    color: "#DCE8DD",
    artwork: "🏡",
  },
  {
    id: "2",
    platform: "LINKEDIN",
    time: "5:00 PM",
    title: "The Next Era of AI Publishing",
    type: "POST",
    status: "Approve",
    approved: false,
    color: "#E6E9FA",
    artwork: "✳️",
  },
];

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
      <Text className="text-[20px] font-bold" style={{ color: COLORS.text }}>
        {title}
      </Text>
      {action ? (
        <Pressable onPress={onAction} hitSlop={8}>
          <Text className="text-sm font-semibold" style={{ color: COLORS.coral }}>
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
  icon: string;
  value: string;
  label: string;
  change: string;
}) {
  return (
    <View
      className="min-w-0 flex-1 rounded-[22px] border p-3"
      style={{
        backgroundColor: COLORS.surface,
        borderColor: COLORS.border,
        shadowColor: "#000",
        shadowOpacity: 0.04,
        shadowRadius: 5,
        shadowOffset: { width: 0, height: 2 },
        elevation: 1,
      }}
    >
      <View className="mb-3 flex-row flex-wrap items-center justify-between gap-1">
        <View
          className="h-9 w-9 items-center justify-center rounded-2xl"
          style={{ backgroundColor: COLORS.peach }}
        >
          <Text className="text-lg" style={{ color: COLORS.coral }}>
            {icon}
          </Text>
        </View>
        <View
          className="rounded-lg px-1.5 py-1"
          style={{ backgroundColor: COLORS.greenLight }}
        >
          <Text className="text-[10px] font-bold" style={{ color: COLORS.green }}>
            {change}
          </Text>
        </View>
      </View>

      <Text
        className="text-[23px] font-extrabold"
        numberOfLines={1}
        adjustsFontSizeToFit
        style={{ color: COLORS.text }}
      >
        {value}
      </Text>
      <Text className="mt-1 text-[12px]" style={{ color: COLORS.muted }}>
        {label}
      </Text>
    </View>
  );
}

function ContentCard({
  post,
  onApprove,
}: {
  post: (typeof POSTS)[number];
  onApprove: () => void;
}) {
  return (
    <View
      className="mb-3 flex-row items-center rounded-[22px] border p-3"
      style={{
        backgroundColor: COLORS.surface,
        borderColor: COLORS.border,
        shadowColor: "#000",
        shadowOpacity: 0.035,
        shadowRadius: 4,
        shadowOffset: { width: 0, height: 2 },
        elevation: 1,
      }}
    >
      <View
        className="h-[78px] w-[78px] items-center justify-center rounded-[17px]"
        style={{ backgroundColor: post.color }}
      >
        <Text className="text-3xl">{post.artwork}</Text>
        <View className="mt-1 rounded-md bg-white/90 px-2 py-0.5">
          <Text className="text-[9px] font-bold" style={{ color: COLORS.text }}>
            {post.type}
          </Text>
        </View>
      </View>

      <View className="ml-3 min-w-0 flex-1">
        <View className="mb-2 flex-row flex-wrap items-center gap-1.5">
          <View
            className="rounded-full px-2 py-1"
            style={{
              backgroundColor:
                post.platform === "INSTAGRAM" ? "#F3ECE6" : "#EAF0FF",
            }}
          >
            <Text
              className="text-[9px] font-extrabold"
              style={{
                color: post.platform === "INSTAGRAM" ? "#74584D" : "#345CE5",
              }}
            >
              {post.platform}
            </Text>
          </View>
          <Text className="text-[11px]" style={{ color: COLORS.muted }}>
            {post.time}
          </Text>
        </View>

        <Text
          className="text-[14px] font-bold leading-5"
          numberOfLines={2}
          style={{ color: COLORS.text }}
        >
          {post.title}
        </Text>

        <Pressable
          onPress={onApprove}
          className="mt-2 self-start rounded-full px-3 py-2"
          style={{
            backgroundColor: post.approved ? COLORS.green : COLORS.coral,
          }}
        >
          <Text className="text-[11px] font-bold text-white">
            {post.approved ? "✓  Approved" : "✓  Approve"}
          </Text>
        </Pressable>
      </View>
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
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingBottom: 24 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View
          className="flex-row items-center justify-between border-b px-6 py-4"
          style={{ borderColor: COLORS.border }}
        >
          <View className="flex-row items-center">
            <Text
              className="text-[30px] font-black tracking-[-1.5px]"
              style={{ color: COLORS.text }}
            >
              ibda
            </Text>
            <View
              className="ml-2 h-3 w-3 rounded-full"
              style={{ backgroundColor: COLORS.coral }}
            />
          </View>

          <View className="flex-row items-center gap-4">
            <Pressable
              onPress={() => router.push("/notifications")}
              className="relative h-11 w-10 items-center justify-center"
              accessibilityLabel="Notifications"
            >
              <Text className="text-[27px]" style={{ color: COLORS.text }}>
                ♧
              </Text>
              {unreadNotificationCount > 0 ? (
                <View className="absolute -right-1 -top-1 min-h-5 min-w-5 items-center justify-center rounded-full bg-[#FF6B5F] px-1">
                  <Text className="text-[10px] font-bold text-white">
                    {unreadNotificationCount > 9
                      ? "9+"
                      : unreadNotificationCount}
                  </Text>
                </View>
              ) : null}
            </Pressable>

            <Pressable
              onPress={() => showComingSoon("Your profile")}
              className="h-12 w-12 items-center justify-center rounded-full border-2"
              style={{
                borderColor: "#F4B9AD",
                backgroundColor: "#EAD8C9",
              }}
              accessibilityLabel="Profile"
            >
              <Text className="text-xl">👤</Text>
            </Pressable>
          </View>
        </View>

        <View className="px-6 pt-6">
          {/* Greeting */}
          <Text
            className="text-[13px] font-bold tracking-[1.5px]"
            style={{ color: COLORS.muted }}
          >
            {dateLabel}
          </Text>

          <Text
            className="mt-4 text-[34px] font-extrabold leading-[40px]"
            style={{ color: COLORS.text }}
          >
            {greeting},{"\n"}there
          </Text>

          <Text
            className="mt-2 text-[17px] leading-6"
            style={{ color: "#5E4D45" }}
          >
            Your content is on track. Two posts are ready for your review today.
          </Text>

          {/* Analytics metrics */}
          <View className="mt-6 flex-row gap-3">
            <MetricCard
              icon="↗"
              value="124.5k"
              label="Reach"
              change="+18.4%"
            />
            <MetricCard
              icon="ϟ"
              value="4.6%"
              label="Engagement"
              change="+1.2%"
            />
            <MetricCard
              icon="◎"
              value="3,428"
              label="Link Clicks"
              change="+9.1%"
            />
          </View>

          <Text className="mt-2 text-[10px]" style={{ color: COLORS.muted }}>
            Sample metrics — connect analytics to show your live data.
          </Text>

          {/* Create with AI */}
          <View
            className="mt-6 rounded-[28px] border p-5"
            style={{
              backgroundColor: COLORS.surface,
              borderColor: COLORS.border,
              shadowColor: "#000",
              shadowOpacity: 0.04,
              shadowRadius: 5,
              shadowOffset: { width: 0, height: 2 },
              elevation: 1,
            }}
          >
            <View className="mb-4 flex-row items-center">
              <View
                className="mr-3 h-10 w-10 items-center justify-center rounded-2xl"
                style={{ backgroundColor: COLORS.peach }}
              >
                <Text className="text-2xl" style={{ color: COLORS.coral }}>
                  ✧
                </Text>
              </View>
              <Text
                className="text-[21px] font-bold"
                style={{ color: COLORS.text }}
              >
                Create with AI
              </Text>
            </View>

            <View
              className="rounded-[20px] border p-2"
              style={{
                borderColor: COLORS.border,
                backgroundColor: "#F5F2ED",
              }}
            >
              <TextInput
                value={prompt}
                onChangeText={setPrompt}
                placeholder="Prompt idea (e.g. Design tips...)"
                placeholderTextColor="#756D64"
                className="px-2 py-2 text-[15px]"
                style={{ color: COLORS.text }}
                returnKeyType="done"
                accessibilityLabel="Content idea prompt"
              />

              <Pressable
                onPress={handleGenerate}
                className="mt-2 min-h-12 flex-row items-center justify-center rounded-full px-4"
                style={{ backgroundColor: COLORS.coral }}
              >
                <Text className="mr-2 text-lg text-white">✧</Text>
                <Text className="text-[15px] font-bold text-white">
                  Generate
                </Text>
              </Pressable>
            </View>
          </View>

          {/* Content rhythm */}
          <View className="mt-8">
            <SectionTitle
              title="Content Rhythm"
              action="Week 42  ›"
              onAction={() => router.push("/calendar")}
            />

            <View
              className="flex-row justify-between rounded-[23px] border p-3"
              style={{
                backgroundColor: COLORS.surface,
                borderColor: COLORS.border,
                shadowColor: "#000",
                shadowOpacity: 0.035,
                shadowRadius: 4,
                shadowOffset: { width: 0, height: 2 },
                elevation: 1,
              }}
            >
              {weekDays.map((day, index) => {
                const selected = activeDay === day.weekday;
                const hasContent = [1, 2, 3, 4].includes(index);

                return (
                  <Pressable
                    key={`${day.date}-${index}`}
                    onPress={() => setActiveDay(day.weekday)}
                    className="min-w-0 flex-1 items-center rounded-[16px] py-3"
                    style={{
                      backgroundColor: selected ? COLORS.coral : "transparent",
                      transform: [{ scale: selected ? 1.02 : 1 }],
                    }}
                  >
                    <Text
                      className="text-[12px] font-semibold"
                      style={{
                        color: selected ? "#FFFFFF" : COLORS.muted,
                      }}
                    >
                      {day.day}
                    </Text>

                    <Text
                      className="mt-2 text-[17px] font-bold"
                      style={{
                        color: selected ? "#FFFFFF" : COLORS.text,
                      }}
                    >
                      {day.date}
                    </Text>

                    <View
                      className="mt-2 h-2 w-2 rounded-full"
                      style={{
                        backgroundColor: hasContent
                          ? selected
                            ? "#FFFFFF"
                            : COLORS.coral
                          : selected
                            ? "#FFFFFF"
                            : "#E5DED7",
                      }}
                    />
                  </Pressable>
                );
              })}
            </View>
          </View>

          {/* Attention section */}
          <View className="mt-8">
            <SectionTitle
              title="Needs your attention"
              action="View all  ›"
              onAction={() => showComingSoon("Approval inbox")}
            />

            <View className="mb-4 flex-row items-center">
              <View
                className="rounded-full px-3 py-1.5"
                style={{ backgroundColor: "#FFE0DA" }}
              >
                <Text
                  className="text-[12px] font-bold"
                  style={{ color: "#A94336" }}
                >
                  2 ready
                </Text>
              </View>
            </View>

            {POSTS.map((post) => (
              <ContentCard
                key={post.id}
                post={{
                  ...post,
                  approved: approvedPosts.includes(post.id),
                }}
                onApprove={() => {
                  if (approvedPosts.includes(post.id)) {
                    showComingSoon("Post details");
                    return;
                  }

                  Alert.alert(
                    "Approve this post?",
                    "This preview action updates the local UI only. Connect the approval API for a saved approval.",
                    [
                      { text: "Cancel", style: "cancel" },
                      {
                        text: "Approve",
                        onPress: () =>
                          setApprovedPosts((current) => [
                            ...current,
                            post.id,
                          ]),
                      },
                    ]
                  );
                }}
              />
            ))}
          </View>
        </View>
      </ScrollView>

      {/* Bottom navigation */}
      <View
        className="flex-row border-t px-1 pb-2 pt-2"
        style={{
          backgroundColor: COLORS.background,
          borderColor: COLORS.border,
        }}
      >
      </View>
      <BottomNavigation />
    </View>
  );
}
