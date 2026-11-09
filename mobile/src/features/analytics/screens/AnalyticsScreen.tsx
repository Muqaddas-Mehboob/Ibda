import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { useCallback, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
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
    color: "#C24A3C",
  },
  {
    key: "pending_approvals",
    label: "Pending approvals",
    detail: "Submitted in this period",
    color: "#D69B48",
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
    color: "#826C8B",
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
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">Analytics</Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          A clear view of your content workflow across your brands.
        </Text>

        <View
          accessibilityRole="tablist"
          className="mb-6 flex-row rounded-2xl border border-[#E9E2DA] bg-white p-1"
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
                className={`min-h-[54px] flex-1 items-center justify-center rounded-[18px] ${
                  selected ? "bg-[#292724]" : ""
                }`}
              >
                <Text
                  className={`text-[15px] leading-[24px] font-semibold ${
                    selected ? "text-white" : "text-[#716A64]"
                  }`} variant="button"
                >
                  {range} days
                </Text>
              </Pressable>
            );
          })}
        </View>

        {loading ? (
          <View className="items-center py-16">
            <ActivityIndicator size="large" color="#C24A3C" />
            <Text className="mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">Loading your analytics...</Text>
          </View>
        ) : error ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn’t load analytics
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
        ) : analytics ? (
          <>
            <View className="mb-6 flex-row flex-wrap justify-between gap-y-3">
              {METRICS.map((metric) => (
                <StudioCard
                  key={metric.key}
                  className="w-[48%] rounded-3xl border border-[#E9E2DA] bg-white p-5"
                >
                  <View
                    className="mb-4 h-2 w-10 rounded-full"
                    style={{ backgroundColor: metric.color }}
                  />
                  <Text className="text-[30px] leading-[37px] tracking-[-0.6px] font-bold text-[#292724]" variant="metric">
                    {analytics.summary[metric.key]}
                  </Text>
                  <Text className="mt-1 font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="label">
                    {metric.label}
                  </Text>
                  <Text className="mt-1 text-[12px] leading-[18px] text-[#716A64]" variant="caption">
                    {metric.detail}
                  </Text>
                </StudioCard>
              ))}
            </View>

            {!hasData ? (
              <StudioCard className="mb-6 rounded-3xl border border-[#E9E2DA] bg-white p-5">
                <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                  No activity in this period
                </Text>
                <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                  When you create content, submit approvals, or schedule posts,
                  your real activity will appear here.
                </Text>
              </StudioCard>
            ) : null}

            <StudioCard className="mb-6 rounded-3xl border border-[#E9E2DA] bg-white p-5">
              <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                Content activity
              </Text>
              <Text className="mb-5 mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                Posts created by{" "}
                {analytics.activity_granularity === "day" ? "day" : "week"}
              </Text>
              {analytics.activity.every((item) => item.content_posts === 0) ? (
                <Text className="py-6 text-center text-[15px] leading-[24px] text-[#716A64]" variant="body">
                  No content posts in this period.
                </Text>
              ) : (
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={{ gap: 12, width: "100%", maxWidth: 960, alignSelf: "center" }}
                >
                  {analytics.activity.map((item) => (
                    <View
                      key={item.date}
                      accessibilityLabel={`${activityDateLabel(item.date)}: ${item.content_posts} posts`}
                      className="w-10 items-center"
                    >
                      <View className="h-32 w-8 justify-end overflow-hidden rounded-full bg-[#F1E9DF]">
                        <View
                          className="w-full rounded-full bg-[#C24A3C]"
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
                      <Text className="mt-2 text-[11px] font-semibold text-[#716A64]" variant="caption">
                        {activityDateLabel(item.date)}
                      </Text>
                      <Text className="mt-1 text-[12px] font-bold text-[#292724]" variant="caption">
                        {item.content_posts}
                      </Text>
                    </View>
                  ))}
                </ScrollView>
              )}
            </StudioCard>

            <StudioCard className="mb-6 rounded-3xl border border-[#E9E2DA] bg-white p-5">
              <Text className="mb-4 text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                Content by brand
              </Text>
              {analytics.brands.length === 0 ? (
                <Text className="py-3 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                  No brand content in this period.
                </Text>
              ) : (
                <View className="gap-4">
                  {analytics.brands.map((brand) => (
                    <View key={brand.brand_id}>
                      <View className="mb-2 flex-row justify-between gap-3">
                        <Text
                          numberOfLines={1}
                          className="flex-1 font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="label"
                        >
                          {brand.brand_name}
                        </Text>
                        <Text className="font-bold text-[#292724] text-[15px] leading-[24px]" variant="label">
                          {brand.content_posts}
                        </Text>
                      </View>
                      <View className="h-2 overflow-hidden rounded-full bg-[#F1E9DF]">
                        <View
                          className="h-full rounded-full bg-[#C24A3C]"
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
            </StudioCard>

            <View className="rounded-3xl border border-[#E9E2DA] bg-[#F1E9DF] p-6">
              <Text className="font-bold text-[#292724] text-[15px] leading-[24px]" variant="label">
                Social performance
              </Text>
              <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
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
