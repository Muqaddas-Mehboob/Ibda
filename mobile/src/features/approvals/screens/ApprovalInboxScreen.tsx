import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { useCallback, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  getApprovals,
  type Approval,
  type ApprovalStatus,
} from "../services/approval.service";

const FILTERS: { label: string; value: ApprovalStatus }[] = [
  { label: "Pending", value: "pending" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
];

const EMPTY_MESSAGES: Record<ApprovalStatus, string> = {
  pending: "Nothing is waiting for review. New content will appear here.",
  approved: "You haven't approved any content yet.",
  rejected: "You haven't rejected any content.",
};

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}

export function ApprovalInboxScreen() {
  const router = useRouter();
  const [filter, setFilter] = useState<ApprovalStatus>("pending");
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError("");

      try {
        setApprovals(await getApprovals(filter));
      } catch (loadError) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load approval items."
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [filter]
  );

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 40, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#C24A3C"
          />
        }
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
          CONTENT WORKSPACE
        </Text>
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
          Approval Inbox
        </Text>
        <Text className="mb-7 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          Review content from your brands before it moves to the next step.
        </Text>

        <View
          accessibilityRole="tablist"
          className="mb-6 flex-row rounded-2xl border border-[#E9E2DA] bg-white p-1"
        >
          {FILTERS.map((item) => {
            const selected = filter === item.value;
            return (
              <Pressable
                key={item.value}
                onPress={() => setFilter(item.value)}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                className={`min-h-[54px] flex-1 items-center justify-center rounded-[18px] px-2 ${
                  selected ? "bg-[#292724]" : ""
                }`}
              >
                <Text
                  className={`text-[15px] leading-[24px] font-semibold ${
                    selected ? "text-white" : "text-[#716A64]"
                  }`} variant="button"
                >
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator color="#C24A3C" size="large" />
            <Text className="mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">Loading approvals...</Text>
          </View>
        ) : error ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn&apos;t load approvals
            </Text>
            <Text className="mt-2 text-[#B04438] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-[54px] self-start justify-center rounded-[18px] bg-[#292724] px-4 py-2"
            >
              <Text className="font-semibold text-white text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </StudioCard>
        ) : approvals.length === 0 ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
              {filter === "pending"
                ? "You’re all caught up"
                : `No ${filter} content yet`}
            </Text>
            <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              {EMPTY_MESSAGES[filter]}
            </Text>
          </StudioCard>
        ) : (
          <View className="gap-4">
            {approvals.map((approval) => (
              <Pressable
                key={approval.id}
                onPress={() =>
                  router.push({
                    pathname: "/approvals/[approvalId]",
                    params: { approvalId: approval.id },
                  })
                }
                accessibilityRole="button"
                accessibilityLabel={`Review ${approval.post.title || "content"} for ${approval.post.brand_name}`}
                className="rounded-3xl border border-[#E9E2DA] bg-white shadow-sm shadow-[#292724]/5 active:bg-[#F1E9DF] p-6"
              >
                <View className="mb-3 flex-row items-start justify-between gap-3">
                  <View className="flex-1">
                    <Text className="text-base leading-[24px] font-bold text-[#292724]" variant="controlTitle">
                      {approval.post.title || approval.post.brand_name}
                    </Text>
                    <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      {approval.post.brand_name} ·{" "}
                      {approval.post.platform.replaceAll("_", " ")}
                    </Text>
                  </View>
                  <Text className="rounded-full bg-[#F1E9DF] px-3 py-1 text-[12px] font-semibold capitalize text-[#716A64]" variant="caption">
                    {approval.status}
                  </Text>
                </View>
                <Text
                  numberOfLines={4}
                  className="text-[#716A64] text-[15px] leading-[24px]" variant="button"
                >
                  {approval.post.body}
                </Text>
                <View className="mt-4 flex-row items-center justify-between border-t border-[#E9E2DA] pt-4">
                  <Text className="text-[15px] leading-[24px] text-[#716A64]" variant="body">
                    {formatDate(approval.post.created_at)}
                  </Text>
                  <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="label">
                    View details →
                  </Text>
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
