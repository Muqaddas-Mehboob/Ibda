import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable } from "../../../components/ui/StudioControls";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, RefreshControl, ScrollView, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { confirmAsync } from "../../../lib/confirm";
import {
  cancelSubscription,
  createPortalSession,
  getSubscriptionPlans,
  getUserSubscription,
  switchSubscriptionPlan,
  verifyCheckoutSession,
  type SubscriptionPlansResponse,
  type PaymentTransaction,
  type UserSubscriptionResponse,
} from "../services/subscription.service";
import type { BillingInterval, PlanId } from "../data/planCatalog";

function formatDate(value: string | null) {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Not available"
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
}

function formatAmount(amountMinor: number | null, currency: string) {
  if (amountMinor === null || !currency) return "Amount unavailable";
  try {
    const formatter = new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    });
    const fractionDigits =
      formatter.resolvedOptions().maximumFractionDigits ?? 2;
    return formatter.format(amountMinor / 10 ** fractionDigits);
  } catch {
    return `${amountMinor} ${currency} minor units`;
  }
}

function formatTransactionType(type: PaymentTransaction["transaction_type"]) {
  return {
    initial_payment: "Initial payment",
    renewal: "Renewal",
    plan_change: "Plan change",
    refund: "Refund",
    other: "Payment",
  }[type];
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View className="mb-5">
      <Text className="mb-3 text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">{title}</Text>
      <View className="overflow-hidden rounded-[24px] border border-[#E9E2DA] bg-white">
        {children}
      </View>
    </View>
  );
}

