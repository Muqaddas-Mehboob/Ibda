import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type AppNotification,
  type NotificationListResponse,
} from "../services/notification.service";

function dateGroup(value: string): string {
  const createdAt = new Date(value);
  if (Number.isNaN(createdAt.getTime())) return "Earlier";

  const today = new Date();
  const day = new Date(
    createdAt.getFullYear(),
    createdAt.getMonth(),
    createdAt.getDate()
  );
  const todayStart = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate()
  );
  const dayDifference = Math.round(
    (todayStart.getTime() - day.getTime()) / (24 * 60 * 60 * 1000)
  );

  if (dayDifference === 0) return "Today";
  if (dayDifference === 1) return "Yesterday";
  if (dayDifference > 1 && dayDifference < 7) {
    return day.toLocaleDateString(undefined, { weekday: "long" });
  }
  return day.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: day.getFullYear() === today.getFullYear() ? undefined : "numeric",
  });
}

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "Time unavailable";

  const seconds = Math.round((timestamp - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, {
    numeric: "auto",
  });
  if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(hours / 24), "day");
}

function groupedNotifications(notifications: AppNotification[]) {
  const groups = new Map<string, AppNotification[]>();
  for (const notification of notifications) {
    const group = dateGroup(notification.created_at);
    const current = groups.get(group) ?? [];
    current.push(notification);
    groups.set(group, current);
  }
  return Array.from(groups.entries());
}

export function NotificationsScreen() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [processingAll, setProcessingAll] = useState(false);
  const [processingId, setProcessingId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const response: NotificationListResponse = await getNotifications();
      setNotifications(response.results);
      setUnreadCount(response.unread_count);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load notifications."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const groups = useMemo(
    () => groupedNotifications(notifications),
    [notifications]
  );

  const markAllRead = async () => {
    if (processingAll || unreadCount === 0) return;
    setProcessingAll(true);
    setError("");
    try {
      await markAllNotificationsRead();
      const readAt = new Date().toISOString();
      setNotifications((current) =>
        current.map((item) =>
          item.is_read ? item : { ...item, is_read: true, read_at: readAt }
        )
      );
      setUnreadCount(0);
    } catch (markError) {
      setError(
        markError instanceof Error
          ? markError.message
          : "Unable to mark notifications as read."
      );
    } finally {
      setProcessingAll(false);
    }
  };

  const openNotification = async (notification: AppNotification) => {
    setError("");
    if (!notification.is_read) {
      setProcessingId(notification.id);
      try {
        const updated = await markNotificationRead(notification.id);
        setNotifications((current) =>
          current.map((item) => (item.id === updated.id ? updated : item))
        );
        setUnreadCount((count) => Math.max(0, count - 1));
      } catch (markError) {
        setError(
          markError instanceof Error
            ? markError.message
            : "Unable to mark this notification as read."
        );
        setProcessingId("");
        return;
      }
      setProcessingId("");
    }

    if (notification.destination === "approval") {
      if (notification.related_object_id) {
        router.push({
          pathname: "/approvals/[approvalId]",
          params: { approvalId: notification.related_object_id },
        });
      } else {
        router.push("/approvals");
      }
    } else if (notification.destination === "calendar") {
      router.push("/calendar");
    }
  };

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#C24A3C"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <Pressable
        onPress={() =>
          router.canGoBack() ? router.back() : router.replace("/dashboard")
        }
        accessibilityRole="button"
        accessibilityLabel="Go back"
        className="mb-8 h-11 w-11 items-center justify-center rounded-full border border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
      >
        <Text className="text-xl text-[#716A64]">‹</Text>
      </Pressable>
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="secondary">
          YOUR WORKSPACE
        </Text>
        <View className="mb-2 flex-row items-center justify-between">
          <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
            Notifications
          </Text>
          {unreadCount > 0 && (
            <Pressable
              onPress={() => void markAllRead()}
              disabled={processingAll}
              accessibilityRole="button"
              className="min-h-[54px] justify-center px-2 rounded-[18px]"
            >
              <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="button">
                {processingAll ? "Updating..." : "Mark all read"}
              </Text>
            </Pressable>
          )}
        </View>
        <Text className="mb-6 text-base leading-6 text-[#716A64]" variant="body">
          Stay up to date on decisions and activity across your content.
        </Text>

        {error && notifications.length > 0 ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text className="text-[#A33D34] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => void load(true)}
              accessibilityRole="button"
              className="mt-3 min-h-[54px] self-start justify-center px-2 rounded-[18px]"
            >
              <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </View>
        ) : null}

        {loading ? (
          <View className="items-center py-16">
            <ActivityIndicator size="large" color="#C24A3C" />
            <Text className="mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Loading notifications...
            </Text>
          </View>
        ) : error && notifications.length === 0 ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn’t load notifications
            </Text>
            <Text className="mt-2 text-[#A33D34] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-[54px] self-start justify-center rounded-[18px] bg-[#292724] px-4"
            >
              <Text className="font-semibold text-white text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </StudioCard>
        ) : notifications.length === 0 ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <View className="mb-4 h-12 w-12 items-center justify-center rounded-2xl bg-[#F1E9DF]">
              <Text className="text-xl">♧</Text>
            </View>
            <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
              You’re all caught up
            </Text>
            <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Updates about your approval decisions will appear here.
            </Text>
          </StudioCard>
        ) : (
          <View className="gap-6">
            {groups.map(([groupName, items]) => (
              <View key={groupName}>
                <Text className="mb-3 text-[15px] leading-[24px] font-bold uppercase tracking-wide text-[#716A64]" variant="eyebrow" tone="secondary">
                  {groupName}
                </Text>
                <View className="overflow-hidden rounded-3xl border border-[#E9E2DA] bg-white">
                  {items.map((notification, index) => (
                    <Pressable
                      key={notification.id}
                      onPress={() => void openNotification(notification)}
                      disabled={processingId === notification.id}
                      accessibilityRole="button"
                      accessibilityLabel={`${notification.is_read ? "" : "Unread. "}${notification.title}. ${notification.message}. ${relativeTime(notification.created_at)}`}
                      className={`min-h-[88px] flex-row items-center gap-3 px-4 py-4 ${
                        index > 0 ? "border-t border-[#E9E2DA]" : ""
                      } ${notification.is_read ? "" : "bg-[#FFFCF8]"}`}
                    >
                      <View className="h-10 w-10 items-center justify-center rounded-2xl bg-[#F1E9DF]">
                        <Text className="text-lg text-[#C24A3C]">
                          {notification.notification_type ===
                          "approval_approved"
                            ? "✓"
                            : notification.notification_type ===
                                "approval_rejected"
                              ? "!"
                              : "▦"}
                        </Text>
                      </View>
                      <View className="flex-1">
                        <Text className="font-bold text-[#292724] text-[15px] leading-[24px]" variant="controlTitle">
                          {notification.title}
                        </Text>
                        <Text className="mt-1 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                          {notification.message}
                        </Text>
                        <Text className="mt-2 text-[12px] text-[#9B9188]" variant="caption">
                          {relativeTime(notification.created_at)}
                        </Text>
                      </View>
                      {processingId === notification.id ? (
                        <ActivityIndicator size="small" color="#C24A3C" />
                      ) : !notification.is_read ? (
                        <View
                          accessibilityLabel="Unread"
                          className="h-2.5 w-2.5 rounded-full bg-[#C24A3C]"
                        />
                      ) : null}
                    </Pressable>
                  ))}
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
