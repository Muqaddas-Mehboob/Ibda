import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput, StudioCard } from "../../../components/ui/StudioControls";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Platform, RefreshControl, ScrollView, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  getContentPost,
  getContentPosts,
  type ContentPost,
} from "../../content-studio/services/content.service";
import {
  getConnectedAccounts,
  type SocialAccount,
} from "../../integrations/services/socialAccount.service";
import {
  cancelScheduledPost,
  getDeviceTimezone,
  getPublishingPlatforms,
  getScheduledPosts,
  parseLocalDateTimeInput,
  rescheduleScheduledPost,
  schedulePost,
  toLocalDateTimeInput,
  type PublishingCapability,
  type ScheduledPost,
  type ScheduledStatus,
} from "../services/calendar.service";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const STATUS_STYLES: Record<
  ScheduledStatus,
  { label: string; dot: string; badge: string; text: string }
> = {
  pending: {
    label: "Scheduled",
    dot: "bg-[#FF6B5F]",
    badge: "bg-[#FFF1EE]",
    text: "text-[#B04438]",
  },
  publishing: {
    label: "Publishing",
    dot: "bg-[#7B61FF]",
    badge: "bg-[#EFECFF]",
    text: "text-[#4B3AC0]",
  },
  published: {
    label: "Published",
    dot: "bg-[#2E8B57]",
    badge: "bg-[#E8F5EC]",
    text: "text-[#1F6B41]",
  },
  failed: {
    label: "Failed",
    dot: "bg-[#B02A1F]",
    badge: "bg-[#FCE5E1]",
    text: "text-[#A33D34]",
  },
  blocked: {
    label: "Not connected",
    dot: "bg-[#B8860B]",
    badge: "bg-[#FDF3DC]",
    text: "text-[#8A6412]",
  },
  cancelled: {
    label: "Cancelled",
    dot: "bg-[#B9AFA6]",
    badge: "bg-[#F3EEE8]",
    text: "text-[#827970]",
  },
};

function localDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function scheduledDateKey(value: string): string | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : localDateKey(date);
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function monthStart(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function weekStartOf(date: Date): Date {
  const day = startOfLocalDay(date);
  const offset = (day.getDay() + 6) % 7;
  return new Date(day.getFullYear(), day.getMonth(), day.getDate() - offset);
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function getMonthDays(date: Date): (Date | null)[] {
  const first = monthStart(date);
  const leadingDays = (first.getDay() + 6) % 7;
  const dayCount = new Date(
    date.getFullYear(),
    date.getMonth() + 1,
    0
  ).getDate();
  const cells: (Date | null)[] = Array.from(
    { length: leadingDays },
    () => null
  );

  for (let day = 1; day <= dayCount; day += 1) {
    cells.push(new Date(date.getFullYear(), date.getMonth(), day, 12));
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Time unavailable"
    : date.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      });
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
}

function formatDateTimeInZone(value: string, timeZoneName: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  const options: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  };
  try {
    return date.toLocaleString(
      undefined,
      timeZoneName ? { ...options, timeZone: timeZoneName } : options
    );
  } catch {
    return date.toLocaleString(undefined, options);
  }
}

