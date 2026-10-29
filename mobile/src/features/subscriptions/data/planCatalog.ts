export type BillingInterval = "monthly" | "annual";
export type PlanId = "starter" | "pro" | "enterprise";

export type PlanPrice = {
  price_minor: number | null;
  currency: string | null;
  checkout_available: boolean;
};

export type PricingPlan = {
  id: PlanId;
  name: string;
  description: string | null;
  features: string[];
  features_configured: boolean;
  prices: Record<BillingInterval, PlanPrice>;
  billing_intervals: BillingInterval[];
  checkout_available: boolean;
};
