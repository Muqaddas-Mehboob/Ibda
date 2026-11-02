import React from "react";
import { Alert } from "react-native";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { SubscriptionScreen } from "../SubscriptionScreen";
import { PricingScreen } from "../PricingScreen";
import {
  cancelSubscription,
  getSubscriptionPlans,
  getUserSubscription,
  switchSubscriptionPlan,
} from "../../services/subscription.service";

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockSetParams = jest.fn();

jest.mock("expo-router", () => {
  const ReactModule = require("react");
  return {
    useRouter: () => ({
      push: mockPush,
      replace: mockReplace,
      setParams: mockSetParams,
    }),
    useLocalSearchParams: () => ({ plan: "starter" }),
    useFocusEffect: (callback: () => void) =>
      ReactModule.useEffect(callback, [callback]),
  };
});

jest.mock("../../../../components/navigation/BottomNavigation", () => ({
  BottomNavigation: () => null,
}));

jest.mock("../../services/subscription.service", () => ({
  cancelSubscription: jest.fn(),
  getSubscriptionPlans: jest.fn(),
  getUserSubscription: jest.fn(),
  switchSubscriptionPlan: jest.fn(),
  startSubscriptionCheckout: jest.fn(),
}));

const plans = {
  plans: [
    {
      id: "starter" as const,
      name: "Starter",
      description: "Core tools",
      features: [],
      features_configured: true,
      prices: {
        monthly: {
          price_minor: 1200,
          currency: "USD",
          checkout_available: true,
        },
        annual: {
          price_minor: 12000,
          currency: "USD",
          checkout_available: true,
        },
      },
      billing_intervals: ["monthly" as const, "annual" as const],
      checkout_available: true,
    },
    {
      id: "pro" as const,
      name: "Pro",
      description: "Advanced tools",
      features: [],
      features_configured: true,
      prices: {
        monthly: {
          price_minor: 2500,
          currency: "USD",
          checkout_available: true,
        },
        annual: {
          price_minor: 25000,
          currency: "USD",
          checkout_available: true,
        },
      },
      billing_intervals: ["monthly" as const, "annual" as const],
      checkout_available: true,
    },
  ],
  provider_configured: true,
  checkout_available: true,
  missing_configuration: [],
  message: "",
};

function makeAccount(
  status: "active" | "pending" | "canceled" | "expired" | "past_due" | null
) {
  return {
    subscription: status
      ? {
          id: "subscription-1",
          provider: "stripe",
          plan_id: "starter",
          billing_interval: "monthly" as const,
          status,
          current_period_start: "2026-11-02T08:00:00Z",
          current_period_end: "2026-12-02T08:00:00Z",
          cancel_at_period_end: false,
          canceled_at: null,
          created_at: "2026-11-02T08:00:00Z",
        }
      : null,
    plan_id: status && status !== "expired" ? "starter" : "free",
    entitlements: {},
    transactions:
      status === "active"
        ? [
            {
              id: "payment-1",
              subscription_id: "subscription-1",
              plan_id: "starter",
              billing_interval: "monthly" as const,
              subscription_status: "active" as const,
              status: "succeeded" as const,
              amount_minor: 1200,
              currency: "USD",
              occurred_at: "2026-11-02T08:00:00Z",
              created_at: "2026-11-02T08:00:00Z",
            },
          ]
        : [],
    checkout_available: true,
    checkout_eligible: !status || status === "canceled" || status === "expired",
    manage_available: status === "active" || status === "past_due",
  };
}

const plansRequest = jest.mocked(getSubscriptionPlans);
const subscriptionRequest = jest.mocked(getUserSubscription);
const cancelRequest = jest.mocked(cancelSubscription);
const switchRequest = jest.mocked(switchSubscriptionPlan);