function formatLongDate(value: Date): string {
  return value.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function platformLabel(platforms: PublishingCapability[], value: string) {
  return (
    platforms.find((platform) => platform.platform === value)?.label ??
    value.replaceAll("_", " ")
  );
}

async function confirmDestructive(title: string, message: string) {
  if (Platform.OS === "web") {
    return typeof window !== "undefined" && window.confirm(`${title}\n\n${message}`);
  }

  return new Promise<boolean>((resolve) => {
    Alert.alert(title, message, [
      { text: "Keep it", style: "cancel", onPress: () => resolve(false) },
      {
        text: "Confirm",
        style: "destructive",
        onPress: () => resolve(true),
      },
    ]);
  });
}

function Chip({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      className={`min-h-9 justify-center rounded-2xl border px-3 ${
        active
          ? "border-[#C24A3C] bg-[#C24A3C] active:bg-[#A63F32]"
          : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
      }`}
    >
      <Text
        className={`text-[12px] font-semibold ${
          active ? "text-white" : "text-[#716A64]"
        }`} variant="caption"
      >
        {label}
      </Text>
    </Pressable>
  );
}

type ViewMode = "month" | "week" | "list";

export function CalendarScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ postId?: string | string[] }>();
  const preselectedPostId =
    typeof params.postId === "string" ? params.postId : null;

  const [viewMode, setViewMode] = useState<ViewMode>("month");
  const [month, setMonth] = useState(() => monthStart(new Date()));
  const [selectedDate, setSelectedDate] = useState(() =>
    startOfLocalDay(new Date())
  );
  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [drafts, setDrafts] = useState<ContentPost[]>([]);
  const [platforms, setPlatforms] = useState<PublishingCapability[]>([]);
  const [facebookPages, setFacebookPages] = useState<SocialAccount[]>([]);
  const [instagramAccounts, setInstagramAccounts] = useState<SocialAccount[]>(
    []
  );
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  const [brandFilter, setBrandFilter] = useState<string>("all");
  const [platformFilter, setPlatformFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const [showScheduler, setShowScheduler] = useState(false);
  const [approvedPosts, setApprovedPosts] = useState<ContentPost[]>([]);
  const [schedulerPostId, setSchedulerPostId] = useState<string | null>(
    preselectedPostId
  );
  const [schedulerPlatforms, setSchedulerPlatforms] = useState<string[]>([]);
  const [schedulerAccountIds, setSchedulerAccountIds] = useState<
    Record<string, string>
  >({});
  const [schedulerInput, setSchedulerInput] = useState("");
  const [schedulerTimezone, setSchedulerTimezone] = useState(getDeviceTimezone);
  const [schedulerNotice, setSchedulerNotice] = useState("");
  const [savingSchedule, setSavingSchedule] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editInput, setEditInput] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  const visibleWeekStart = useMemo(() => weekStartOf(selectedDate), [selectedDate]);

  const rangeStart = useMemo(() => {
    const start = monthStart(month);
    return visibleWeekStart < start ? visibleWeekStart : start;
  }, [month, visibleWeekStart]);

  const rangeEnd = useMemo(() => {
    const monthEnd = new Date(month.getFullYear(), month.getMonth() + 1, 1);
    const weekEnd = addDays(visibleWeekStart, 7);
    const queueEnd = addDays(startOfLocalDay(new Date()), 90);
    return new Date(Math.max(monthEnd.getTime(), weekEnd.getTime(), queueEnd.getTime()));
  }, [month, visibleWeekStart]);

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError("");

      try {
        const [scheduled, capabilities, draftPosts, connected] =
          await Promise.all([
            getScheduledPosts(rangeStart, rangeEnd),
            getPublishingPlatforms(),
            getContentPosts("draft"),
            getConnectedAccounts(),
          ]);
        setPosts(scheduled);
        setFacebookPages(
          connected.accounts.filter(
            (account) =>
              account.platform === "facebook_pages" &&
              account.status === "connected"
          )
        );
        setInstagramAccounts(
          connected.accounts.filter(
            (account) =>
              account.platform === "instagram" &&
              account.status === "connected"
          )
        );
        setPlatforms(
          capabilities.platforms.map((item) => ({
            ...item,
            label: item.label || item.platform,
          }))
        );
        setDrafts(draftPosts);
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load scheduled posts."
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [rangeEnd, rangeStart]
  );

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const filteredPosts = useMemo(() => {
    return posts.filter((scheduled) => {
      if (brandFilter !== "all" && scheduled.post.brand_id !== brandFilter) {
        return false;
      }
      if (platformFilter !== "all" && scheduled.platform !== platformFilter) {
        return false;
      }
      if (statusFilter !== "all" && scheduled.status !== statusFilter) {
        return false;
      }
      return true;
    });
  }, [posts, brandFilter, platformFilter, statusFilter]);

  const postsByDate = useMemo(() => {
    const result = new Map<string, ScheduledPost[]>();
    for (const scheduled of filteredPosts) {
      const key = scheduledDateKey(scheduled.scheduled_for);
      if (!key) continue;
      const bucket = result.get(key) ?? [];
      bucket.push(scheduled);
      result.set(key, bucket);
    }
    return result;
  }, [filteredPosts]);

  const brandOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const scheduled of posts) {
      seen.set(scheduled.post.brand_id, scheduled.post.brand_name);
    }
    return Array.from(seen, ([id, name]) => ({ id, name }));
  }, [posts]);

  const platformOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const scheduled of posts) seen.add(scheduled.platform);
    return Array.from(seen);
  }, [posts]);

  const selectedPosts = postsByDate.get(localDateKey(selectedDate)) ?? [];
  const monthDays = useMemo(() => getMonthDays(month), [month]);
  const weekDays = useMemo(
    () => Array.from({ length: 7 }, (_, index) => addDays(visibleWeekStart, index)),
    [visibleWeekStart]
  );
  const anyPlatformAvailable = platforms.some((platform) => platform.available);

  const changePeriod = (offset: number) => {
    if (viewMode === "week") {
      const next = addDays(visibleWeekStart, offset * 7);
      setSelectedDate(next);
      setMonth(monthStart(next));
      return;
    }
    const next = new Date(month.getFullYear(), month.getMonth() + offset, 1);
    setMonth(next);
    setSelectedDate(startOfLocalDay(next));
  };

  const openScheduler = useCallback(async () => {
    setActionError("");
    setActionMessage("");
    setSchedulerNotice("");
    setSchedulerAccountIds({
      facebook: facebookPages[0]?.id ?? "",
      instagram: instagramAccounts[0]?.id ?? "",
    });
    setShowScheduler(true);
    setSchedulerInput(toLocalDateTimeInput(addDays(new Date(), 1).toISOString()));
    setSchedulerTimezone(getDeviceTimezone());

    try {
      const approved = await getContentPosts("approved");
      let candidates = approved;

      if (preselectedPostId && !approved.some((post) => post.id === preselectedPostId)) {
        const post = await getContentPost(preselectedPostId).catch(() => null);
        if (post) {
          if (post.status === "approved") {
            candidates = [post, ...approved];
          } else {
            setSchedulerNotice(
              `"${post.title || "This content"}" is ${post.status.replaceAll(
                "_",
                " "
              )}. Only approved content can be scheduled — submit it for approval in Studio and approve it first.`
            );
          }
        }
      }

      setApprovedPosts(candidates);
      const initial =
        preselectedPostId &&
        candidates.some((post) => post.id === preselectedPostId)
          ? preselectedPostId
          : candidates[0]?.id ?? null;
      setSchedulerPostId(initial);
      const post = candidates.find((item) => item.id === initial);
      setSchedulerPlatforms(post ? [post.platform] : []);
    } catch (loadError) {
      setSchedulerNotice(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load approved content."
      );
    }
  }, [facebookPages, instagramAccounts, preselectedPostId]);

  const toggleSchedulerPlatform = (platform: string) => {
    setSchedulerPlatforms((current) => {
      if (current.includes(platform)) {
        return current.filter((item) => item !== platform);
      }
      if (platform === "facebook" && !schedulerAccountIds.facebook) {
        setSchedulerAccountIds((accounts) => ({
          ...accounts,
          facebook: facebookPages[0]?.id ?? "",
        }));
      }
      if (platform === "instagram" && !schedulerAccountIds.instagram) {
        setSchedulerAccountIds((accounts) => ({
          ...accounts,
          instagram: instagramAccounts[0]?.id ?? "",
        }));
      }
      return [...current, platform];
    });
  };

  const submitSchedule = async () => {
    if (savingSchedule) return;
    setActionError("");
    setActionMessage("");

    if (!schedulerPostId) {
      setActionError("Select approved content to schedule.");
      return;
    }
    if (!schedulerPlatforms.length) {
      setActionError("Select at least one platform.");
      return;
    }
    const facebookSelected = schedulerPlatforms.includes("facebook");
    const instagramSelected = schedulerPlatforms.includes("instagram");
    if (facebookSelected && !facebookPages.length) {
      setActionError(
        "Connect a Facebook Page in Integrations before scheduling a Facebook post."
      );
      return;
    }
    if (
      facebookSelected &&
      facebookPages.length > 1 &&
      !schedulerAccountIds.facebook
    ) {
      setActionError("Choose which Facebook Page should publish this post.");
      return;
    }
    if (instagramSelected && !instagramAccounts.length) {
      setActionError(
        "Connect an Instagram professional account in Integrations before scheduling."
      );
      return;
    }
    if (
      instagramSelected &&
      instagramAccounts.length > 1 &&
      !schedulerAccountIds.instagram
    ) {
      setActionError(
        "Choose which Instagram account should publish this post."
      );
      return;
    }
    if (
      instagramSelected &&
      !approvedPosts.find((post) => post.id === schedulerPostId)?.image_url
    ) {
      setActionError(
        "Instagram feed posts need a public JPEG image. Add one in Studio before submitting content for approval."
      );
      return;
    }

    const localDate = parseLocalDateTimeInput(schedulerInput);
    if (!localDate) {
      setActionError("Enter the date and time as YYYY-MM-DDTHH:mm.");
      return;
    }
    if (localDate.getTime() <= Date.now()) {
      setActionError("Choose a time in the future.");
      return;
    }

    setSavingSchedule(true);
    try {
      const socialAccountIds: Record<string, string> = {};
      if (facebookSelected) {
        socialAccountIds.facebook =
          schedulerAccountIds.facebook || facebookPages[0].id;
      }
      if (instagramSelected) {
        socialAccountIds.instagram =
          schedulerAccountIds.instagram || instagramAccounts[0].id;
      }
      await schedulePost({
        post_id: schedulerPostId,
        platforms: schedulerPlatforms,
        scheduled_for: localDate.toISOString(),
        timezone_name: schedulerTimezone.trim() || "UTC",
        social_account_ids: socialAccountIds,
      });
      setActionMessage("Content scheduled.");
      setShowScheduler(false);
      setSchedulerAccountIds({});
      setApprovedPosts((current) =>
        current.filter((post) => post.id !== schedulerPostId)
      );
      setSchedulerPostId(null);
      await load(true);
    } catch (scheduleError) {
      setActionError(
        scheduleError instanceof Error
          ? scheduleError.message
          : "Unable to schedule this content."
      );
    } finally {
      setSavingSchedule(false);
    }
  };

  const startReschedule = (scheduled: ScheduledPost) => {
    setEditingId(scheduled.id);
    setEditInput(toLocalDateTimeInput(scheduled.scheduled_for));
    setActionError("");
    setActionMessage("");
  };

  const submitReschedule = async (scheduled: ScheduledPost) => {
    if (savingEdit) return;
    const localDate = parseLocalDateTimeInput(editInput);
    if (!localDate) {
      setActionError("Enter the date and time as YYYY-MM-DDTHH:mm.");
      return;
    }
    if (localDate.getTime() <= Date.now()) {
      setActionError("Choose a time in the future.");
      return;
    }

    setSavingEdit(true);
    try {
      await rescheduleScheduledPost(scheduled.id, {
        scheduled_for: localDate.toISOString(),
        timezone_name: scheduled.timezone_name || getDeviceTimezone(),
      });
      setEditingId(null);
      setActionMessage("Schedule updated.");
      await load(true);
    } catch (editError) {
      setActionError(
        editError instanceof Error
          ? editError.message
          : "Unable to reschedule this post."
      );
    } finally {
      setSavingEdit(false);
    }
  };

  const cancelSchedule = async (scheduled: ScheduledPost) => {
    const confirmed = await confirmDestructive(
      "Cancel this scheduled post?",
      `"${scheduled.post.title || "This post"}" will not be published to ${
        platformLabel(platforms, scheduled.platform)
      }      at ${formatDateTimeInZone(
        scheduled.scheduled_for,
        scheduled.timezone_name
      )}. The content itself is kept.`
    );
    if (!confirmed) return;

    setActionError("");
    setActionMessage("");
    try {
      await cancelScheduledPost(scheduled.id);
      setActionMessage("Scheduled post cancelled. The content is still saved.");
      await load(true);
    } catch (cancelError) {
      setActionError(
        cancelError instanceof Error
          ? cancelError.message
          : "Unable to cancel this scheduled post."
      );
    }
  };

  const renderCard = (scheduled: ScheduledPost) => {
    const style = STATUS_STYLES[scheduled.status];
    const canManage =
      scheduled.status === "pending" ||
      scheduled.status === "blocked" ||
      scheduled.status === "failed";

    return (
      <StudioCard
        key={scheduled.id}
        className="rounded-3xl border border-[#E9E2DA] bg-white p-5"
      >
        <View className="flex-row items-start justify-between gap-3">
          <View className="flex-1">
            <Text className="text-base leading-[24px] font-bold text-[#292724]" variant="label">
              {scheduled.post.title || scheduled.post.brand_name || "Scheduled post"}
            </Text>
            <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
              {scheduled.post.brand_name} · {platformLabel(platforms, scheduled.platform)}
              {scheduled.social_account
                ? ` · ${scheduled.social_account.display_name}`
                : ""}
            </Text>
          </View>
          <View className={`rounded-full px-3 py-1 ${style.badge}`}>
            <Text className={`text-[12px] font-bold ${style.text}`} variant="caption">
              {style.label}
            </Text>
          </View>
        </View>

        {!!scheduled.post.body && (
          <Text numberOfLines={3} className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
            {scheduled.post.body}
          </Text>
        )}

        <Text className="mt-4 self-start rounded-xl bg-[#F7EACF] px-3 py-2 font-semibold text-[#8A6412] text-[15px] leading-[24px]" variant="label">
          {formatDateTimeInZone(
            scheduled.scheduled_for,
            scheduled.timezone_name
          )}
          {scheduled.timezone_name ? ` · ${scheduled.timezone_name}` : ""}
        </Text>

        {!scheduled.publishing_available &&
        (scheduled.status === "pending" || scheduled.status === "blocked") ? (
          <Text className="mt-2 text-[12px] leading-[23px] text-[#8A6412]" variant="caption">
            {platformLabel(platforms, scheduled.platform)} publishing is not
            connected. This post can be scheduled and tracked but cannot be
            published yet.
          </Text>
        ) : null}

        {!!scheduled.error_message && scheduled.status !== "pending" ? (
          <Text className="mt-2 text-[12px] leading-[23px] text-[#A33D34]" variant="caption">
            {scheduled.error_message}
          </Text>
        ) : null}

        {scheduled.status === "published" && scheduled.published_at ? (
          <Text className="mt-2 text-[12px] text-[#1F6B41]" variant="caption">
            Confirmed published {formatDateTime(scheduled.published_at)}.
          </Text>
        ) : null}

        {editingId === scheduled.id ? (
          <View className="mt-3 rounded-2xl bg-[#F7F4EF] p-3">
            <Text className="text-[12px] font-semibold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
              New date and time
            </Text>
            <TextInput
              value={editInput}
              onChangeText={setEditInput}
              autoCapitalize="none"
              autoCorrect={false}
              accessibilityLabel="New scheduled date and time"
              placeholder="2030-01-15T09:30"
              className="mt-2 rounded-[18px] border border-[#E9E2DA] bg-[#F7F4EF] px-3 py-4 text-base text-[#292724]"
            />
            <View className="mt-3 flex-row gap-2">
              <Pressable
                onPress={() => void submitReschedule(scheduled)}
                disabled={savingEdit}
                accessibilityRole="button"
                className={`min-h-[54px] flex-1 items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-3 ${
                  savingEdit ? "opacity-60" : ""
                }`}
              >
                <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                  {savingEdit ? "Saving..." : "Save time"}
                </Text>
              </Pressable>
              <Pressable
                onPress={() => setEditingId(null)}
                disabled={savingEdit}
                accessibilityRole="button"
                className="min-h-[54px] flex-1 items-center justify-center rounded-[18px] border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-3"
              >
                <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="button">Close</Text>
              </Pressable>
            </View>
          </View>
        ) : canManage ? (
          <View className="mt-3 flex-row gap-2">
            <Pressable
              onPress={() => startReschedule(scheduled)}
              accessibilityRole="button"
              className="min-h-10 flex-1 items-center justify-center rounded-xl border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-3"
            >
              <Text className="text-[15px] leading-[24px] font-semibold text-[#716A64]" variant="button">
                Reschedule
              </Text>
            </Pressable>
            <Pressable
              onPress={() => void cancelSchedule(scheduled)}
              accessibilityRole="button"
              className="min-h-10 flex-1 items-center justify-center rounded-xl border border-[#F0C5BE] bg-white px-3"
            >
              <Text className="text-[15px] leading-[24px] font-semibold text-[#B04438]" variant="button">
                Cancel post
              </Text>
            </Pressable>
          </View>
        ) : null}
      </StudioCard>
    );
  };

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 36, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}
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
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#8A6412]" variant="eyebrow" tone="secondary">
          PUBLISHING
        </Text>
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
          Calendar &amp; Queue
        </Text>
        <Text className="mb-5 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          Schedule approved content, review what’s queued, and track publishing
          results.
        </Text>

        <Pressable
          onPress={() => void openScheduler()}
          accessibilityRole="button"
          className="mb-6 min-h-[54px] items-center justify-center rounded-[18px] bg-[#C24A3C] active:bg-[#A63F32] px-4"
        >
          <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">Schedule content</Text>
        </Pressable>

        {!anyPlatformAvailable && platforms.length > 0 ? (
          <View className="mb-5 rounded-2xl border border-[#F3DFB8] bg-[#FDF3DC] p-4">
            <Text className="text-[15px] leading-[23px] text-[#8A6412]" variant="body">
              No social publishing integration is connected. You can schedule
              and manage posts here, but nothing will be published to a
              platform until credentials and permissions are configured.
            </Text>
          </View>
        ) : null}

        {showScheduler ? (
          <StudioCard className="mb-5 rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <View className="flex-row items-center justify-between">
              <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                Schedule approved content
              </Text>
              <Pressable
                onPress={() => setShowScheduler(false)}
                accessibilityRole="button"
                className="min-h-9 justify-center px-2"
              >
                <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="button">Close</Text>
              </Pressable>
            </View>

            {schedulerNotice ? (
              <Text className="mt-3 rounded-xl bg-[#FDF3DC] p-3 text-[15px] leading-[23px] text-[#8A6412]" variant="body">
                {schedulerNotice}
              </Text>
            ) : null}

            {approvedPosts.length === 0 ? (
              <View className="mt-3 rounded-xl bg-[#F7F4EF] p-3">
                <Text className="text-[15px] leading-[23px] text-[#716A64]" variant="body">
                  No approved content is waiting to be scheduled. Create content
                  in Studio, submit it for approval, then approve it.
                </Text>
                <Pressable
                  onPress={() => router.push("/content-studio")}
                  accessibilityRole="button"
                  className="mt-3 min-h-10 items-center justify-center rounded-xl bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-3"
                >
                  <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">Open Studio</Text>
                </Pressable>
              </View>
            ) : (
              <>
                <Text className="mt-4 text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                  Content
                </Text>
                <View className="mt-2 gap-2">
                  {approvedPosts.map((post) => {
                    const selected = post.id === schedulerPostId;
                    return (
                      <Pressable
                        key={post.id}
                        onPress={() => {
                          setSchedulerPostId(post.id);
                          setSchedulerPlatforms([post.platform]);
                        }}
                        accessibilityRole="button"
                        accessibilityState={{ selected }}
                        className={`rounded-xl border px-3 py-3 ${
                          selected
                            ? "border-[#C24A3C] bg-[#FFF1EE]"
                            : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                        }`}
                      >
                        <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="button">
                          {post.title || post.body.slice(0, 60)}
                        </Text>
                        <Text className="mt-1 text-[12px] text-[#716A64]" variant="caption">
                          {post.brand_name} · {post.platform}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>

                <Text className="mt-4 text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                  Platforms
                </Text>
                <View className="mt-2 flex-row flex-wrap gap-2">
                  {platforms.map((platform) => (
                    <Chip
                      key={platform.platform}
                      label={platform.label}
                      active={schedulerPlatforms.includes(platform.platform)}
                      onPress={() => toggleSchedulerPlatform(platform.platform)}
                    />
                  ))}
                </View>

                {schedulerPlatforms.includes("facebook") ? (
                  <>
                    <Text className="mt-4 text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                      Facebook Page
                    </Text>
                    {facebookPages.length === 0 ? (
                      <Text className="mt-2 rounded-xl bg-[#FDF3DC] p-3 text-[15px] leading-[23px] text-[#8A6412]" variant="body">
                        No Facebook Page is connected. Connect one in
                        Integrations before scheduling to Facebook.
                      </Text>
                    ) : (
                      <View className="mt-2 flex-row flex-wrap gap-2">
                        {facebookPages.map((page) => (
                          <Chip
                            key={page.id}
                            label={page.display_name || page.platform_account_id}
                            active={schedulerAccountIds.facebook === page.id}
                            onPress={() =>
                              setSchedulerAccountIds((accounts) => ({
                                ...accounts,
                                facebook: page.id,
                              }))
                            }
                          />
                        ))}
                      </View>
                    )}
                  </>
                ) : null}

                {schedulerPlatforms.includes("instagram") ? (
                  <>
                    <Text className="mt-4 text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                      Instagram account
                    </Text>
                    {instagramAccounts.length === 0 ? (
                      <Text className="mt-2 rounded-xl bg-[#FDF3DC] p-3 text-[15px] leading-[23px] text-[#8A6412]" variant="body">
                        No Instagram professional account is connected. Connect
                        one in Integrations before scheduling to Instagram.
                      </Text>
                    ) : (
                      <View className="mt-2 flex-row flex-wrap gap-2">
                        {instagramAccounts.map((account) => (
                          <Chip
                            key={account.id}
                            label={
                              account.display_name ||
                              account.platform_account_id
                            }
                            active={
                              schedulerAccountIds.instagram === account.id
                            }
                            onPress={() =>
                              setSchedulerAccountIds((accounts) => ({
                                ...accounts,
                                instagram: account.id,
                              }))
                            }
                          />
                        ))}
                      </View>
                    )}
                  </>
                ) : null}

                <Text className="mt-4 text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                  Date and time
                </Text>
                <TextInput
                  value={schedulerInput}
                  onChangeText={setSchedulerInput}
                  autoCapitalize="none"
                  autoCorrect={false}
                  accessibilityLabel="Scheduled date and time"
                  placeholder="2030-01-15T09:30"
                  className="mt-2 rounded-[18px] border border-[#E9E2DA] bg-[#F7F4EF] px-3 py-4 text-base text-[#292724]"
                />
                <Text className="mt-1 text-[12px] text-[#716A64]" variant="caption">
                  Format: YYYY-MM-DDTHH:mm in your local time.
                </Text>

                <Text className="mt-4 text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                  Timezone
                </Text>
                <TextInput
                  value={schedulerTimezone}
                  onChangeText={setSchedulerTimezone}
                  autoCapitalize="none"
                  autoCorrect={false}
                  accessibilityLabel="Timezone"
                  placeholder="Asia/Karachi"
                  className="mt-2 rounded-[18px] border border-[#E9E2DA] bg-[#F7F4EF] px-3 py-4 text-base text-[#292724]"
                />
                <Text className="mt-1 text-[12px] text-[#716A64]" variant="caption">
                  The time is stored in UTC and shown in this zone.
                </Text>

                <Pressable
                  onPress={() => void submitSchedule()}
                  disabled={savingSchedule}
                  accessibilityRole="button"
                  className={`mt-4 min-h-[54px] items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-4 ${
                    savingSchedule ? "opacity-60" : ""
                  }`}
                >
                  <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                    {savingSchedule ? "Scheduling..." : "Schedule post"}
                  </Text>
                </Pressable>
              </>
            )}
          </StudioCard>
        ) : null}

        {actionError ? (
          <View className="mb-4 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text accessibilityRole="alert" className="text-[#A33D34] text-[15px] leading-[24px]" variant="body">
              {actionError}
            </Text>
          </View>
        ) : null}
        {actionMessage ? (
          <View className="mb-4 rounded-2xl border border-[#B8DEC5] bg-white p-4">
            <Text className="text-[#286B40] text-[15px] leading-[24px]" variant="body">{actionMessage}</Text>
          </View>
        ) : null}

        <View className="mb-4 flex-row gap-2">
          {(["month", "week", "list"] as ViewMode[]).map((mode) => (
            <Chip
              key={mode}
              label={mode === "month" ? "Month" : mode === "week" ? "Week" : "List"}
              active={viewMode === mode}
              onPress={() => {
                setViewMode(mode);
                if (mode === "week") setSelectedDate(startOfLocalDay(new Date()));
              }}
            />
          ))}
        </View>

        <View className="mb-4 gap-2">
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View className="flex-row gap-2 pr-2">
              <Chip
                label="All brands"
                active={brandFilter === "all"}
                onPress={() => setBrandFilter("all")}
              />
              {brandOptions.map((brand) => (
                <Chip
                  key={brand.id}
                  label={brand.name}
                  active={brandFilter === brand.id}
                  onPress={() => setBrandFilter(brand.id)}
                />
              ))}
            </View>
          </ScrollView>
          {platformOptions.length > 1 ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View className="flex-row gap-2 pr-2">
                <Chip
                  label="All platforms"
                  active={platformFilter === "all"}
                  onPress={() => setPlatformFilter("all")}
                />
                {platformOptions.map((platform) => (
                  <Chip
                    key={platform}
                    label={platformLabel(platforms, platform)}
                    active={platformFilter === platform}
                    onPress={() => setPlatformFilter(platform)}
                  />
                ))}
              </View>
            </ScrollView>
          ) : null}
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View className="flex-row gap-2 pr-2">
              <Chip
                label="All statuses"
                active={statusFilter === "all"}
                onPress={() => setStatusFilter("all")}
              />
              {(Object.keys(STATUS_STYLES) as ScheduledStatus[]).map((status) => (
                <Chip
                  key={status}
                  label={STATUS_STYLES[status].label}
                  active={statusFilter === status}
                  onPress={() => setStatusFilter(status)}
                />
              ))}
            </View>
          </ScrollView>
        </View>

        {loading ? (
          <View className="items-center rounded-3xl border border-[#E9E2DA] bg-white py-8">
            <ActivityIndicator size="small" color="#C24A3C" />
            <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">Loading your calendar...</Text>
          </View>
        ) : error ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn’t load your schedule
            </Text>
            <Text className="mt-2 text-[#A33D34] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-[54px] self-start justify-center rounded-[18px] bg-[#292724] px-4 py-2"
            >
              <Text className="font-semibold text-white text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </StudioCard>
        ) : (
          <>
            {viewMode === "month" ? (
              <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
                <View className="mb-6 flex-row items-center justify-between">
                  <Pressable
                    onPress={() => changePeriod(-1)}
                    accessibilityRole="button"
                    accessibilityLabel="Previous month"
                    className="h-11 w-11 items-center justify-center rounded-full bg-[#F1E9DF]"
                  >
                    <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">‹</Text>
                  </Pressable>
                  <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                    {month.toLocaleDateString(undefined, {
                      month: "long",
                      year: "numeric",
                    })}
                  </Text>
                  <Pressable
                    onPress={() => changePeriod(1)}
                    accessibilityRole="button"
                    accessibilityLabel="Next month"
                    className="h-11 w-11 items-center justify-center rounded-full bg-[#F1E9DF]"
                  >
                    <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">›</Text>
                  </Pressable>
                </View>

                <View className="mb-2 flex-row">
                  {WEEKDAYS.map((weekday) => (
                    <View key={weekday} className="flex-1 items-center py-2">
                      <Text className="text-[12px] font-semibold text-[#716A64]" variant="caption">
                        {weekday}
                      </Text>
                    </View>
                  ))}
                </View>

                <View className="flex-row flex-wrap">
                  {monthDays.map((day, index) => {
                    if (!day) {
                      return (
                        <View key={`blank-${index}`} className="w-[14.285%] p-1" />
                      );
                    }
                    const key = localDateKey(day);
                    const dayPosts = postsByDate.get(key) ?? [];
                    const selected = key === localDateKey(selectedDate);
                    const isToday = key === localDateKey(new Date());
                    return (
                      <Pressable
                        key={key}
                        onPress={() => setSelectedDate(startOfLocalDay(day))}
                        accessibilityRole="button"
                        accessibilityLabel={`${day.toLocaleDateString(undefined, {
                          month: "long",
                          day: "numeric",
                        })}${dayPosts.length ? `, ${dayPosts.length} scheduled posts` : ""}`}
                        accessibilityState={{ selected }}
                        className="w-[14.285%] items-center rounded-2xl p-1"
                      >
                        <View
                          className={`h-10 w-10 items-center justify-center rounded-full ${
                            selected
                              ? "bg-[#D69B48]"
                              : isToday
                                ? "border border-[#D69B48] bg-[#F7EACF]"
                                : ""
                          }`}
                        >
                          <Text
                            className={`text-[15px] leading-[24px] font-semibold ${
                              selected ? "text-[#292724]" : "text-[#292724]"
                            }`} variant="label"
                          >
                            {day.getDate()}
                          </Text>
                        </View>
                        <View className="mt-1 h-2 flex-row items-center justify-center gap-1">
                          {dayPosts.slice(0, 3).map((post) => (
                            <View
                              key={post.id}
                              className={`h-1.5 w-1.5 rounded-full ${
                                selected
                                  ? "bg-[#D69B48]"
                                  : STATUS_STYLES[post.status].dot
                              }`}
                            />
                          ))}
                        </View>
                      </Pressable>
                    );
                  })}
                </View>
              </StudioCard>
            ) : null}

            {viewMode === "week" ? (
              <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
                <View className="mb-4 flex-row items-center justify-between">
                  <Pressable
                    onPress={() => changePeriod(-1)}
                    accessibilityRole="button"
                    accessibilityLabel="Previous week"
                    className="h-11 w-11 items-center justify-center rounded-full bg-[#F1E9DF]"
                  >
                    <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">‹</Text>
                  </Pressable>
                  <Text className="text-[15px] leading-[24px] font-bold text-[#292724]" variant="label">
                    {visibleWeekStart.toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}{" "}
                    –{" "}
                    {addDays(visibleWeekStart, 6).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </Text>
                  <Pressable
                    onPress={() => changePeriod(1)}
                    accessibilityRole="button"
                    accessibilityLabel="Next week"
                    className="h-11 w-11 items-center justify-center rounded-full bg-[#F1E9DF]"
                  >
                    <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">›</Text>
                  </Pressable>
                </View>

                <View className="gap-2">
                  {weekDays.map((day) => {
                    const key = localDateKey(day);
                    const dayPosts = postsByDate.get(key) ?? [];
                    const selected = key === localDateKey(selectedDate);
                    return (
                      <Pressable
                        key={key}
                        onPress={() => setSelectedDate(startOfLocalDay(day))}
                        accessibilityRole="button"
                        accessibilityState={{ selected }}
                        className={`flex-row items-center justify-between rounded-2xl border px-3 py-3 ${
                          selected
                            ? "border-[#C24A3C] bg-[#FFF1EE]"
                            : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                        }`}
                      >
                        <View>
                          <Text className="text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                            {day.toLocaleDateString(undefined, { weekday: "short" })}
                          </Text>
                          <Text className="text-base leading-[24px] font-bold text-[#292724]" variant="label">
                            {day.getDate()}
                          </Text>
                        </View>
                        <View className="flex-1 flex-row items-center justify-end gap-1">
                          {dayPosts.slice(0, 3).map((post) => (
                            <View
                              key={post.id}
                              className={`h-2 w-2 rounded-full ${STATUS_STYLES[post.status].dot}`}
                            />
                          ))}
                          <Text className="ml-2 text-[12px] text-[#716A64]" variant="caption">
                            {dayPosts.length
                              ? `${dayPosts.length} post${dayPosts.length > 1 ? "s" : ""}`
                              : "—"}
                          </Text>
                        </View>
                      </Pressable>
                    );
                  })}
                </View>
              </StudioCard>
            ) : null}

            {viewMode !== "list" ? (
              <View className="mt-6">
                <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
                  {formatLongDate(selectedDate)}
                </Text>
                {selectedPosts.length === 0 ? (
                  <StudioCard className="mt-3 rounded-3xl border border-[#E9E2DA] bg-white p-5">
                    <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                      Nothing scheduled for this day
                    </Text>
                    <Text className="mt-1 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                      Schedule approved content to fill this slot.
                    </Text>
                  </StudioCard>
                ) : (
                  <View className="mt-3 gap-3">
                    {selectedPosts.map(renderCard)}
                  </View>
                )}
              </View>
            ) : (
              <View className="gap-3">
                <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
                  Scheduled queue
                </Text>
                {filteredPosts.length === 0 ? (
                  <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
                    <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                      No scheduled posts match these filters
                    </Text>
                    <Text className="mt-1 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                      Adjust the filters or schedule approved content.
                    </Text>
                  </StudioCard>
                ) : (
                  filteredPosts.map(renderCard)
                )}

                <Text className="mt-4 text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
                  Drafts
                </Text>
                {drafts.length === 0 ? (
                  <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
                    <Text className="text-[#716A64] text-[15px] leading-[24px]" variant="body">
                      No drafts. Content created in Studio appears here until it
                      is approved and scheduled.
                    </Text>
                  </StudioCard>
                ) : (
                  drafts.map((draft) => (
                    <StudioCard
                      key={draft.id}
                      className="rounded-3xl border border-dashed border-[#D8D0C7] bg-white p-5"
                    >
                      <View className="flex-row items-start justify-between gap-3">
                        <Text className="flex-1 font-bold text-[#292724] text-[15px] leading-[24px]" variant="label">
                          {draft.title || draft.body.slice(0, 60)}
                        </Text>
                        <View className="rounded-full bg-[#F1E9DF] px-3 py-1">
                          <Text className="text-[12px] font-bold text-[#716A64]" variant="caption">
                            Draft
                          </Text>
                        </View>
                      </View>
                      <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                        {draft.brand_name} · {draft.platform}
                      </Text>
                      <Text className="mt-2 text-[12px] leading-[23px] text-[#716A64]" variant="caption">
                        Submit this draft for approval in Studio before it can be
                        scheduled.
                      </Text>
                      <Pressable
                        onPress={() => router.push("/content-studio")}
                        accessibilityRole="button"
                        className="mt-3 min-h-10 items-center justify-center rounded-xl border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-3"
                      >
                        <Text className="text-[15px] leading-[24px] font-semibold text-[#716A64]" variant="button">
                          Open in Studio
                        </Text>
                      </Pressable>
                    </StudioCard>
                  ))
                )}
              </View>
            )}
          </>
        )}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
