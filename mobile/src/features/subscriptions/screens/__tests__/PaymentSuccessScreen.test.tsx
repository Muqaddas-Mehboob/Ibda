import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { PaymentSuccessScreen } from "../PaymentSuccessScreen";
import { verifyCheckoutSession } from "../../services/subscription.service";

const mockReplace = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useLocalSearchParams: () => ({ session_id: "cs_test_checkout" }),
}));

jest.mock("../../services/subscription.service", () => ({
  verifyCheckoutSession: jest.fn(),
}));

const verification = jest.mocked(verifyCheckoutSession);

function makeResult(status: "pending" | "success" | "failed") {
  return {
    status,
    plan_id: "pro" as const,
    billing_interval: "annual" as const,
    payment_status:
      status === "success"
        ? ("succeeded" as const)
        : status === "failed"
          ? ("failed" as const)
          : ("pending" as const),
    subscription_status: status === "success" ? ("active" as const) : ("pending" as const),
    amount_minor: status === "success" ? 24000 : null,
    currency: status === "success" ? "USD" : "",
    paid_at: status === "success" ? "2026-10-30T10:00:00Z" : null,
    current_period_end: null,
    cancel_at_period_end: false,
  };
}

describe("PaymentSuccessScreen", () => {
  beforeEach(() => {
    verification.mockReset();
    mockReplace.mockReset();
    jest.useRealTimers();
  });

  it("shows a loading state while the backend verifies the session", async () => {
    verification.mockReturnValue(new Promise(() => {}));

    await render(<PaymentSuccessScreen />);

    expect(await screen.findByText("Confirming your payment")).toBeTruthy();
    expect(screen.queryByText("Payment Successful")).toBeNull();
  });

  it("shows pending after bounded retries and lets the user retry", async () => {
    jest.useFakeTimers();
    verification.mockResolvedValue(makeResult("pending"));

    await render(<PaymentSuccessScreen />);

    await act(async () => {
      await jest.advanceTimersByTimeAsync(12000);
    });

    expect(screen.getByText("Payment processing")).toBeTruthy();
    expect(screen.queryByText("Payment Successful")).toBeNull();
    expect(verification).toHaveBeenCalledTimes(7);
    await fireEvent.press(screen.getByText("Check again"));
    expect(verification).toHaveBeenCalledTimes(8);
  });

  it("shows success details only after backend confirmation", async () => {
    verification.mockResolvedValue(makeResult("success"));

    await render(<PaymentSuccessScreen />);

    expect(await screen.findByText("Payment Successful")).toBeTruthy();
    expect(screen.getByText("Pro")).toBeTruthy();
    expect(screen.getByText("annual")).toBeTruthy();
    expect(screen.getByText("$240.00")).toBeTruthy();
    await fireEvent.press(screen.getByText("Go to Billing"));
    expect(mockReplace).toHaveBeenCalledWith("/subscription");
  });

  it("shows an understandable verification error and retry action", async () => {
    verification.mockRejectedValue(new Error("Session expired"));

    await render(<PaymentSuccessScreen />);

    expect(await screen.findByText("Can't verify payment")).toBeTruthy();
    expect(screen.getByText("Session expired")).toBeTruthy();
    expect(screen.queryByText("Payment Successful")).toBeNull();
    await fireEvent.press(screen.getByText("Retry verification"));
    expect(verification).toHaveBeenCalledTimes(2);
  });

  it("shows a failed payment state without claiming success", async () => {
    verification.mockResolvedValue(makeResult("failed"));

    await render(<PaymentSuccessScreen />);

    expect(await screen.findByText("Payment not completed")).toBeTruthy();
    expect(screen.queryByText("Payment Successful")).toBeNull();
  });
});
