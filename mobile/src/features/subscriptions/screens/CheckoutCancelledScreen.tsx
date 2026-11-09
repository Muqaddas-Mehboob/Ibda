import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { ScrollView, View } from "react-native";
import { useRouter } from "expo-router";

export function CheckoutCancelledScreen() {
  const router = useRouter();

  return (
    <View className="flex-1 justify-center bg-[#FAF8F4] p-6">
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center", width: "100%", maxWidth: 960, alignSelf: "center" }}>
        <StudioCard className="w-full max-w-[520px] self-center rounded-[24px] border border-[#25221F]/30 bg-[#F4F0EA] p-5">
          <View className="h-16 w-16 items-center justify-center self-center rounded-full bg-[#F4F0EA]">
            <Text
              className="text-[22px] leading-[30px] tracking-[-0.3px] font-bold text-[#25221F]"
              accessibilityLabel="Checkout cancelled" variant="metric"
            >
              ×
            </Text>
          </View>
          <Text className="mt-5 text-center text-[22px] leading-[30px] tracking-[-0.3px] font-bold text-[#25221F]" variant="metric">
            Checkout canceled
          </Text>
          <Text className="mt-3 text-center text-[#25221F] text-[14px] leading-[22px]" variant="body">
            Checkout was canceled before Stripe confirmed payment. No
            subscription was activated. You can return to Billing whenever
            you’re ready.
          </Text>
          <Pressable
            onPress={() => router.replace("/subscription")}
            accessibilityRole="button"
            className="mt-6 min-h-[48px] items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5"
          >
            <Text className="font-bold text-[#FAF8F4] text-[14px] leading-[22px]" variant="button">Go to Billing</Text>
          </Pressable>
        </StudioCard>
      </ScrollView>
    </View>
  );
}
