import { Redirect } from "expo-router";

export default function SubscriptionSuccessRoute() {
  return <Redirect href="/subscription?checkout=success" />;
}
