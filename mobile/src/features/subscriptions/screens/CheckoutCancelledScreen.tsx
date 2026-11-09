import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { ScrollView, View } from "react-native";
import { useRouter } from "expo-router";

export function CheckoutCancelledScreen() {
  const router = useRouter();

  return (
    <View className="flex-1 justify-center bg-[#FAF8F4] p-6">
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center", width: "100%", maxWidth: 960, alignSelf: "center" }}>
        <StudioCard className="w-full max-w-[520px] self-center rounded-[24px] border border-[#E9E2DA] bg-white p-5">
          <View className="h-16 w-16 items-center justify-center self-center rounded-full bg-[#F1E9DF]">
            <Text
              className="text-[30px] leading-[37px] tracking-[-0.6px] font-bold text-[#716A64]"
              accessibilityLabel="Checkout cancelled" variant="metric"
            >
              ×
            </Text>
          </View>
          <Text className="mt-5 text-center text-[30px] leading-[37px] tracking-[-0.6px] font-bold text-[#292724]" variant="metric">
            Checkout canceled
          </Text>
          <Text className="mt-3 text-center text-[#716A64] text-[15px] leading-[24px]" variant="body">
            Checkout was canceled before Stripe confirmed payment. No
            subscription was activated. You can return to Billing whenever
            you’re ready.
          </Text>
          <Pressable
            onPress={() => router.replace("/subscription")}
            accessibilityRole="button"
            className="mt-6 min-h-[54px] items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5"
          >
            <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">Go to Billing</Text>
          </Pressable>
        </StudioCard>
      </ScrollView>
    </View>
  );
}
