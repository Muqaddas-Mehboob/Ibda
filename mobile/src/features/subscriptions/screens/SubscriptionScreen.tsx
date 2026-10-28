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
  getSubscriptionPlans,
  getUserSubscription,
  type SubscriptionPlansResponse,
  type UserSubscriptionResponse,
} from "../services/subscription.service";

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

function formatAmount(amountMinor: number, currency: string) {
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
  const [plans, setPlans] = useState<SubscriptionPlansResponse | null>(null);
  const [account, setAccount] = useState<UserSubscriptionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const [planResponse, subscriptionResponse] = await Promise.all([
        getSubscriptionPlans(),
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
          View your plan and billing history. Payments are not enabled yet.
        </Text>

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

        {!loading && !error && plans && account ? (
          <>
            <Section title="Current plan">
              <View className="p-4">
                <View className="flex-row items-center justify-between">
                  <Text className="text-xl font-bold text-[#24221F]">
                    {account.plan_id === "free" ? "Free" : "Premium"}
                  </Text>
                  <View className="rounded-full bg-[#F3EEE8] px-3 py-1">
                    <Text className="text-xs font-bold uppercase text-[#827970]">
                      {account.subscription?.status ?? "active"}
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
                      Current period ends:{" "}
                      {formatDate(account.subscription.current_period_end)}
                    </Text>
                    {account.subscription.cancel_at_period_end ? (
                      <Text className="mt-2 text-sm font-semibold text-[#B04438]">
                        Scheduled to cancel at the end of this period
                      </Text>
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
                  Subscription changes are unavailable until a verified
                  billing provider is configured.
                </Text>
              </View>
            </Section>

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
                  <Text className="mt-1 text-sm text-[#827970]">
                    {plan.id === "free"
                      ? "No charge"
                      : "Pricing and billing intervals are not set"}
                  </Text>
                  <Text className="mt-2 text-sm leading-5 text-[#827970]">
                    Plan features and limits will appear once they have been
                    defined.
                  </Text>
                  {plan.id === "premium" ? (
                    <Pressable
                      onPress={() => router.push("/subscription/monthly")}
                      accessibilityRole="button"
                      accessibilityLabel="View subscription plans"
                      className="mt-4 min-h-11 items-center justify-center rounded-xl bg-[#FF6B5F] px-4"
                    >
                      <Text className="font-bold text-white">
                        Explore plans
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              ))}
            </Section>

            <Section title="Payment history">
              {account.transactions.length ? (
                account.transactions.map((item, index) => (
                  <View
                    key={item.id}
                    className={`p-4 ${
                      index ? "border-t border-[#EAE4DC]" : ""
                    }`}
                  >
                    <View className="flex-row items-center justify-between gap-3">
                      <Text className="font-semibold capitalize text-[#24221F]">
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
