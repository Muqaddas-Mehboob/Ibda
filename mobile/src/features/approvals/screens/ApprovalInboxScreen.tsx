import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
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
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 40, paddingBottom: 32 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#FF6B5F"
          />
        }
      >
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          CONTENT WORKSPACE
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">
          Approval Inbox
        </Text>
        <Text className="mb-7 mt-3 text-base leading-6 text-[#827970]">
          Review content from your brands before it moves to the next step.
        </Text>

        <View
          accessibilityRole="tablist"
          className="mb-6 flex-row rounded-2xl border border-[#EAE4DC] bg-white p-1"
        >
          {FILTERS.map((item) => {
            const selected = filter === item.value;
            return (
              <Pressable
                key={item.value}
                onPress={() => setFilter(item.value)}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                className={`min-h-11 flex-1 items-center justify-center rounded-xl px-2 ${
                  selected ? "bg-[#24221F]" : ""
                }`}
              >
                <Text
                  className={`text-sm font-semibold ${
                    selected ? "text-white" : "text-[#827970]"
                  }`}
                >
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator color="#FF6B5F" size="large" />
            <Text className="mt-3 text-[#827970]">Loading approvals...</Text>
          </View>
        ) : error ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
            <Text className="font-semibold text-[#24221F]">
              Couldn&apos;t load approvals
            </Text>
            <Text className="mt-2 leading-5 text-[#B04438]">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-11 self-start justify-center rounded-xl bg-[#24221F] px-4 py-2"
            >
              <Text className="font-semibold text-white">Try again</Text>
            </Pressable>
          </View>
        ) : approvals.length === 0 ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-6">
            <Text className="text-xl font-bold text-[#24221F]">
              {filter === "pending"
                ? "You’re all caught up"
                : `No ${filter} content yet`}
            </Text>
            <Text className="mt-2 leading-6 text-[#827970]">
              {EMPTY_MESSAGES[filter]}
            </Text>
          </View>
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
                className="rounded-3xl border border-[#EAE4DC] bg-white p-5"
              >
                <View className="mb-3 flex-row items-start justify-between gap-3">
                  <View className="flex-1">
                    <Text className="text-base font-bold text-[#24221F]">
                      {approval.post.title || approval.post.brand_name}
                    </Text>
                    <Text className="mt-1 text-sm text-[#827970]">
                      {approval.post.brand_name} ·{" "}
                      {approval.post.platform.replaceAll("_", " ")}
                    </Text>
                  </View>
                  <Text className="rounded-full bg-[#F3EEE8] px-3 py-1 text-xs font-semibold capitalize text-[#705B52]">
                    {approval.status}
                  </Text>
                </View>
                <Text
                  numberOfLines={4}
                  className="leading-6 text-[#51483F]"
                >
                  {approval.post.body}
                </Text>
                <View className="mt-4 flex-row items-center justify-between border-t border-[#EAE4DC] pt-4">
                  <Text className="text-sm text-[#827970]">
                    {formatDate(approval.post.created_at)}
                  </Text>
                  <Text className="font-semibold text-[#FF6B5F]">
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
