import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
  useWindowDimensions,
  Platform,
} from "react-native";
import Constants from "expo-constants";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import type { BillingInterval } from "../data/planCatalog";
import {
  getSubscriptionPlans,
  startSubscriptionCheckout,
  SubscriptionApiError,
  SubscriptionFetchError,
  SubscriptionSessionError,
  type SubscriptionPlansResponse,
} from "../services/subscription.service";

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

function getUnavailableMessage(
  catalog: SubscriptionPlansResponse,
  planId: string,
  interval: BillingInterval
) {
  const missing = catalog.missing_configuration;
  const planInterval = `${planId}_${interval}_`;

  if (missing.includes(`${planId}_${interval}_stripe_price`)) {
    return "A Stripe Price has not been configured for this plan and interval.";
  }
  if (missing.includes(`${planInterval}stripe_price_unavailable`)) {
    return "The backend could not verify this Stripe Price. Try again later.";
  }
  if (missing.includes(`${planInterval}stripe_price_inactive`)) {
    return "This Stripe Price is inactive. Contact support to restore checkout.";
  }
  if (missing.includes(`${planInterval}stripe_price_interval_mismatch`)) {
    return "This Stripe Price does not match the selected billing interval.";
  }
  if (missing.includes(`${planInterval}stripe_price_id_duplicated`)) {
    return "This Stripe Price is assigned more than once in the backend catalog.";
  }
  if (!catalog.provider_configured || missing.includes("stripe_test_secret_key")) {
    return "Stripe test mode is not configured on the backend.";
  }
  if (missing.includes("stripe_webhook_secret")) {
    return "Stripe webhook verification is not configured on the backend.";
  }
  if (missing.includes("stripe_checkout_success_url")) {
    return "The backend success return URL is not configured.";
  }
  if (missing.includes("stripe_checkout_cancel_url")) {
    return "The backend cancellation return URL is not configured.";
  }
  return "Checkout is temporarily unavailable for this plan and interval.";
}

function getCheckoutReturnUrl() {
  const configuredScheme = Constants.expoConfig?.scheme;
  const scheme = Array.isArray(configuredScheme)
    ? configuredScheme[0]
    : configuredScheme;
  if (!scheme) {
    throw new Error("The app return-link scheme is not configured.");
  }
  return `${scheme}://subscription`;
}