export function SubscriptionScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    checkout?: string | string[];
    session_id?: string | string[];
  }>();
  const checkoutReturn =
    typeof params.checkout === "string" ? params.checkout : null;
  const checkoutSessionId =
    typeof params.session_id === "string" ? params.session_id : null;
  const [plans, setPlans] = useState<SubscriptionPlansResponse | null>(null);
  const [account, setAccount] = useState<UserSubscriptionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [checkoutSyncStatus, setCheckoutSyncStatus] = useState<
    "syncing" | "confirmed" | "pending" | "failed" | "error"
  >("syncing");
  const [savingAction, setSavingAction] = useState<
    "cancel" | "switch" | "portal" | null
  >(null);
  const [awaitingPortalConfirmation, setAwaitingPortalConfirmation] =
    useState(false);
  const [showPlanOptions, setShowPlanOptions] = useState(false);
  const [selectedPlanChange, setSelectedPlanChange] = useState<{
    planId: PlanId;
    interval: BillingInterval;
  } | null>(null);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const [planResponse, subscriptionResponse] = await Promise.all([
        getSubscriptionPlans(Platform.OS === "web" ? "web" : "mobile"),
        getUserSubscription(),
      ]);
      setPlans(planResponse);
      setAccount(subscriptionResponse);
      setAwaitingPortalConfirmation(
        (awaiting) =>
          awaiting && subscriptionResponse.subscription?.status === "past_due"
      );
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load subscription details."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);
  useEffect(() => {
    if (checkoutReturn !== "success") return;

    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let refreshFailed = false;
    setCheckoutSyncStatus("syncing");

    const refreshCheckoutHistory = async () => {
      try {
        const verification = checkoutSessionId
          ? await verifyCheckoutSession(checkoutSessionId)
          : null;
        const response = await getUserSubscription();
        if (!active) return;
        setAccount(response);
        const subscription = response.subscription;
        const matchingCheckout = response.transactions.find(
          (item) =>
            checkoutSessionId &&
            item.checkout_session_id === checkoutSessionId
        );
        if (
          verification?.status === "failed" ||
          matchingCheckout?.status === "failed"
        ) {
          setCheckoutSyncStatus("failed");
          return;
        }
        const paymentConfirmed = Boolean(
          verification?.status === "success" &&
            verification.payment_status === "succeeded"
        ) || Boolean(
          checkoutSessionId &&
            response.transactions.some(
              (item) =>
                item.checkout_session_id === checkoutSessionId &&
                item.status === "succeeded"
            )
        );
        if (paymentConfirmed) {
          setCheckoutSyncStatus("confirmed");
          return;
        }
      } catch {
        if (!active) return;
        refreshFailed = true;
      }

      if (attempt >= 5) {
        setCheckoutSyncStatus(refreshFailed ? "error" : "pending");
        return;
      }
      attempt += 1;
      timer = setTimeout(() => {
        void refreshCheckoutHistory();
      }, 2000);
    };

    void refreshCheckoutHistory();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [checkoutReturn, checkoutSessionId]);
  const currentPayment = account?.subscription
    ? account.transactions.find(
        (item) =>
          item.subscription_id === account.subscription?.id &&
          item.status === "succeeded"
      )
    : undefined;
  const latestPayment = account?.subscription
    ? account.transactions.find(
        (item) => item.subscription_id === account.subscription?.id
      )
    : undefined;
  const currentSubscription = account?.subscription ?? null;
  const cancelAvailable = Boolean(
    account?.manage_available &&
      currentSubscription &&
      ["active", "past_due"].includes(currentSubscription.status) &&
      !currentSubscription.cancel_at_period_end
  );
  const switchAvailable = Boolean(
    account?.manage_available &&
      currentSubscription?.status === "active" &&
      !currentSubscription.cancel_at_period_end
  );
  const portalAvailable = Boolean(
    account?.manage_available && currentSubscription?.status === "past_due"
  );

  const performCancellation = async (cancelAtPeriodEnd: boolean) => {
    if (savingAction) return;
    setSavingAction("cancel");
    setActionError("");
    setActionMessage("");
    try {
      const result = await cancelSubscription(cancelAtPeriodEnd);
      setActionMessage(
        result.effective_at
          ? `${result.message} Effective date: ${formatDate(result.effective_at)}.`
          : result.message
      );
      await load(true);
    } catch (cancelError) {
      setActionError(
        cancelError instanceof Error
          ? cancelError.message
          : "Unable to cancel this subscription."
      );
    } finally {
      setSavingAction(null);
    }
  };

  const confirmCancellation = async (cancelAtPeriodEnd: boolean) => {
    const message = cancelAtPeriodEnd
      ? "Your subscription will remain active through the current paid period and end on its renewal date. No refund is implied."
      : "This immediately ends subscription access. Any refund is subject to Stripe and the applicable billing terms.";
    const title = cancelAtPeriodEnd
      ? "Cancel at period end?"
      : "Cancel immediately?";

    const confirmed = await confirmAsync(title, message, {
      confirmText: "Confirm cancellation",
      cancelText: "Keep subscription",
      destructive: true,
    });
    if (!confirmed) return;
    void performCancellation(cancelAtPeriodEnd);
  };

  const performPlanSwitch = async () => {
    if (!selectedPlanChange || savingAction) return;
    setSavingAction("switch");
    setActionError("");
    setActionMessage("");
    try {
      const result = await switchSubscriptionPlan(
        selectedPlanChange.planId,
        selectedPlanChange.interval
      );
      setActionMessage(
        `Plan updated. ${result.proration_disclosure}`
      );
      setSelectedPlanChange(null);
      setShowPlanOptions(false);
      await load(true);
    } catch (switchError) {
      setActionError(
        switchError instanceof Error
          ? switchError.message
          : "Unable to change this subscription plan."
      );
    } finally {
      setSavingAction(null);
    }
  };

  const confirmPlanSwitch = async () => {
    if (!selectedPlanChange) return;
    const newPlan = plans?.plans.find(
      (plan) => plan.id === selectedPlanChange.planId
    );
    const price = newPlan?.prices[selectedPlanChange.interval];
    const amount =
      price?.price_minor !== null && price?.currency
        ? formatAmount(price.price_minor, price.currency)
        : "the configured Stripe price";
    const message =
      `Switch to ${newPlan?.name ?? selectedPlanChange.planId} ` +
      `${selectedPlanChange.interval} billing at ${amount}? ` +
      "Stripe may add prorated charges or credits to your upcoming invoice.";

    const confirmed = await confirmAsync("Confirm plan change", message, {
      confirmText: "Confirm plan change",
      cancelText: "Keep current plan",
      webPrompt: message,
    });
    if (!confirmed) return;
    void performPlanSwitch();
  };

  const openBillingPortal = async () => {
    if (savingAction) return;
    setSavingAction("portal");
    setActionError("");
    setActionMessage("");
    let openingBrowser = false;

    try {
      const portal = await createPortalSession(
        Platform.OS === "web" ? "web" : "mobile"
      );
      let portalUrl: URL;
      try {
        portalUrl = new URL(portal.url);
      } catch {
        throw new Error(
          "The payment portal link was invalid. Please try again."
        );
      }
      if (portalUrl.protocol !== "https:") {
        throw new Error(
          "The payment portal link was invalid. Please try again."
        );
      }

      if (Platform.OS === "web") {
        openingBrowser = true;
        window.location.assign(portalUrl.toString());
        return;
      }

      openingBrowser = true;
      await WebBrowser.openAuthSessionAsync(
        portalUrl.toString(),
        Linking.createURL("/subscription")
      );
      setAwaitingPortalConfirmation(true);
      setActionMessage(
        "Checking with Stripe for your updated payment details..."
      );
      await load(true);
    } catch (portalError) {
      setActionError(
        openingBrowser
          ? "Unable to open the payment portal. Please try again."
          : portalError instanceof Error
            ? portalError.message
            : "Unable to open the payment portal."
      );
    } finally {
      setSavingAction(null);
    }
  };

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
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
          router.canGoBack() ? router.back() : router.replace("/settings")
        }
        accessibilityRole="button"
        accessibilityLabel="Go back"
        className="mb-8 h-11 w-11 items-center justify-center rounded-full border border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
      >
        <Text className="text-xl text-[#716A64]">‹</Text>
      </Pressable>
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="secondary">
          YOUR ACCOUNT
        </Text>
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
          Plans & billing
        </Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          View your current plan, validated Stripe pricing, and billing history.
        </Text>

        {checkoutReturn === "success" ? (
          <View className="mb-5 rounded-2xl border border-[#E9E2DA] bg-white p-4">
            <Text className="text-[15px] leading-[23px] text-[#716A64]" variant="body">
              {checkoutSyncStatus === "confirmed"
                ? "Payment confirmed. Your subscription and payment history have been refreshed."
                : checkoutSyncStatus === "pending"
                  ? "Checkout returned to Billing. Payment history will update when Stripe confirms payment. You can pull down to refresh; you do not need to pay again."
                  : checkoutSyncStatus === "failed"
                    ? "Checkout did not complete successfully. No successful payment was recorded. Review payment history below or start a new checkout."
                  : checkoutSyncStatus === "error"
                    ? "Could not refresh billing right now. Pull down to refresh your subscription and payment history. You do not need to pay again."
                    : "Checkout returned to Billing. Refreshing your subscription and payment history from the backend."}
            </Text>
            {checkoutSyncStatus === "syncing" ? (
              <ActivityIndicator
                className="mt-3 self-start"
                color="#C24A3C"
                accessibilityLabel="Refreshing payment history"
              />
            ) : null}
          </View>
        ) : checkoutReturn === "cancelled" ? (
          <View className="mb-5 rounded-2xl border border-[#E9E2DA] bg-white p-4">
            <Text className="text-[15px] leading-[23px] text-[#716A64]" variant="body">
              Checkout was canceled. Your subscription status below is
              refreshed from the backend.
            </Text>
          </View>
        ) : null}

        {loading ? (
          <View className="flex-row items-center gap-3 rounded-2xl border border-[#E9E2DA] bg-white p-5">
            <ActivityIndicator color="#C24A3C" />
            <Text className="text-[#716A64] text-[15px] leading-[24px]" variant="body">Loading billing details...</Text>
          </View>
        ) : null}

        {error ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text className="text-[#A33D34] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-3 min-h-[54px] items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-4"
            >
              <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </View>
        ) : null}
        {actionError ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text accessibilityRole="alert" className="text-[#A33D34] text-[15px] leading-[24px]" variant="body">
              {actionError}
            </Text>
          </View>
        ) : null}
        {actionMessage ? (
          <View className="mb-5 rounded-2xl border border-[#B8DEC5] bg-white p-4">
            <Text className="text-[#286B40] text-[15px] leading-[24px]" variant="body">{actionMessage}</Text>
          </View>
        ) : null}

        {!loading && !error && plans && account ? (
          <>
            <Section title="Current plan">
              <View className="p-4">
                <View className="flex-row items-center justify-between">
                  <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
                    {!account.subscription && account.plan_id === "free"
                      ? "Free"
                      : plans.plans.find(
                          (plan) => plan.id === account.subscription?.plan_id
                        )?.name ??
                        (account.subscription?.plan_id.startsWith("premium")
                          ? "Pro"
                          : account.subscription?.plan_id ?? "Free")}
                  </Text>
                  <View className="rounded-full bg-[#F1E9DF] px-3 py-1">
                    <Text className="text-[12px] font-bold uppercase text-[#716A64]" variant="caption">
                      {account.subscription?.status ?? "free"}
                    </Text>
                  </View>
                </View>
                {account.subscription ? (
                  <>
                    <Text className="mt-3 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      Billing interval:{" "}
                      {account.subscription.billing_interval === "none"
                        ? "Not specified"
                        : account.subscription.billing_interval}
                    </Text>
                    <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      {account.subscription.cancel_at_period_end
                        ? "Subscription ends: "
                        : account.subscription.status === "canceled"
                          ? "Canceled on: "
                          : account.subscription.status === "active"
                            ? "Next renewal: "
                            : "Current period ends: "}
                      {formatDate(
                        account.subscription.cancel_at_period_end
                          ? account.subscription.current_period_end
                          : account.subscription.status === "canceled"
                            ? account.subscription.canceled_at
                            : account.subscription.current_period_end
                      )}
                    </Text>
                    <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      Current price:{" "}
                      {currentPayment
                        ? formatAmount(
                            currentPayment.amount_minor,
                            currentPayment.currency
                          )
                        : (() => {
                            const currentPlan = plans.plans.find(
                              (plan) =>
                                plan.id === account.subscription?.plan_id
                            );
                            const interval =
                              account.subscription?.billing_interval;
                            const price =
                              interval === "monthly" || interval === "annual"
                                ? currentPlan?.prices[interval]
                                : undefined;
                            return price?.price_minor !== null &&
                              price?.currency
                              ? formatAmount(
                                  price.price_minor,
                                  price.currency
                                )
                              : "Not available";
                          })()}
                    </Text>
                    {account.subscription.cancel_at_period_end ? (
                      <Text className="mt-2 text-[15px] leading-[24px] font-semibold text-[#B04438]" variant="label">
                        Active until{" "}
                        {formatDate(account.subscription.current_period_end)}.
                        Cancellation is scheduled for that date.
                      </Text>
                    ) : account.subscription.provider === "stripe" &&
                      account.subscription.status === "active" ? (
                      <Text className="mt-2 text-[15px] leading-[24px] font-semibold text-[#27824A]" variant="label">
                        Subscription renews on{" "}
                        {formatDate(account.subscription.current_period_end)}.
                      </Text>
                    ) : null}
                    {account.subscription.status === "pending" ? (
                      <Text className="mt-2 text-[15px] leading-[24px] font-semibold text-[#9A6A14]" variant="label">
                        Payment is pending Stripe confirmation. You can resume
                        the existing checkout below.
                      </Text>
                    ) : null}
                    {account.subscription.status === "past_due" ||
                    latestPayment?.status === "failed" ? (
                      <Text className="mt-2 text-[15px] leading-[24px] font-semibold text-[#B04438]" variant="label">
                        Payment failed or is overdue. Update the payment method
                        below before making plan changes.
                      </Text>
                    ) : null}
                    {portalAvailable ? (
                      <View className="mt-5">
                        <Pressable
                          onPress={() => void openBillingPortal()}
                          disabled={savingAction !== null}
                          accessibilityRole="button"
                          className={`min-h-[54px] items-center justify-center rounded-[18px] px-4 ${
                            savingAction ? "bg-[#C8BEB5]" : "bg-[#292724]"
                          }`}
                        >
                          <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                            {savingAction === "portal"
                              ? "Opening payment portal..."
                              : "Update payment method"}
                          </Text>
                        </Pressable>
                        {awaitingPortalConfirmation &&
                        currentSubscription?.status === "past_due" ? (
                          <Text className="mt-2 text-[15px] leading-[23px] text-[#8A6412]" variant="body">
                            Waiting for Stripe to confirm your updated payment
                            details. This can take a moment — pull to refresh
                            Billing to check again.
                          </Text>
                        ) : null}
                      </View>
                    ) : null}
                    {currentPayment ? (
                      <View className="mt-4 rounded-xl bg-[#F7F4EF] p-3">
                        <Text className="text-[12px] font-bold uppercase tracking-[1px] text-[#716A64]" variant="eyebrow" tone="secondary">
                          Latest confirmed payment
                        </Text>
                        <View className="mt-2 flex-row items-center justify-between gap-3">
                          <Text className="text-[15px] leading-[24px] capitalize text-[#716A64]" variant="body">
                            {currentPayment.status}
                          </Text>
                          {currentPayment.amount_minor !== null &&
                          currentPayment.currency ? (
                            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                              {formatAmount(
                                currentPayment.amount_minor,
                                currentPayment.currency
                              )}
                            </Text>
                          ) : null}
                        </View>
                        <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                          {formatDate(
                            currentPayment.occurred_at ??
                              currentPayment.created_at
                          )}
                        </Text>
                      </View>
                    ) : null}
                    {latestPayment &&
                    latestPayment.status !== "succeeded" ? (
                      <View className="mt-4 rounded-xl bg-[#FCE5E1] p-3">
                        <Text className="text-[12px] font-bold uppercase tracking-[1px] text-[#A33D34]" variant="eyebrow" tone="secondary">
                          Latest payment status
                        </Text>
                        <Text className="mt-2 font-semibold capitalize text-[#A33D34] text-[15px] leading-[24px]" variant="label">
                          {latestPayment.status}
                        </Text>
                      </View>
                    ) : null}
                    {cancelAvailable ? (
                      <View className="mt-5 gap-2">
                        <Pressable
                          onPress={() => void confirmCancellation(true)}
                          disabled={savingAction !== null}
                          accessibilityRole="button"
                          className={`min-h-[54px] items-center justify-center rounded-[18px] px-4 ${
                            savingAction ? "bg-[#C8BEB5]" : "bg-[#B04438]"
                          }`}
                        >
                          <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                            {savingAction === "cancel"
                              ? "Updating subscription..."
                              : "Cancel Subscription"}
                          </Text>
                        </Pressable>
                        <Pressable
                          onPress={() => void confirmCancellation(false)}
                          disabled={savingAction !== null}
                          accessibilityRole="button"
                          className="min-h-[54px] items-center justify-center rounded-[18px] border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-4"
                        >
                          <Text className="font-semibold text-[#B04438] text-[15px] leading-[24px]" variant="button">
                            Cancel immediately instead
                          </Text>
                        </Pressable>
                      </View>
                    ) : null}
                    {switchAvailable ? (
                      <Pressable
                        onPress={() => {
                          setShowPlanOptions((visible) => !visible);
                          setSelectedPlanChange(null);
                        }}
                        disabled={savingAction !== null}
                        accessibilityRole="button"
                        className="mt-3 min-h-[54px] items-center justify-center rounded-[18px] border border-[#C24A3C] bg-white px-4"
                      >
                        <Text className="font-bold text-[#B04438] text-[15px] leading-[24px]" variant="button">
                          {showPlanOptions ? "Hide plans" : "Switch Plan"}
                        </Text>
                      </Pressable>
                    ) : null}
                  </>
                ) : (
                  <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                    No paid subscription is active on this account.
                  </Text>
                )}
              </View>
              <View className="border-t border-[#E9E2DA] px-4 py-3">
                <Text className="text-[15px] leading-[23px] text-[#716A64]" variant="body">
                  {account.subscription?.cancel_at_period_end
                    ? `Your plan remains active until ${formatDate(
                        account.subscription.current_period_end
                      )}.`
                    : account.checkout_eligible && plans.checkout_available
                    ? "Select a configured plan and billing interval to begin Stripe test-mode checkout. Subscription access is updated only after verified Stripe events."
                    : account.subscription?.status === "pending"
                      ? "Use the existing pending checkout; a second subscription will not be created."
                      : account.manage_available
                        ? "Use the subscription management actions above. A duplicate checkout is not available while this subscription is active."
                    : "Checkout is unavailable until test-mode Stripe, a valid recurring Price, and fixed return URLs are configured on the backend."}
                </Text>
              </View>
            </Section>

            {showPlanOptions && switchAvailable ? (
              <Section title="Switch plan">
                <View className="p-4">
                  <Text className="mb-3 text-[15px] leading-[23px] text-[#716A64]" variant="body">
                    Choose a new plan and billing interval. Stripe applies
                    proration as a charge or credit on the upcoming invoice.
                  </Text>
                  {plans.plans.map((plan) => (
                    <View key={plan.id} className="mb-4 last:mb-0">
                      <Text className="font-bold text-[#292724] text-[15px] leading-[24px]" variant="label">
                        {plan.name}
                      </Text>
                      {(["monthly", "annual"] as const).map((interval) => {
                        const price = plan.prices[interval];
                        const current =
                          plan.id === currentSubscription?.plan_id &&
                          interval === currentSubscription.billing_interval;
                        if (current || !price.checkout_available) return null;
                        return (
                          <Pressable
                            key={`${plan.id}-${interval}`}
                            onPress={() =>
                              setSelectedPlanChange({
                                planId: plan.id,
                                interval,
                              })
                            }
                            disabled={savingAction !== null}
                            accessibilityRole="button"
                            className="mt-2 min-h-[54px] flex-row items-center justify-between rounded-[18px] border border-[#E9E2DA] px-3"
                          >
                            <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="button">
                              Switch to {interval}
                            </Text>
                            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="button">
                              {price.price_minor !== null && price.currency
                                ? `${formatAmount(
                                    price.price_minor,
                                    price.currency
                                  )} / ${interval === "monthly" ? "month" : "year"}`
                                : "Price unavailable"}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  ))}
                  {selectedPlanChange ? (
                    <View className="mt-2 rounded-xl bg-[#F1E9DF] p-4">
                      <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="label">
                        Stripe will apply prorated charges or credits based on
                        the remaining billing period. The exact amount is
                        calculated by Stripe before the next invoice.
                      </Text>
                      <Pressable
                        onPress={() => void confirmPlanSwitch()}
                        disabled={savingAction !== null}
                        accessibilityRole="button"
                        className="mt-3 min-h-[54px] items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-4"
                      >
                        <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                          {savingAction === "switch"
                            ? "Updating plan..."
                            : "Confirm plan change"}
                        </Text>
                      </Pressable>
                    </View>
                  ) : null}
                </View>
              </Section>
            ) : null}

            {account.checkout_eligible ? (
            <Section title="Available plans">
              {plans.plans.map((plan, index) => (
                <View
                  key={plan.id}
                  className={`p-4 ${
                    index ? "border-t border-[#E9E2DA]" : ""
                  }`}
                >
                  <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                    {plan.name}
                  </Text>
                  {(["monthly", "annual"] as const).map((interval) => {
                    const price = plan.prices[interval];
                    return (
                      <Text
                        key={interval}
                        className="mt-2 text-[15px] leading-[24px] text-[#716A64]" variant="body"
                      >
                        {interval === "monthly" ? "Monthly" : "Annual"}:{" "}
                        {price.price_minor !== null && price.currency
                          ? formatAmount(price.price_minor, price.currency)
                          : "Price unavailable"}
                        {price.price_minor !== null && price.currency
                          ? interval === "monthly"
                            ? " / month"
                            : " / year"
                          : ""}
                        {!price.checkout_available
                          ? " (checkout unavailable)"
                          : ""}
                      </Text>
                    );
                  })}
                  <Text className="mt-2 text-[15px] leading-[23px] text-[#716A64]" variant="body">
                    {plan.features_configured
                      ? plan.features.length
                        ? plan.features.join(" · ")
                        : "No features are listed for this plan."
                      : "Plan features and limits have not been configured."}
                  </Text>
                  <View className="mt-4 flex-row gap-2">
                    <Pressable
                      onPress={() =>
                        router.push({
                          pathname: "/subscription/monthly",
                          params: { plan: plan.id },
                        })
                      }
                      accessibilityRole="button"
                      accessibilityLabel={`View ${plan.name} monthly pricing`}
                      className="min-h-[54px] flex-1 items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-3"
                    >
                      <Text className="text-center text-[15px] leading-[24px] font-bold text-white" variant="button">
                        Monthly pricing
                      </Text>
                    </Pressable>
                    <Pressable
                      onPress={() =>
                        router.push({
                          pathname: "/subscription/annual",
                          params: { plan: plan.id },
                        })
                      }
                      accessibilityRole="button"
                      accessibilityLabel={`View ${plan.name} annual pricing`}
                      className="min-h-[54px] flex-1 items-center justify-center rounded-[18px] border border-[#C24A3C] bg-white px-3"
                    >
                      <Text className="text-center text-[15px] leading-[24px] font-bold text-[#B94E45]" variant="button">
                        Annual pricing
                      </Text>
                    </Pressable>
                  </View>
                </View>
              ))}
            </Section>
            ) : currentSubscription?.status === "pending" ? (
              <Section title="Pending checkout">
                <View className="p-4">
                  <Text className="text-[#716A64] text-[15px] leading-[24px]" variant="body">
                    The previous checkout is still pending. Resume it to avoid
                    creating a duplicate subscription.
                  </Text>
                  <Pressable
                    onPress={() =>
                      router.push({
                        pathname:
                          currentSubscription.billing_interval === "annual"
                            ? "/subscription/annual"
                            : "/subscription/monthly",
                        params: { plan: currentSubscription.plan_id },
                      })
                    }
                    accessibilityRole="button"
                    className="mt-3 min-h-[54px] items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-4"
                  >
                    <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                      Resume pending checkout
                    </Text>
                  </Pressable>
                </View>
              </Section>
            ) : null}

            <Section title="Payment history">
              {account.transactions.length ? (
                account.transactions.map((item, index) => (
                  <View
                    key={item.id}
                    className={`p-4 ${
                      index ? "border-t border-[#E9E2DA]" : ""
                    }`}
                  >
                    <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                      {item.plan_name ||
                        plans.plans.find((plan) => plan.id === item.plan_id)
                          ?.name ||
                        item.plan_id}{" "}
                      · {formatTransactionType(item.transaction_type)} · {item.billing_interval}
                    </Text>
                    <View className="mt-2 flex-row items-center justify-between gap-3">
                      <Text className="text-[15px] leading-[24px] font-semibold capitalize text-[#716A64]" variant="label">
                        {item.status}
                      </Text>
                      {item.amount_minor !== null && item.currency ? (
                        <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                          {formatAmount(item.amount_minor, item.currency)}
                        </Text>
                      ) : null}
                    </View>
                    <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      {formatDate(item.paid_at ?? item.occurred_at ?? item.created_at)}
                    </Text>
                    {item.payment_method_brand && item.payment_method_last4 ? (
                      <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                        {item.payment_method_brand} ending in {item.payment_method_last4}
                      </Text>
                    ) : null}
                    {item.receipt_url ? (
                      <Pressable
                        onPress={() => void Linking.openURL(item.receipt_url)}
                        accessibilityRole="link"
                        accessibilityLabel="Open invoice receipt"
                        className="mt-2 min-h-10 justify-center"
                      >
                        <Text className="font-semibold text-[#B94E45] text-[15px] leading-[24px]" variant="button">
                          View invoice
                        </Text>
                      </Pressable>
                    ) : null}
                  </View>
                ))
              ) : (
                <Text className="p-4 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                  No payment transactions yet.
                </Text>
              )}
            </Section>
          </>
        ) : null}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
