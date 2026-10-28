export type BillingInterval = "monthly" | "annual";
export type PlanId = "starter" | "pro" | "enterprise";

type PlanPrice = {
  amountMinor: number | null;
  currency: string | null;
};

type PricingPlan = {
  id: PlanId;
  name: string;
  description: string;
  features: string[];
  prices: Record<BillingInterval, PlanPrice>;
};

export const pricingPlans = [
  {
    id: "starter",
    name: "Starter",
    description: "Plan details are being finalized.",
    features: [],
    prices: {
      monthly: { amountMinor: null, currency: null },
      annual: { amountMinor: null, currency: null },
    },
  },
  {
    id: "pro",
    name: "Pro",
    description: "Plan details are being finalized.",
    features: [],
    prices: {
      monthly: { amountMinor: null, currency: null },
      annual: { amountMinor: null, currency: null },
    },
  },
  {
    id: "enterprise",
    name: "Enterprise",
    description: "Plan details are being finalized.",
    features: [],
    prices: {
      monthly: { amountMinor: null, currency: null },
      annual: { amountMinor: null, currency: null },
    },
  },
] satisfies PricingPlan[];

export function getPlanById(id: string | undefined) {
  return pricingPlans.find((plan) => plan.id === id);
}
