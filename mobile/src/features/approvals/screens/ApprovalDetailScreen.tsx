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
        className="mb-8 h-11 w-11 items-center justify-center rounded-full border border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
      >
        <Text className="text-xl text-[#716A64]">‹</Text>
      </Pressable>
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 36, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}
      >
        <Pressable
          onPress={() => router.back()}
          disabled={processing}
          accessibilityRole="button"
          className="mb-7 min-h-[54px] self-start justify-center rounded-[18px]"
        >
          <Text className="text-base leading-[24px] font-medium text-[#716A64]" variant="button">
            ← Back to inbox
          </Text>
        </Pressable>

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator color="#C24A3C" size="large" />
            <Text className="mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Loading content...
            </Text>
          </View>
        ) : error && !approval ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn&apos;t load this approval
            </Text>
            <Text className="mt-2 text-[#B04438] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => router.replace("/approvals")}
              className="mt-4 self-start"
            >
              <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="button">
                Return to inbox
              </Text>
            </Pressable>
          </StudioCard>
        ) : approval ? (
          <>
            <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="secondary">
              CONTENT REVIEW
            </Text>
            <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
              {approval.post.title || "Review content"}
            </Text>
            <Text className="mb-6 mt-3 text-base leading-[24px] text-[#716A64]" variant="body">
              {approval.post.brand_name} ·{" "}
              {approval.post.platform.replaceAll("_", " ")} ·{" "}
              {formatDate(approval.post.created_at)}
            </Text>

            <StudioCard className="mb-6 rounded-3xl border border-[#E9E2DA] bg-white p-5">
              <Text className="mb-3 text-[12px] font-bold uppercase tracking-wider text-[#716A64]" variant="eyebrow" tone="secondary">
                CONTENT
              </Text>
              <Text className="text-base leading-7 text-[#292724]" variant="body">
                {approval.post.body}
              </Text>
            </StudioCard>

            <View className="mb-6 flex-row items-center justify-between rounded-2xl border border-[#E9E2DA] bg-white px-4 py-3">
              <Text className="font-medium text-[#716A64] text-[15px] leading-[24px]" variant="label">Status</Text>
              <Text className="font-bold capitalize text-[#292724] text-[15px] leading-[24px]" variant="label">
                {approval.status.replaceAll("_", " ")}
              </Text>
            </View>

            {!!error && (
              <Text accessibilityRole="alert" className="mb-4 text-[#B04438] text-[15px] leading-[24px]" variant="body">
                {error}
              </Text>
            )}

            {approval.status === "pending" ? (
              <View className="gap-3">
                <Pressable
                  onPress={() => void submitDecision("approve")}
                  disabled={processing}
                  accessibilityRole="button"
                  className={`min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-4 ${
                    processing ? "opacity-70" : ""
                  }`}
                >
                  {processing ? (
                    <ActivityIndicator color="#FFFFFF" />
                  ) : (
                    <Text className="font-bold text-white text-[15px] leading-[24px]" variant="label">
                      Approve content
                    </Text>
                  )}
                </Pressable>
                <Pressable
                  onPress={confirmReject}
                  disabled={processing}
                  accessibilityRole="button"
                  className="min-h-[54px] items-center justify-center rounded-[18px] border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-5 py-4"
                >
                  <Text className="font-bold text-[#A33D34] text-[15px] leading-[24px]" variant="button">
                    Reject content
                  </Text>
                </Pressable>
              </View>
            ) : (
              <Text className="rounded-2xl bg-[#F1E9DF] p-4 text-center font-semibold capitalize text-[#716A64] text-[15px] leading-[24px]" variant="label">
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
