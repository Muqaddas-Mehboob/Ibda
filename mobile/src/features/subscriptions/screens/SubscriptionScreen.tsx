import { useCallback, useState } from "react";
import {
  Alert,
  ActivityIndicator,
  Pressable,
  Platform,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  cancelSubscription,
  getSubscriptionPlans,
  getUserSubscription,
  switchSubscriptionPlan,
  type SubscriptionPlansResponse,
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

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View className="mb-5">
      <Text className="mb-3 text-lg font-bold text-[#24221F]">{title}</Text>
      <View className="overflow-hidden rounded-2xl border border-[#EAE4DC] bg-white">
        {children}
      </View>
    </View>
  );
}

export function SubscriptionScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ checkout?: string | string[] }>();
  const checkoutReturn =
    typeof params.checkout === "string" ? params.checkout : null;
  const [plans, setPlans] = useState<SubscriptionPlansResponse | null>(null);
  const [account, setAccount] = useState<UserSubscriptionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [savingAction, setSavingAction] = useState<"cancel" | "switch" | null>(
    null
  );
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

  const confirmCancellation = (cancelAtPeriodEnd: boolean) => {
    const message = cancelAtPeriodEnd
      ? "Your subscription will remain active through the current paid period and end on its renewal date. No refund is implied."
      : "This immediately ends subscription access. Any refund is subject to Stripe and the applicable billing terms.";
    const title = cancelAtPeriodEnd
      ? "Cancel at period end?"
      : "Cancel immediately?";

    if (Platform.OS === "web") {
      if (typeof window !== "undefined" && window.confirm(`${title}\n\n${message}`)) {
        void performCancellation(cancelAtPeriodEnd);
      }
      return;
    }

    Alert.alert(title, message, [
      { text: "Keep subscription", style: "cancel" },
      {
        text: "Confirm cancellation",
        style: "destructive",
        onPress: () => void performCancellation(cancelAtPeriodEnd),
      },
    ]);
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

  const confirmPlanSwitch = () => {
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

    if (Platform.OS === "web") {
      if (typeof window !== "undefined" && window.confirm(message)) {
        void performPlanSwitch();
      }
      return;
    }

    Alert.alert("Confirm plan change", message, [
      { text: "Keep current plan", style: "cancel" },
      {
        text: "Confirm plan change",
        onPress: () => void performPlanSwitch(),
      },
    ]);
  };

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
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
          YOUR ACCOUNT
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">
          Plans & billing
        </Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#827970]">
          View your current plan, validated Stripe pricing, and billing history.
        </Text>

        {checkoutReturn === "success" ? (
          <View className="mb-5 rounded-2xl border border-[#EAE4DC] bg-white p-4">
            <Text className="text-sm leading-5 text-[#51483F]">
              You returned from checkout. Your current plan below is refreshed
              from the backend; access changes only after Stripe confirms the
              subscription.
            </Text>
          </View>
        ) : checkoutReturn === "cancelled" ? (
          <View className="mb-5 rounded-2xl border border-[#EAE4DC] bg-white p-4">
            <Text className="text-sm leading-5 text-[#51483F]">
              Checkout was canceled. Your subscription status below is
              refreshed from the backend.
            </Text>
          </View>
        ) : null}

        {loading ? (
          <View className="flex-row items-center gap-3 rounded-2xl border border-[#EAE4DC] bg-white p-5">
            <ActivityIndicator color="#FF6B5F" />
            <Text className="text-[#827970]">Loading billing details...</Text>
          </View>
        ) : null}

        {error ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text className="leading-5 text-[#A33D34]">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-3 min-h-11 items-center justify-center rounded-xl bg-[#FF6B5F] px-4"
            >
              <Text className="font-bold text-white">Try again</Text>
            </Pressable>
          </View>
        ) : null}
        {actionError ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text accessibilityRole="alert" className="leading-5 text-[#A33D34]">
              {actionError}
            </Text>
          </View>
        ) : null}
        {actionMessage ? (
          <View className="mb-5 rounded-2xl border border-[#B8DEC5] bg-white p-4">
            <Text className="leading-5 text-[#286B40]">{actionMessage}</Text>
          </View>
        ) : null}

        {!loading && !error && plans && account ? (
          <>
            <Section title="Current plan">
              <View className="p-4">
                <View className="flex-row items-center justify-between">
                  <Text className="text-xl font-bold text-[#24221F]">
                    {!account.subscription && account.plan_id === "free"
                      ? "Free"
                      : plans.plans.find(
                          (plan) => plan.id === account.subscription?.plan_id
                        )?.name ??
                        (account.subscription?.plan_id.startsWith("premium")
                          ? "Pro"
                          : account.subscription?.plan_id ?? "Free")}
                  </Text>
                  <View className="rounded-full bg-[#F3EEE8] px-3 py-1">
                    <Text className="text-xs font-bold uppercase text-[#827970]">
                      {account.subscription?.status ?? "free"}
                    </Text>
                  </View>
                </View>
                {account.subscription ? (
                  <>
                    <Text className="mt-3 text-sm text-[#827970]">
                      Billing interval:{" "}
                      {account.subscription.billing_interval === "none"
                        ? "Not specified"
                        : account.subscription.billing_interval}
                    </Text>
                    <Text className="mt-1 text-sm text-[#827970]">
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
                    <Text className="mt-1 text-sm text-[#827970]">
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
                      <Text className="mt-2 text-sm font-semibold text-[#B04438]">
                        Active until{" "}
                        {formatDate(account.subscription.current_period_end)}.
                        Cancellation is scheduled for that date.
                      </Text>
                    ) : account.subscription.provider === "stripe" &&
                      account.subscription.status === "active" ? (
                      <Text className="mt-2 text-sm font-semibold text-[#27824A]">
                        Subscription renews on{" "}
                        {formatDate(account.subscription.current_period_end)}.
                      </Text>
                    ) : null}
                    {account.subscription.status === "pending" ? (
                      <Text className="mt-2 text-sm font-semibold text-[#9A6A14]">
                        Payment is pending Stripe confirmation. You can resume
                        the existing checkout below.
                      </Text>
                    ) : null}
                    {account.subscription.status === "past_due" ||
                    latestPayment?.status === "failed" ? (
                      <Text className="mt-2 text-sm font-semibold text-[#B04438]">
                        Payment failed or is overdue. Update the payment method
                        in Stripe before making plan changes.
                      </Text>
                    ) : null}
                    {currentPayment ? (
                      <View className="mt-4 rounded-xl bg-[#F8F5F0] p-3">
                        <Text className="text-xs font-bold uppercase tracking-[1px] text-[#827970]">
                          Latest confirmed payment
                        </Text>
                        <View className="mt-2 flex-row items-center justify-between gap-3">
                          <Text className="text-sm capitalize text-[#51483F]">
                            {currentPayment.status}
                          </Text>
                          {currentPayment.amount_minor !== null &&
                          currentPayment.currency ? (
                            <Text className="font-semibold text-[#24221F]">
                              {formatAmount(
                                currentPayment.amount_minor,
                                currentPayment.currency
                              )}
                            </Text>
                          ) : null}
                        </View>
                        <Text className="mt-1 text-sm text-[#827970]">
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
                        <Text className="text-xs font-bold uppercase tracking-[1px] text-[#A33D34]">
                          Latest payment status
                        </Text>
                        <Text className="mt-2 font-semibold capitalize text-[#A33D34]">
                          {latestPayment.status}
                        </Text>
                      </View>
                    ) : null}
                    {cancelAvailable ? (
                      <View className="mt-5 gap-2">
                        <Pressable
                          onPress={() => confirmCancellation(true)}
                          disabled={savingAction !== null}
                          accessibilityRole="button"
                          className={`min-h-12 items-center justify-center rounded-xl px-4 ${
                            savingAction ? "bg-[#C8BEB5]" : "bg-[#B04438]"
                          }`}
                        >
                          <Text className="font-bold text-white">
                            {savingAction === "cancel"
                              ? "Updating subscription..."
                              : "Cancel Subscription"}
                          </Text>
                        </Pressable>
                        <Pressable
                          onPress={() => confirmCancellation(false)}
                          disabled={savingAction !== null}
                          accessibilityRole="button"
                          className="min-h-11 items-center justify-center rounded-xl border border-[#EAE4DC] bg-white px-4"
                        >
                          <Text className="font-semibold text-[#B04438]">
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
                        className="mt-3 min-h-12 items-center justify-center rounded-xl border border-[#FF6B5F] bg-white px-4"
                      >
                        <Text className="font-bold text-[#B04438]">
                          {showPlanOptions ? "Hide plans" : "Switch Plan"}
                        </Text>
                      </Pressable>
                    ) : null}
                  </>
                ) : (
                  <Text className="mt-2 leading-5 text-[#827970]">
                    No paid subscription is active on this account.
                  </Text>
                )}
              </View>
              <View className="border-t border-[#EAE4DC] px-4 py-3">
                <Text className="text-sm leading-5 text-[#827970]">
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
                  <Text className="mb-3 text-sm leading-5 text-[#827970]">
                    Choose a new plan and billing interval. Stripe applies
                    proration as a charge or credit on the upcoming invoice.
                  </Text>
                  {plans.plans.map((plan) => (
                    <View key={plan.id} className="mb-4 last:mb-0">
                      <Text className="font-bold text-[#24221F]">
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
                            className="mt-2 min-h-11 flex-row items-center justify-between rounded-xl border border-[#EAE4DC] px-3"
                          >
                            <Text className="font-semibold text-[#51483F]">
                              Switch to {interval}
                            </Text>
                            <Text className="font-semibold text-[#24221F]">
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
                    <View className="mt-2 rounded-xl bg-[#F3EEE8] p-4">
                      <Text className="font-semibold leading-5 text-[#51483F]">
                        Stripe will apply prorated charges or credits based on
                        the remaining billing period. The exact amount is
                        calculated by Stripe before the next invoice.
                      </Text>
                      <Pressable
                        onPress={confirmPlanSwitch}
                        disabled={savingAction !== null}
                        accessibilityRole="button"
                        className="mt-3 min-h-12 items-center justify-center rounded-xl bg-[#FF6B5F] px-4"
                      >
                        <Text className="font-bold text-white">
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
                    index ? "border-t border-[#EAE4DC]" : ""
                  }`}
                >
                  <Text className="text-lg font-bold text-[#24221F]">
                    {plan.name}
                  </Text>
                  {(["monthly", "annual"] as const).map((interval) => {
                    const price = plan.prices[interval];
                    return (
                      <Text
                        key={interval}
                        className="mt-2 text-sm text-[#827970]"
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
                  <Text className="mt-2 text-sm leading-5 text-[#827970]">
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
                      className="min-h-11 flex-1 items-center justify-center rounded-xl bg-[#FF6B5F] px-3"
                    >
                      <Text className="text-center text-sm font-bold text-white">
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
                      className="min-h-11 flex-1 items-center justify-center rounded-xl border border-[#FF6B5F] bg-white px-3"
                    >
                      <Text className="text-center text-sm font-bold text-[#B94E45]">
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
                  <Text className="leading-5 text-[#827970]">
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
                    className="mt-3 min-h-12 items-center justify-center rounded-xl bg-[#FF6B5F] px-4"
                  >
                    <Text className="font-bold text-white">
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
                      index ? "border-t border-[#EAE4DC]" : ""
                    }`}
                  >
                    <Text className="font-semibold capitalize text-[#24221F]">
                      {plans.plans.find((plan) => plan.id === item.plan_id)
                        ?.name ?? item.plan_id}{" "}
                      · {item.billing_interval}
                    </Text>
                    <View className="mt-2 flex-row items-center justify-between gap-3">
                      <Text className="text-sm font-semibold capitalize text-[#51483F]">
                        {item.status}
                      </Text>
                      {item.amount_minor !== null && item.currency ? (
                        <Text className="font-semibold text-[#24221F]">
                          {formatAmount(item.amount_minor, item.currency)}
                        </Text>
                      ) : null}
                    </View>
                    <Text className="mt-1 text-sm text-[#827970]">
                      {formatDate(item.occurred_at ?? item.created_at)}
                    </Text>
                  </View>
                ))
              ) : (
                <Text className="p-4 leading-5 text-[#827970]">
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
