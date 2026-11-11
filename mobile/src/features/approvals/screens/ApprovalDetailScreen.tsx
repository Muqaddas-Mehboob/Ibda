import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Platform, ScrollView, View } from "react-native";
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
    <View className="flex-1 bg-[#FAF8F4]">
      <Pressable
        onPress={() =>
          router.canGoBack() ? router.back() : router.replace("/dashboard")
        }
        accessibilityRole="button"
        accessibilityLabel="Go back"
        className="mb-4 h-11 w-11 items-center justify-center rounded-full border border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA]"
      >
        <Text className="text-xl text-[#25221F]">‹</Text>
      </Pressable>
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 16, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}
      >
        <Pressable
          onPress={() => router.back()}
          disabled={processing}
          accessibilityRole="button"
          className="mb-7 min-h-[48px] self-start justify-center rounded-[18px]"
        >
          <Text className="text-[14px] leading-[22px] font-medium text-[#25221F]" variant="button">
            ← Back to inbox
          </Text>
        </Pressable>

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator color="#C24A3C" size="large" />
            <Text className="mt-3 text-[#25221F] text-[14px] leading-[22px]" variant="body">
              Loading content...
            </Text>
          </View>
        ) : error && !approval ? (
          <StudioCard className="rounded-3xl border border-[#25221F]/30 bg-[#F4F0EA] p-5">
            <Text className="font-semibold text-[#25221F] text-[14px] leading-[22px]" variant="label">
              Couldn&apos;t load this approval
            </Text>
            <Text className="mt-2 text-[#25221F] text-[14px] leading-[22px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => router.replace("/approvals")}
              className="mt-4 self-start"
            >
              <Text className="font-semibold text-[#C24A3C] text-[14px] leading-[22px]" variant="button">
                Return to inbox
              </Text>
            </Pressable>
          </StudioCard>
        ) : approval ? (
          <>
            <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="secondary">
              CONTENT REVIEW
            </Text>
            <Text className="text-[22px] leading-[30px] tracking-[-0.4px] font-bold text-[#25221F]" variant="page" tone="olive">
              {approval.post.title || "Review content"}
            </Text>
            <Text className="mb-6 mt-3 text-[14px] leading-[22px] text-[#25221F]" variant="body">
              {approval.post.brand_name} ·{" "}
              {approval.post.platform.replaceAll("_", " ")} ·{" "}
              {formatDate(approval.post.created_at)}
            </Text>

            <StudioCard className="mb-6 rounded-3xl border border-[#E2D9CF] bg-[#F4F0EA] p-5">
              <Text className="mb-3 text-[12px] font-bold uppercase tracking-wider text-[#25221F]" variant="eyebrow" tone="secondary">
                CONTENT
              </Text>
              <Text className="text-[14px] leading-7 text-[#25221F]" variant="body">
                {approval.post.body}
              </Text>
            </StudioCard>

            <View className="mb-6 flex-row items-center justify-between rounded-2xl border border-[#E2D9CF] bg-[#FAF8F4] px-4 py-3">
              <Text className="font-medium text-[#25221F] text-[14px] leading-[22px]" variant="label">Status</Text>
              <Text className="font-bold capitalize text-[#25221F] text-[14px] leading-[22px]" variant="label">
                {approval.status.replaceAll("_", " ")}
              </Text>
            </View>

            {!!error && (
              <Text accessibilityRole="alert" className="mb-4 text-[#25221F] text-[14px] leading-[22px]" variant="body">
                {error}
              </Text>
            )}

            {approval.status === "pending" ? (
              <View className="gap-3">
                <Pressable
                  onPress={() => void submitDecision("approve")}
                  disabled={processing}
                  accessibilityRole="button"
                  className={`min-h-[48px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-3 ${
                    processing ? "opacity-70" : ""
                  }`}
                >
                  {processing ? (
                    <ActivityIndicator color="#FAF8F4" />
                  ) : (
                    <Text className="font-bold text-[#FAF8F4] text-[14px] leading-[22px]" variant="label">
                      Approve content
                    </Text>
                  )}
                </Pressable>
                <Pressable
                  onPress={confirmReject}
                  disabled={processing}
                  accessibilityRole="button"
                  className="min-h-[48px] items-center justify-center rounded-[18px] border border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA] px-5 py-3"
                >
                  <Text className="font-bold text-[#25221F] text-[14px] leading-[22px]" variant="button">
                    Reject content
                  </Text>
                </Pressable>
              </View>
            ) : (
              <Text className="rounded-2xl bg-[#F4F0EA] p-4 text-center font-semibold capitalize text-[#25221F] text-[14px] leading-[22px]" variant="label">
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
