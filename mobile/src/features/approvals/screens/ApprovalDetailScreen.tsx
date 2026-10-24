import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  getApproval,
  reviewApproval,
  type Approval,
  type ApprovalDecision,
} from "../services/approval.service";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : date.toLocaleString();
}

export function ApprovalDetailScreen() {
  const router = useRouter();
  const { approvalId: routeApprovalId } =
    useLocalSearchParams<{ approvalId: string }>();
  const approvalId =
    typeof routeApprovalId === "string" ? routeApprovalId : "";
  const [approval, setApproval] = useState<Approval | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError("");
      if (!approvalId) {
        setError("This approval link is missing its ID.");
        setLoading(false);
        return;
      }

      try {
        const result = await getApproval(approvalId);
        if (active) setApproval(result);
      } catch (loadError) {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load this approval."
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [approvalId]);

  const submitDecision = async (decision: ApprovalDecision) => {
    if (!approval || processing) return;
    setProcessing(true);
    setError("");

    try {
      const result = await reviewApproval(approval.id, decision);
      setApproval(result);
      router.replace("/approvals");
    } catch (actionError) {
      setError(
        actionError instanceof Error
          ? actionError.message
          : `Unable to ${decision} this content. Please try again.`
      );
    } finally {
      setProcessing(false);
    }
  };

  const confirmReject = () => {
    if (Platform.OS === "web" && typeof window !== "undefined") {
      if (window.confirm("Reject this content? This cannot be undone.")) {
        void submitDecision("reject");
      }
      return;
    }

    Alert.alert(
      "Reject this content?",
      "This will mark the content as rejected.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Reject",
          style: "destructive",
          onPress: () => void submitDecision("reject"),
        },
      ]
    );
  };

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 32, paddingBottom: 40 }}
      >
        <Pressable
          onPress={() => router.back()}
          disabled={processing}
          accessibilityRole="button"
          className="mb-7 min-h-11 self-start justify-center"
        >
          <Text className="text-base font-medium text-[#705B52]">
            ← Back to inbox
          </Text>
        </Pressable>

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator color="#FF6B5F" size="large" />
            <Text className="mt-3 text-[#827970]">
              Loading content...
            </Text>
          </View>
        ) : error && !approval ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
            <Text className="font-semibold text-[#24221F]">
              Couldn&apos;t load this approval
            </Text>
            <Text className="mt-2 leading-5 text-[#B04438]">{error}</Text>
            <Pressable
              onPress={() => router.replace("/approvals")}
              className="mt-4 self-start"
            >
              <Text className="font-semibold text-[#FF6B5F]">
                Return to inbox
              </Text>
            </Pressable>
          </View>
        ) : approval ? (
          <>
            <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
              CONTENT REVIEW
            </Text>
            <Text className="text-4xl font-bold text-[#24221F]">
              {approval.post.title || "Review content"}
            </Text>
            <Text className="mb-6 mt-3 text-base text-[#827970]">
              {approval.post.brand_name} ·{" "}
              {approval.post.platform.replaceAll("_", " ")} ·{" "}
              {formatDate(approval.post.created_at)}
            </Text>

            <View className="mb-6 rounded-3xl border border-[#EAE4DC] bg-white p-6">
              <Text className="mb-3 text-xs font-bold uppercase tracking-wider text-[#827970]">
                CONTENT
              </Text>
              <Text className="text-base leading-7 text-[#24221F]">
                {approval.post.body}
              </Text>
            </View>

            <View className="mb-6 flex-row items-center justify-between rounded-2xl border border-[#EAE4DC] bg-white px-4 py-3">
              <Text className="font-medium text-[#827970]">Status</Text>
              <Text className="font-bold capitalize text-[#24221F]">
                {approval.status.replaceAll("_", " ")}
              </Text>
            </View>

            {!!error && (
              <Text accessibilityRole="alert" className="mb-4 text-[#B04438]">
                {error}
              </Text>
            )}

            {approval.status === "pending" ? (
              <View className="gap-3">
                <Pressable
                  onPress={() => void submitDecision("approve")}
                  disabled={processing}
                  accessibilityRole="button"
                  className={`min-h-14 flex-row items-center justify-center rounded-2xl bg-[#FF6B5F] px-5 py-4 ${
                    processing ? "opacity-70" : ""
                  }`}
                >
                  {processing ? (
                    <ActivityIndicator color="#FFFFFF" />
                  ) : (
                    <Text className="font-bold text-white">
                      Approve content
                    </Text>
                  )}
                </Pressable>
                <Pressable
                  onPress={confirmReject}
                  disabled={processing}
                  accessibilityRole="button"
                  className="min-h-14 items-center justify-center rounded-2xl border border-[#EAE4DC] bg-white px-5 py-4"
                >
                  <Text className="font-bold text-[#A33D34]">
                    Reject content
                  </Text>
                </Pressable>
              </View>
            ) : (
              <Text className="rounded-2xl bg-[#F3EEE8] p-4 text-center font-semibold capitalize text-[#705B52]">
                This content has already been {approval.status}.
              </Text>
            )}
          </>
        ) : null}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
