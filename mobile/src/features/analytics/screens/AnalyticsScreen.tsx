import { useCallback, useState } from "react";
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
  getAnalytics,
  type AnalyticsDays,
  type AnalyticsResponse,
} from "../services/analytics.service";

const RANGES: AnalyticsDays[] = [7, 30, 90];

const METRICS = [
  {
    key: "content_posts",
    label: "Content posts",
    detail: "Created in this period",
    color: "#FF6B5F",
  },
  {
    key: "pending_approvals",
    label: "Pending approvals",
    detail: "Submitted in this period",
    color: "#D49B42",
  },
  {
    key: "approved_content",
    label: "Approved",
    detail: "Posts created in this period",
    color: "#4D9678",
  },
  {
    key: "rejected_content",
    label: "Rejected",
    detail: "Posts created in this period",
    color: "#B76C5E",
  },
  {
    key: "scheduled_posts",
    label: "Scheduled posts",
    detail: "Scheduled dates in this period",
    color: "#8171A8",
  },
] as const;

function activityDateLabel(value: string) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
}

export function AnalyticsScreen() {
  const [days, setDays] = useState<AnalyticsDays>(30);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError("");
      try {
        setAnalytics(await getAnalytics(days));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load analytics."
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [days]
  );

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const hasData =
    analytics !== null &&
    Object.values(analytics.summary).some((value) => value > 0);
  const maxActivity = Math.max(
    1,
    ...(analytics?.activity.map((item) => item.content_posts) ?? [])
  );

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 32,
        }}
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
          YOUR WORKSPACE
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">Analytics</Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#827970]">
          A clear view of your content workflow across your brands.
        </Text>

        <View
          accessibilityRole="tablist"
          className="mb-6 flex-row rounded-2xl border border-[#EAE4DC] bg-white p-1"
        >
          {RANGES.map((range) => {
            const selected = days === range;
            return (
              <Pressable
                key={range}
                onPress={() => setDays(range)}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                accessibilityLabel={`Last ${range} days`}
                className={`min-h-11 flex-1 items-center justify-center rounded-xl ${
                  selected ? "bg-[#24221F]" : ""
                }`}
              >
                <Text
                  className={`text-sm font-semibold ${
                    selected ? "text-white" : "text-[#827970]"
                  }`}
                >
                  {range} days
                </Text>
              </Pressable>
            );
          })}
        </View>

        {loading ? (
          <View className="items-center py-16">
            <ActivityIndicator size="large" color="#FF6B5F" />
            <Text className="mt-3 text-[#827970]">Loading your analytics...</Text>
          </View>
        ) : error ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
            <Text className="font-semibold text-[#24221F]">
              Couldn’t load analytics
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
        ) : analytics ? (
          <>
            <View className="mb-6 flex-row flex-wrap justify-between gap-y-3">
              {METRICS.map((metric) => (
                <View
                  key={metric.key}
                  className="w-[48%] rounded-3xl border border-[#EAE4DC] bg-white p-4"
                >
                  <View
                    className="mb-4 h-2 w-10 rounded-full"
                    style={{ backgroundColor: metric.color }}
                  />
                  <Text className="text-3xl font-bold text-[#24221F]">
                    {analytics.summary[metric.key]}
                  </Text>
                  <Text className="mt-1 font-semibold text-[#51483F]">
                    {metric.label}
                  </Text>
                  <Text className="mt-1 text-xs leading-4 text-[#827970]">
                    {metric.detail}
                  </Text>
                </View>
              ))}
            </View>

            {!hasData ? (
              <View className="mb-6 rounded-3xl border border-[#EAE4DC] bg-white p-5">
                <Text className="text-lg font-bold text-[#24221F]">
                  No activity in this period
                </Text>
                <Text className="mt-2 leading-5 text-[#827970]">
                  When you create content, submit approvals, or schedule posts,
                  your real activity will appear here.
                </Text>
              </View>
            ) : null}

            <View className="mb-6 rounded-3xl border border-[#EAE4DC] bg-white p-5">
              <Text className="text-lg font-bold text-[#24221F]">
                Content activity
              </Text>
              <Text className="mb-5 mt-1 text-sm text-[#827970]">
                Posts created by{" "}
                {analytics.activity_granularity === "day" ? "day" : "week"}
              </Text>
              {analytics.activity.every((item) => item.content_posts === 0) ? (
                <Text className="py-6 text-center text-sm text-[#827970]">
                  No content posts in this period.
                </Text>
              ) : (
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={{ gap: 12 }}
                >
                  {analytics.activity.map((item) => (
                    <View
                      key={item.date}
                      accessibilityLabel={`${activityDateLabel(item.date)}: ${item.content_posts} posts`}
                      className="w-10 items-center"
                    >
                      <View className="h-32 w-8 justify-end overflow-hidden rounded-full bg-[#F3EEE8]">
                        <View
                          className="w-full rounded-full bg-[#FF6B5F]"
                          style={{
                            height:
                              item.content_posts === 0
                                ? 0
                                : Math.max(
                                    5,
                                    (item.content_posts / maxActivity) * 128
                                  ),
                          }}
                        />
                      </View>
                      <Text className="mt-2 text-[10px] font-semibold text-[#827970]">
                        {activityDateLabel(item.date)}
                      </Text>
                      <Text className="mt-1 text-xs font-bold text-[#24221F]">
                        {item.content_posts}
                      </Text>
                    </View>
                  ))}
                </ScrollView>
              )}
            </View>

            <View className="mb-6 rounded-3xl border border-[#EAE4DC] bg-white p-5">
              <Text className="mb-4 text-lg font-bold text-[#24221F]">
                Content by brand
              </Text>
              {analytics.brands.length === 0 ? (
                <Text className="py-3 text-sm text-[#827970]">
                  No brand content in this period.
                </Text>
              ) : (
                <View className="gap-4">
                  {analytics.brands.map((brand) => (
                    <View key={brand.brand_id}>
                      <View className="mb-2 flex-row justify-between gap-3">
                        <Text
                          numberOfLines={1}
                          className="flex-1 font-semibold text-[#51483F]"
                        >
                          {brand.brand_name}
                        </Text>
                        <Text className="font-bold text-[#24221F]">
                          {brand.content_posts}
                        </Text>
                      </View>
                      <View className="h-2 overflow-hidden rounded-full bg-[#F3EEE8]">
                        <View
                          className="h-full rounded-full bg-[#FF6B5F]"
                          style={{
                            width: `${
                              (brand.content_posts /
                                Math.max(
                                  1,
                                  ...analytics.brands.map(
                                    (item) => item.content_posts
                                  )
                                )) *
                              100
                            }%`,
                          }}
                        />
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </View>

            <View className="rounded-3xl border border-[#EAE4DC] bg-[#F5EFE7] p-5">
              <Text className="font-bold text-[#24221F]">
                Social performance
              </Text>
              <Text className="mt-2 leading-5 text-[#827970]">
                Engagement, reach, clicks, and follower metrics aren’t shown
                because no social platform analytics integration is configured.
              </Text>
            </View>
          </>
        ) : null}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