export function PricingScreen({ interval }: { interval: BillingInterval }) {
  const router = useRouter();
  const params = useLocalSearchParams<{ plan?: string | string[] }>();
  const [catalog, setCatalog] = useState<SubscriptionPlansResponse | null>(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [checkoutError, setCheckoutError] = useState("");
  const [checkoutNeedsSignIn, setCheckoutNeedsSignIn] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const checkoutInFlight = useRef(false);
  const selectedPlanId = typeof params.plan === "string" ? params.plan : null;
  const selectedPlan = catalog?.plans.find(
    (plan) => plan.id === selectedPlanId
  );
  const selectedPrice = selectedPlan?.prices[interval];
  const { width: viewportWidth } = useWindowDimensions();
  const columns = viewportWidth >= 980 ? 3 : viewportWidth >= 680 ? 2 : 1;
  const cardWidth =
    columns === 1 ? "100%" : `${(100 - (columns - 1) * 2.5) / columns}%`;

  useEffect(() => {
    let active = true;

    getSubscriptionPlans()
      .then((response) => {
        if (active) {
          setCatalog(response);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setCatalogError(
            error instanceof Error
              ? error.message
              : "Unable to load current pricing. Please try again."
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoadingCatalog(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const retryLoadingCatalog = () => {
    setLoadingCatalog(true);
    setCatalogError("");
    getSubscriptionPlans()
      .then(setCatalog)
      .catch((error: unknown) => {
        setCatalogError(
          error instanceof Error
            ? error.message
            : "Unable to load current pricing. Please try again."
        );
      })
      .finally(() => setLoadingCatalog(false));
  };

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
    setCheckoutError("");
    setCheckoutNeedsSignIn(false);
    router.setParams({ plan: planId });
  };

  const clearSelectedPlan = () => {
    router.setParams({ plan: undefined });
  };

  const continueToCheckout = async () => {
    if (
      checkoutInFlight.current ||
      !selectedPlan ||
      !selectedPrice?.checkout_available
    ) {
      return;
    }

    checkoutInFlight.current = true;
    setCheckingOut(true);
    setCheckoutError("");
    setCheckoutNeedsSignIn(false);
    let openingBrowser = false;
    let failureCategory = "checkout_request";

    try {
      const checkout = await startSubscriptionCheckout(
        selectedPlan.id,
        interval
      );
      let checkoutUrl: URL;
      try {
        checkoutUrl = new URL(checkout.checkout_url);
      } catch {
        failureCategory = "invalid_checkout_url";
        throw new Error("The checkout link was invalid. Please try again.");
      }
      if (checkoutUrl.protocol !== "https:") {
        failureCategory = "invalid_checkout_url";
        throw new Error("The checkout link was invalid. Please try again.");
      }

      if (Platform.OS === "web") {
        openingBrowser = true;
        window.location.assign(checkoutUrl.toString());
        return;
      }

      openingBrowser = true;
      const result = await WebBrowser.openAuthSessionAsync(
        checkoutUrl.toString(),
        getCheckoutReturnUrl()
      );
      if (result.type !== "success") {
        setCheckoutError(
          "Checkout was closed before completion. Your subscription status was not changed."
        );
        clearSelectedPlan();
        return;
      }

      const checkoutResult = Linking.parse(result.url).queryParams?.checkout;
      const returnStatus =
        checkoutResult === "success" || checkoutResult === "cancelled"
          ? checkoutResult
          : undefined;
      router.replace(
        returnStatus
          ? { pathname: "/subscription", params: { checkout: returnStatus } }
          : "/subscription"
      );
    } catch (error) {
      const needsSignIn = error instanceof SubscriptionSessionError;
      const category =
        needsSignIn
          ? "session"
          : error instanceof SubscriptionFetchError
            ? error.category
            : error instanceof SubscriptionApiError
          ? `api_${error.status}`
          : openingBrowser
            ? "browser_open"
            : failureCategory;
      console.warn(`[subscription] Checkout failed: category=${category}`);
      setCheckoutNeedsSignIn(needsSignIn);
      setCheckoutError(
        openingBrowser
          ? "Unable to open Stripe Checkout. Please try again."
          : error instanceof Error
            ? error.message
            : "Unable to start checkout. Please try again."
      );
      clearSelectedPlan();
    } finally {
      checkoutInFlight.current = false;
      setCheckingOut(false);
    }
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
              Choose a plan and billing interval. Prices and checkout availability
              come from the verified Stripe test-mode catalog.
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

          {loadingCatalog ? (
            <View className="mb-5 flex-row items-center justify-center gap-3 rounded-2xl border border-[#EAE4DC] bg-white p-5">
              <ActivityIndicator color="#FF6B5F" />
              <Text className="text-sm text-[#827970]">
                Loading current prices...
              </Text>
            </View>
          ) : null}

          {catalogError ? (
            <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
              <Text accessibilityRole="alert" className="text-sm leading-5 text-[#A33D34]">
                {catalogError}
              </Text>
              <Pressable
                onPress={retryLoadingCatalog}
                accessibilityRole="button"
                accessibilityLabel="Retry loading prices"
                className="mt-3 min-h-11 items-center justify-center rounded-xl bg-[#FF6B5F] px-4"
              >
                <Text className="font-bold text-white">Try again</Text>
              </Pressable>
            </View>
          ) : null}

          <View className="mb-5 flex-row flex-wrap justify-center gap-4">
            {catalog?.plans.map((plan) => {
              const price = plan.prices[interval];
              const savings = getSavingsPercent(
                plan.prices.monthly.price_minor,
                plan.prices.annual.price_minor,
                plan.prices.monthly.currency,
                plan.prices.annual.currency
              );
              const selected = selectedPlanId === plan.id;

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
                    {plan.description ?? "Plan details have not been provided yet."}
                  </Text>

                  <View className="my-5 border-t border-[#EAE4DC]" />

                  {price.price_minor !== null && price.currency ? (
                    <Text className="text-3xl font-bold text-[#24221F]">
                      {formatPrice(price.price_minor, price.currency)}
                      <Text className="text-sm font-medium text-[#827970]">
                        {interval === "monthly" ? " / month" : " / year"}
                      </Text>
                    </Text>
                  ) : (
                    <Text className="text-lg font-bold text-[#24221F]">
                      Price unavailable
                    </Text>
                  )}
                  <Text className="mt-2 text-sm text-[#827970]">
                    Billed {interval === "monthly" ? "monthly" : "annually"}
                  </Text>
                  {!price.checkout_available ? (
                    <Text className="mt-2 text-sm text-[#A33D34]">
                      {catalog
                        ? getUnavailableMessage(catalog, plan.id, interval)
                        : "Checkout availability could not be verified."}
                    </Text>
                  ) : null}
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
                      {plan.features_configured
                        ? "No features are listed for this plan."
                        : "Plan features have not been configured yet."}
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

          {selectedPlan ? (
            <View className="mb-5">
              <Pressable
                onPress={() => void continueToCheckout()}
                disabled={
                  checkingOut ||
                  loadingCatalog ||
                  !selectedPrice?.checkout_available
                }
                accessibilityRole="button"
                accessibilityLabel={`Continue to checkout with ${selectedPlan.name}, ${interval} billing`}
                accessibilityState={{
                  disabled:
                    checkingOut ||
                    loadingCatalog ||
                    !selectedPrice?.checkout_available,
                  busy: checkingOut,
                }}
                className={`min-h-14 items-center justify-center rounded-full px-5 ${
                  checkingOut ||
                  loadingCatalog ||
                  !selectedPrice?.checkout_available
                    ? "bg-[#C8BEB5]"
                    : "bg-[#FF6B5F]"
                }`}
              >
                <Text className="font-bold text-white">
                  {checkingOut
                    ? "Opening secure checkout..."
                    : selectedPrice?.checkout_available
                      ? "Continue to checkout"
                      : "Checkout unavailable for this interval"}
                </Text>
              </Pressable>
            </View>
          ) : null}

          {checkoutError ? (
            <View className="mb-5">
              <Text
                accessibilityRole="alert"
                className="mb-3 text-sm leading-5 text-[#A33D34]"
              >
                {checkoutError}
              </Text>
              {checkoutNeedsSignIn ? (
                <Pressable
                  onPress={() => router.push("/sign-in")}
                  accessibilityRole="button"
                  accessibilityLabel="Sign in to continue to checkout"
                  className="min-h-12 items-center justify-center rounded-full bg-[#FF6B5F] px-5"
                >
                  <Text className="font-bold text-white">Sign in</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          <View className="rounded-2xl border border-[#EAE4DC] bg-[#F3EEE8] p-4">
            <Text className="text-sm leading-5 text-[#51483F]">
              {selectedPlan
                ? `${selectedPlan.name} is selected for ${interval} billing. `
                : "Select a plan to continue. "}
              Subscription access changes only after the backend verifies
              Stripe subscription events.
            </Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
