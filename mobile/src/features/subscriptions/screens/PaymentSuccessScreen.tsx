import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  verifyCheckoutSession,
  type CheckoutSessionVerification,
} from "../services/subscription.service";

type ScreenState = "loading" | "pending" | "success" | "failed" | "error";

const PLAN_NAMES = {
  starter: "Starter",
  pro: "Pro",
  enterprise: "Enterprise",
} as const;

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
    return "Amount unavailable";
  }
}

function formatDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
}

export function PaymentSuccessScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ session_id?: string | string[] }>();
  const sessionId =
    typeof params.session_id === "string" ? params.session_id : null;
  const [state, setState] = useState<ScreenState>("loading");
  const [verification, setVerification] =
    useState<CheckoutSessionVerification | null>(null);
  const [error, setError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const verify = async () => {
      setState("loading");
      setVerification(null);
      setError("");
      if (!sessionId) {
        setError("This return link is missing its checkout reference.");
        setState("error");
        return;
      }

      for (let attempt = 0; attempt < 7; attempt += 1) {
        try {
          const result = await verifyCheckoutSession(sessionId);
          if (!active) return;
          setVerification(result);
          if (result.status === "success") {
            setState("success");
            return;
          }
          if (result.status === "failed") {
            setState("failed");
            return;
          }
        } catch (verificationError) {
          if (!active) return;
          setError(
            verificationError instanceof Error
              ? verificationError.message
              : "We couldn't verify this payment. Please try again."
          );
          setState("error");
          return;
        }

        if (attempt < 6) {
          await new Promise<void>((resolve) => {
            timer = setTimeout(resolve, 2000);
          });
        }
      }

      if (active) setState("pending");
    };

    void verify();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [retryCount, sessionId]);

  const retry = () => setRetryCount((count) => count + 1);
  const planName = verification
    ? PLAN_NAMES[verification.plan_id]
    : null;
  const paidDate = formatDate(verification?.paid_at ?? null);

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: "center",
          padding: 24,
        }}
      >
        <View className="w-full max-w-[560px] self-center rounded-[28px] border border-[#EAE4DC] bg-white p-6">
          <View
            className={`mb-5 h-16 w-16 items-center justify-center self-center rounded-full ${
              state === "success"
                ? "bg-[#E4F3E8]"
                : state === "failed" || state === "error"
                  ? "bg-[#FCE5E1]"
                  : "bg-[#F3EEE8]"
            }`}
          >
            <Text
              className={`text-3xl font-bold ${
                state === "success"
                  ? "text-[#27824A]"
                  : state === "failed" || state === "error"
                    ? "text-[#B94E45]"
                    : "text-[#827970]"
              }`}
              accessibilityLabel={
                state === "success" ? "Payment confirmed" : "Payment status"
              }
            >
              {state === "success"
                ? "✓"
                : state === "failed" || state === "error"
                  ? "!"
                  : "…"}
            </Text>
          </View>

          {state === "loading" ? (
            <>
              <Text className="text-center text-3xl font-bold text-[#24221F]">
                Confirming your payment
              </Text>
              <Text className="mt-3 text-center leading-6 text-[#827970]">
                We’re securely checking the payment and subscription with
                Stripe. This may take a few moments.
              </Text>
              <ActivityIndicator
                className="mt-6"
                color="#FF6B5F"
                accessibilityLabel="Verifying payment"
              />
            </>
          ) : state === "success" && verification ? (
            <>
              <Text className="text-center text-3xl font-bold text-[#24221F]">
                Payment Successful
              </Text>
              <Text className="mt-3 text-center leading-6 text-[#827970]">
                Your payment is confirmed and your subscription is{" "}
                {verification.subscription_status.replace("_", " ")}.
              </Text>
              <View className="mt-6 rounded-2xl bg-[#F8F5F0] p-4">
                <View className="flex-row justify-between gap-4">
                  <Text className="text-[#827970]">Plan</Text>
                  <Text className="font-semibold capitalize text-[#24221F]">
                    {planName}
                  </Text>
                </View>
                <View className="mt-3 flex-row justify-between gap-4">
                  <Text className="text-[#827970]">Billing interval</Text>
                  <Text className="font-semibold capitalize text-[#24221F]">
                    {verification.billing_interval}
                  </Text>
                </View>
                <View className="mt-3 flex-row justify-between gap-4">
                  <Text className="text-[#827970]">Amount paid</Text>
                  <Text className="font-semibold text-[#24221F]">
                    {formatAmount(
                      verification.amount_minor,
                      verification.currency
                    )}
                  </Text>
                </View>
                {paidDate ? (
                  <View className="mt-3 flex-row justify-between gap-4">
                    <Text className="text-[#827970]">Payment date</Text>
                    <Text className="font-semibold text-[#24221F]">
                      {paidDate}
                    </Text>
                  </View>
                ) : null}
                {verification.cancel_at_period_end ? (
                  <Text className="mt-4 text-sm leading-5 text-[#B04438]">
                    This subscription is set to end at the close of its current
                    billing period.
                  </Text>
                ) : null}
              </View>
              <Text className="mt-4 text-center text-sm leading-5 text-[#827970]">
                Thank you for subscribing to Ibda. Your billing details are
                available in your account.
              </Text>
              <Pressable
                onPress={() => router.replace("/subscription")}
                accessibilityRole="button"
                className="mt-6 min-h-14 items-center justify-center rounded-full bg-[#FF6B5F] px-5"
              >
                <Text className="font-bold text-white">Go to Billing</Text>
              </Pressable>
            </>
          ) : state === "pending" ? (
            <>
              <Text className="text-center text-3xl font-bold text-[#24221F]">
                Payment processing
              </Text>
              <Text className="mt-3 text-center leading-6 text-[#827970]">
                Stripe has not finished confirming your payment and
                subscription. We haven’t marked this purchase as successful.
                You can check again shortly.
              </Text>
              {planName ? (
                <Text className="mt-4 text-center font-semibold capitalize text-[#51483F]">
                  {planName} · {verification?.billing_interval} billing
                </Text>
              ) : null}
              <Pressable
                onPress={retry}
                accessibilityRole="button"
                className="mt-6 min-h-14 items-center justify-center rounded-full bg-[#FF6B5F] px-5"
              >
                <Text className="font-bold text-white">Check again</Text>
              </Pressable>
              <Pressable
                onPress={() => router.replace("/subscription")}
                accessibilityRole="button"
                className="mt-3 min-h-12 items-center justify-center rounded-full border border-[#EAE4DC] px-5"
              >
                <Text className="font-semibold text-[#51483F]">
                  Go to Billing
                </Text>
              </Pressable>
            </>
          ) : (
            <>
              <Text className="text-center text-3xl font-bold text-[#24221F]">
                {state === "failed" ? "Payment not completed" : "Can't verify payment"}
              </Text>
              <Text className="mt-3 text-center leading-6 text-[#827970]">
                {state === "failed"
                  ? "Stripe did not confirm this payment. No subscription was activated. You can return to Billing to check your account or try checkout again."
                  : error ||
                    "We couldn't verify this checkout session. Your payment status has not been assumed."}
              </Text>
              <Pressable
                onPress={retry}
                accessibilityRole="button"
                className="mt-6 min-h-14 items-center justify-center rounded-full bg-[#FF6B5F] px-5"
              >
                <Text className="font-bold text-white">Retry verification</Text>
              </Pressable>
              <Pressable
                onPress={() => router.replace("/subscription")}
                accessibilityRole="button"
                className="mt-3 min-h-12 items-center justify-center rounded-full border border-[#EAE4DC] px-5"
              >
                <Text className="font-semibold text-[#51483F]">
                  Go to Billing
                </Text>
              </Pressable>
            </>
          )}
        </View>
      </ScrollView>
    </View>
  );
}