describe("SubscriptionScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    plansRequest.mockResolvedValue(plans);
    subscriptionRequest.mockResolvedValue(makeAccount("active"));
    cancelRequest.mockResolvedValue({
      id: "subscription-1",
      status: "active",
      cancel_at_period_end: true,
      canceled_at: null,
      current_period_end: "2026-12-02T08:00:00Z",
      effective_at: "2026-12-02T08:00:00Z",
      message: "Your subscription remains active.",
    });
    switchRequest.mockResolvedValue({
      id: "subscription-1",
      plan_id: "pro",
      billing_interval: "monthly",
      amount_minor: 2500,
      currency: "USD",
      current_period_end: "2026-12-02T08:00:00Z",
      proration_disclosure: "Prorations apply to the next invoice.",
      status: "active",
    });
  });

  it("shows management actions and suppresses duplicate subscribe actions for active subscriptions", async () => {
    await render(<SubscriptionScreen />);

    expect(await screen.findByText("Cancel Subscription")).toBeTruthy();
    expect(screen.getByText("Switch Plan")).toBeTruthy();
    expect(screen.getByText("Starter")).toBeTruthy();
    expect(screen.getAllByText("$12.00").length).toBeGreaterThan(0);
    expect(screen.queryByText("Monthly pricing")).toBeNull();
    expect(screen.queryByText("Annual pricing")).toBeNull();
  });

  it("asks for cancellation confirmation and calls the shared API", async () => {
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    await render(<SubscriptionScreen />);

    await fireEvent.press(await screen.findByText("Cancel Subscription"));
    expect(alertSpy).toHaveBeenCalledWith(
      "Cancel at period end?",
      expect.stringContaining("remain active through"),
      expect.any(Array)
    );
    const buttons = alertSpy.mock.calls[0]?.[2];
    const confirmButton = buttons?.find(
      (button) => button.text === "Confirm cancellation"
    );
    await act(async () => {
      confirmButton?.onPress?.();
    });
    expect(cancelRequest).toHaveBeenCalledWith(true);
    alertSpy.mockRestore();
  });

  it("shows selectable prices and confirms a plan switch", async () => {
    const alertSpy = jest.spyOn(Alert, "alert").mockImplementation(() => {});
    await render(<SubscriptionScreen />);

    await fireEvent.press(await screen.findByText("Switch Plan"));
    expect(await screen.findAllByText("Switch to annual")).toHaveLength(2);
    await fireEvent.press(screen.getByText("Switch to monthly"));
    expect(screen.getByText("Confirm plan change")).toBeTruthy();
    await fireEvent.press(screen.getByText("Confirm plan change"));
    expect(alertSpy).toHaveBeenCalledWith(
      "Confirm plan change",
      expect.stringContaining("prorated charges or credits"),
      expect.any(Array)
    );
    const buttons = alertSpy.mock.calls[0]?.[2];
    const confirmButton = buttons?.find(
      (button) => button.text === "Confirm plan change"
    );
    await act(async () => {
      confirmButton?.onPress?.();
    });
    expect(switchRequest).toHaveBeenCalledWith("pro", "monthly");
    alertSpy.mockRestore();
  });

  it("shows available Subscribe pricing when there is no current subscription", async () => {
    subscriptionRequest.mockResolvedValue(makeAccount(null));
    await render(<SubscriptionScreen />);

    expect(await screen.findAllByText("Monthly pricing")).toHaveLength(2);
    expect(screen.getAllByText("Annual pricing")).toHaveLength(2);
    expect(screen.queryByText("Cancel Subscription")).toBeNull();
  });
});

describe("PricingScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    plansRequest.mockResolvedValue(plans);
    subscriptionRequest.mockResolvedValue(makeAccount("active"));
  });

  it("does not offer Checkout while an active subscription exists", async () => {
    await render(<PricingScreen interval="monthly" />);

    expect(await screen.findByText("Manage subscription")).toBeTruthy();
    expect(screen.queryByText("Continue to checkout")).toBeNull();
  });
});
