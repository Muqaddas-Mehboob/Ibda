import { Pressable, ScrollView, Text, View } from "react-native";
import { useRouter } from "expo-router";

export function CheckoutCancelledScreen() {
  const router = useRouter();

  return (
    <View className="flex-1 justify-center bg-[#FCF9F4] p-6">
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center" }}>
        <View className="w-full max-w-[520px] self-center rounded-[28px] border border-[#EAE4DC] bg-white p-6">
          <View className="h-16 w-16 items-center justify-center self-center rounded-full bg-[#F3EEE8]">
            <Text
              className="text-3xl font-bold text-[#827970]"
              accessibilityLabel="Checkout cancelled"
            >
              ×
            </Text>
          </View>
          <Text className="mt-5 text-center text-3xl font-bold text-[#24221F]">
            Checkout canceled
          </Text>
          <Text className="mt-3 text-center leading-6 text-[#827970]">
            Checkout was canceled before Stripe confirmed payment. No
            subscription was activated. You can return to Billing whenever
            you’re ready.
          </Text>
          <Pressable
            onPress={() => router.replace("/subscription")}
            accessibilityRole="button"
            className="mt-6 min-h-14 items-center justify-center rounded-full bg-[#FF6B5F] px-5"
          >
            <Text className="font-bold text-white">Go to Billing</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}
