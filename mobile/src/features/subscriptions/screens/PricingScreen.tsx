import { Pressable, ScrollView, Text, View, useWindowDimensions } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  getPlanById,
  pricingPlans,
  type BillingInterval,
} from "../data/planCatalog";

function formatPrice(amountMinor: number, currency: string) {
  const formatter = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  });
  const fractionDigits =
    formatter.resolvedOptions().maximumFractionDigits ?? 2;
  return formatter.format(amountMinor / 10 ** fractionDigits);
}

function getSavingsPercent(
  monthlyAmount: number | null,
  annualAmount: number | null,
  monthlyCurrency: string | null,
  annualCurrency: string | null
) {
  if (
    monthlyAmount === null ||
    annualAmount === null ||
    monthlyCurrency === null ||
    monthlyCurrency !== annualCurrency ||
    monthlyAmount <= 0 ||
    annualAmount >= monthlyAmount * 12
  ) {
    return null;
  }

  const percentage =
    ((monthlyAmount * 12 - annualAmount) / (monthlyAmount * 12)) * 100;
  const roundedPercentage = Math.round(percentage * 10) / 10;
  return roundedPercentage > 0 ? roundedPercentage : null;
}

export function PricingScreen({ interval }: { interval: BillingInterval }) {
  const router = useRouter();
  const params = useLocalSearchParams<{ plan?: string | string[] }>();
  const selectedPlan =
    typeof params.plan === "string" ? getPlanById(params.plan) : undefined;
  const { width: viewportWidth } = useWindowDimensions();
  const columns = viewportWidth >= 980 ? 3 : viewportWidth >= 680 ? 2 : 1;
  const cardWidth =
    columns === 1 ? "100%" : `${(100 - (columns - 1) * 2.5) / columns}%`;

  const changeInterval = (nextInterval: BillingInterval) => {
    if (nextInterval === interval) return;

    router.replace({
      pathname:
        nextInterval === "monthly"
          ? "/subscription/monthly"
          : "/subscription/annual",
      params: selectedPlan ? { plan: selectedPlan.id } : {},
    });
  };

  const selectPlan = (planId: string) => {
    router.setParams({ plan: planId });
  };

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: 20,
          paddingTop: 24,
          paddingBottom: 40,
        }}
        showsVerticalScrollIndicator={false}
      >
        <View
          style={{
            width: "100%",
            maxWidth: 1040,
            alignSelf: "center",
          }}
        >
          <View className="flex-row items-center justify-between border-b border-[#EAE4DC] pb-4">
            <Text className="text-2xl font-black tracking-[-1px] text-[#24221F]">
              ibda
            </Text>
            <Pressable
              onPress={() => router.push("/subscription")}
              accessibilityRole="button"
              accessibilityLabel="Return to billing overview"
              className="min-h-11 flex-row items-center rounded-full border border-[#EAE4DC] bg-white px-4"
            >
              <Text className="text-sm font-semibold text-[#51483F]">
                Billing overview
              </Text>
            </Pressable>
          </View>

          <View className="items-center pb-6 pt-8">
            <View className="rounded-full border border-[#F4D3CE] bg-[#FCE5E1] px-4 py-2">
              <Text className="text-xs font-bold uppercase tracking-[1.5px] text-[#B94E45]">
                Pricing & plans
              </Text>
            </View>
            <Text className="mt-4 text-center text-3xl font-bold leading-10 text-[#24221F]">
              Choose the right plan for you
            </Text>
            <Text className="mt-3 max-w-[620px] text-center text-base leading-6 text-[#827970]">
              Compare the available plans. Pricing and plan details are being
              finalized.
            </Text>
          </View>

          <View
            accessibilityRole="tablist"
            accessibilityLabel="Billing interval"
            className="mx-auto mb-6 w-full max-w-[400px] flex-row rounded-full border border-[#EAE4DC] bg-[#F3EEE8] p-1"
          >
            {(["monthly", "annual"] as const).map((option) => {
              const active = option === interval;
              return (
                <Pressable
                  key={option}
                  onPress={() => changeInterval(option)}
                  accessibilityRole="tab"
                  accessibilityLabel={`${option === "monthly" ? "Monthly" : "Annual"} billing`}
                  accessibilityState={{ selected: active }}
                  className={`min-h-12 flex-1 items-center justify-center rounded-full px-3 ${
                    active ? "bg-white" : ""
                  }`}
                >
                  <Text
                    className={`text-sm font-bold capitalize ${
                      active ? "text-[#FF6B5F]" : "text-[#827970]"
                    }`}
                  >
                    {option}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <View className="mb-5 flex-row flex-wrap justify-center gap-4">
            {pricingPlans.map((plan) => {
              const price = plan.prices[interval];
              const savings = getSavingsPercent(
                plan.prices.monthly.amountMinor,
                plan.prices.annual.amountMinor,
                plan.prices.monthly.currency,
                plan.prices.annual.currency
              );
              const selected = selectedPlan?.id === plan.id;

              return (
                <View
                  key={plan.id}
                  className={`rounded-[24px] border bg-white p-5 ${
                    selected ? "border-[#FF6B5F]" : "border-[#EAE4DC]"
                  }`}
                  style={{ width: cardWidth }}
                >
                  <Text className="text-xl font-bold text-[#24221F]">
                    {plan.name}
                  </Text>
                  <Text className="mt-2 min-h-10 text-sm leading-5 text-[#827970]">
                    {plan.description}
                  </Text>

                  <View className="my-5 border-t border-[#EAE4DC]" />

                  {price.amountMinor !== null && price.currency ? (
                    <Text className="text-3xl font-bold text-[#24221F]">
                      {formatPrice(price.amountMinor, price.currency)}
                      <Text className="text-sm font-medium text-[#827970]">
                        {interval === "monthly" ? " / month" : " / year"}
                      </Text>
                    </Text>
                  ) : (
                    <Text className="text-2xl font-bold text-[#24221F]">
                      Price to be announced
                    </Text>
                  )}
                  <Text className="mt-2 text-sm text-[#827970]">
                    Billed {interval === "monthly" ? "monthly" : "annually"}
                  </Text>
                  {interval === "annual" && savings !== null ? (
                    <View className="mt-3 self-start rounded-full bg-[#FCE5E1] px-3 py-1">
                      <Text className="text-xs font-bold text-[#B94E45]">
                        Save {savings}%
                      </Text>
                    </View>
                  ) : null}

                  <Text className="mb-2 mt-6 text-xs font-bold uppercase tracking-[1px] text-[#51483F]">
                    What’s included
                  </Text>
                  {plan.features.length ? (
                    plan.features.map((feature) => (
                      <View
                        key={feature}
                        className="mb-2 flex-row items-start gap-2"
                      >
                        <Text className="text-[#FF6B5F]">•</Text>
                        <Text className="flex-1 text-sm leading-5 text-[#51483F]">
                          {feature}
                        </Text>
                      </View>
                    ))
                  ) : (
                    <Text className="min-h-10 text-sm leading-5 text-[#827970]">
                      Feature details will be announced soon.
                    </Text>
                  )}

                  <Pressable
                    onPress={() => selectPlan(plan.id)}
                    disabled={selected}
                    accessibilityRole="button"
                    accessibilityLabel={
                      selected ? `${plan.name} selected` : `Select ${plan.name}`
                    }
                    accessibilityState={{ selected, disabled: selected }}
                    className={`mt-5 min-h-12 items-center justify-center rounded-xl px-4 ${
                      selected ? "bg-[#F3EEE8]" : "bg-[#FF6B5F]"
                    }`}
                  >
                    <Text
                      className={`font-bold ${
                        selected ? "text-[#51483F]" : "text-white"
                      }`}
                    >
                      {selected ? "Selected" : `Select ${plan.name}`}
                    </Text>
                  </Pressable>
                </View>
              );
            })}
          </View>

          <View className="rounded-2xl border border-[#EAE4DC] bg-[#F3EEE8] p-4">
            <Text className="text-sm leading-5 text-[#51483F]">
              {selectedPlan
                ? `${selectedPlan.name} is selected for ${interval} billing. `
                : ""}
              Checkout will be implemented in a later phase. Selecting a plan
              does not start a payment or charge you.
            </Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
