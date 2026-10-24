import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  getScheduledPosts,
  type ScheduledPost,
} from "../services/calendar.service";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

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

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

export function CalendarScreen() {
  const [month, setMonth] = useState(() => monthStart(new Date()));
  const [selectedDate, setSelectedDate] = useState(() =>
    startOfLocalDay(new Date())
  );
  const [monthPosts, setMonthPosts] = useState<ScheduledPost[]>([]);
  const [queuePosts, setQueuePosts] = useState<ScheduledPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const visibleMonthStart = useMemo(() => monthStart(month), [month]);
  const visibleMonthEnd = useMemo(
    () => new Date(month.getFullYear(), month.getMonth() + 1, 1),
    [month]
  );
  const queueStart = useMemo(() => startOfLocalDay(new Date()), []);
  const queueEnd = useMemo(
    () =>
      new Date(
        queueStart.getFullYear(),
        queueStart.getMonth(),
        queueStart.getDate() + 90
      ),
    [queueStart]
  );

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError("");

      try {
        const [forMonth, upcoming] = await Promise.all([
          getScheduledPosts(visibleMonthStart, visibleMonthEnd),
          getScheduledPosts(queueStart, queueEnd),
        ]);
        setMonthPosts(forMonth);
        setQueuePosts(upcoming);
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
    [queueEnd, queueStart, visibleMonthEnd, visibleMonthStart]
  );

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const postsByDate = useMemo(() => {
    const result = new Map<string, ScheduledPost[]>();
    for (const post of monthPosts) {
      const key = scheduledDateKey(post.scheduled_for);
      if (!key) continue;
      const posts = result.get(key) ?? [];
      posts.push(post);
      result.set(key, posts);
    }
    return result;
  }, [monthPosts]);

  const selectedPosts = postsByDate.get(localDateKey(selectedDate)) ?? [];
  const days = useMemo(() => getMonthDays(month), [month]);
  const upcomingPosts = useMemo(
    () =>
      queuePosts
        .filter((post) => {
          const scheduledAt = new Date(post.scheduled_for).getTime();
          return Number.isFinite(scheduledAt) && scheduledAt >= Date.now();
        })
        .sort(
          (a, b) =>
            new Date(a.scheduled_for).getTime() -
            new Date(b.scheduled_for).getTime()
        ),
    [queuePosts]
  );

  const changeMonth = (offset: number) => {
    const next = new Date(month.getFullYear(), month.getMonth() + offset, 1);
    setMonth(next);
    setSelectedDate(startOfLocalDay(next));
  };

  const todayKey = localDateKey(new Date());

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 36, paddingBottom: 32 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#FF6B5F"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          PUBLISHING
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">
          Calendar &amp; Queue
        </Text>
        <Text className="mb-7 mt-3 text-base leading-6 text-[#827970]">
          See what’s scheduled and what’s coming up for your brands.
        </Text>

        <View className="rounded-3xl border border-[#EAE4DC] bg-white p-4">
          <View className="mb-5 flex-row items-center justify-between">
            <Pressable
              onPress={() => changeMonth(-1)}
              accessibilityRole="button"
              accessibilityLabel="Previous month"
              className="h-11 w-11 items-center justify-center rounded-full bg-[#F3EEE8]"
            >
              <Text className="text-xl font-bold text-[#24221F]">‹</Text>
            </Pressable>
            <Text className="text-lg font-bold text-[#24221F]">
              {month.toLocaleDateString(undefined, {
                month: "long",
                year: "numeric",
              })}
            </Text>
            <Pressable
              onPress={() => changeMonth(1)}
              accessibilityRole="button"
              accessibilityLabel="Next month"
              className="h-11 w-11 items-center justify-center rounded-full bg-[#F3EEE8]"
            >
              <Text className="text-xl font-bold text-[#24221F]">›</Text>
            </Pressable>
          </View>

          <View className="mb-2 flex-row">
            {WEEKDAYS.map((weekday) => (
              <View key={weekday} className="flex-1 items-center py-2">
                <Text className="text-xs font-semibold text-[#827970]">
                  {weekday}
                </Text>
              </View>
            ))}
          </View>

          <View className="flex-row flex-wrap">
            {days.map((day, index) => {
              if (!day) {
                return <View key={`blank-${index}`} className="w-[14.285%] p-1" />;
              }
              const key = localDateKey(day);
              const dayPosts = loading ? [] : postsByDate.get(key) ?? [];
              const selected = key === localDateKey(selectedDate);
              const isToday = key === todayKey;
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
                  className={`w-[14.285%] items-center rounded-2xl p-1`}
                >
                  <View
                    className={`h-10 w-10 items-center justify-center rounded-full ${
                      selected
                        ? "bg-[#FF6B5F]"
                        : isToday
                          ? "border border-[#FF6B5F] bg-[#FFF7F4]"
                          : ""
                    }`}
                  >
                    <Text
                      className={`text-sm font-semibold ${
                        selected ? "text-white" : "text-[#24221F]"
                      }`}
                    >
                      {day.getDate()}
                    </Text>
                  </View>
                  <View className="mt-1 h-2 flex-row items-center justify-center gap-1">
                    {dayPosts.slice(0, 3).map((post) => (
                      <View
                        key={post.id}
                        className={`h-1.5 w-1.5 rounded-full ${
                          selected ? "bg-[#FFB9AC]" : "bg-[#FF6B5F]"
                        }`}
                      />
                    ))}
                  </View>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View className="mt-7">
          <Text className="text-xl font-bold text-[#24221F]">
            {selectedDate.toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </Text>

          {loading ? (
            <View className="items-center py-8">
              <ActivityIndicator size="small" color="#FF6B5F" />
              <Text className="mt-2 text-[#827970]">
                Loading your calendar...
              </Text>
            </View>
          ) : error ? (
            <View className="mt-4 rounded-3xl border border-[#EAE4DC] bg-white p-5">
              <Text className="font-semibold text-[#24221F]">
                Couldn’t load your schedule
              </Text>
              <Text className="mt-2 leading-5 text-[#A33D34]">{error}</Text>
              <Pressable
                onPress={() => void load()}
                accessibilityRole="button"
                className="mt-4 min-h-11 self-start justify-center rounded-xl bg-[#24221F] px-4 py-2"
              >
                <Text className="font-semibold text-white">Try again</Text>
              </Pressable>
            </View>
          ) : selectedPosts.length === 0 ? (
            <View className="mt-4 rounded-3xl border border-[#EAE4DC] bg-white p-5">
              <Text className="font-semibold text-[#24221F]">
                Nothing scheduled for this day
              </Text>
              <Text className="mt-1 leading-5 text-[#827970]">
                Posts scheduled for this date will appear here.
              </Text>
            </View>
          ) : (
            <View className="mt-4 gap-3">
              {selectedPosts.map((scheduled) => (
                <ScheduledPostCard key={scheduled.id} scheduled={scheduled} />
              ))}
            </View>
          )}
        </View>

        <View className="mt-8">
          <View className="mb-4 flex-row items-center justify-between">
            <Text className="text-xl font-bold text-[#24221F]">
              Upcoming queue
            </Text>
            <Text className="text-sm text-[#827970]">Next 90 days</Text>
          </View>
          {loading ? (
            <View className="items-center py-6">
              <ActivityIndicator color="#FF6B5F" />
            </View>
          ) : !error && upcomingPosts.length === 0 ? (
            <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
              <Text className="font-semibold text-[#24221F]">
                Your queue is clear
              </Text>
              <Text className="mt-1 leading-5 text-[#827970]">
                No upcoming scheduled posts were found.
              </Text>
            </View>
          ) : (
            !error && (
              <View className="gap-3">
                {upcomingPosts.map((scheduled) => (
                  <ScheduledPostCard
                    key={scheduled.id}
                    scheduled={scheduled}
                    showDate
                  />
                ))}
              </View>
            )
          )}
        </View>
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}

function ScheduledPostCard({
  scheduled,
  showDate = false,
}: {
  scheduled: ScheduledPost;
  showDate?: boolean;
}) {
  return (
    <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
      <View className="mb-2 flex-row items-start justify-between gap-3">
        <View className="flex-1">
          <Text className="text-base font-bold text-[#24221F]">
            {scheduled.post.title || scheduled.post.brand_name || "Scheduled post"}
          </Text>
          <Text className="mt-1 text-sm text-[#827970]">
            {scheduled.post.brand_name} ·{" "}
            {scheduled.platform.replaceAll("_", " ")}
          </Text>
        </View>
        <Text className="rounded-full bg-[#F3EEE8] px-3 py-1 text-xs font-semibold capitalize text-[#705B52]">
          {statusLabel(scheduled.status)}
        </Text>
      </View>
      {!!scheduled.post.body && (
        <Text numberOfLines={3} className="mt-2 leading-5 text-[#51483F]">
          {scheduled.post.body}
        </Text>
      )}
      <View className="mt-4 border-t border-[#EAE4DC] pt-3">
        <Text className="font-semibold text-[#FF6B5F]">
          {showDate
            ? formatDateTime(scheduled.scheduled_for)
            : formatTime(scheduled.scheduled_for)}
        </Text>
      </View>
    </View>
  );
}
