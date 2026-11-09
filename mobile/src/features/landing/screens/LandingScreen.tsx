import { StudioIcon, type StudioIconName } from "../../../components/ui/StudioIcon";
import { StudioText as Text } from "../../../components/ui/StudioText";
import { IbdaLogo } from "../../../components/brand/IbdaLogo";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";

import { router } from "expo-router";
import { ScrollView, StatusBar, View, useWindowDimensions } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

function FeatureTile({
  icon,
  title,
  description,
}: {
  icon: StudioIconName;
  title: string;
  description: string;
}) {
  return (
 <View className="min-w-0 flex-1 items-center px-1 py-2">
  <View className="mb-3 h-10 w-10 items-center justify-center rounded-2xl bg-[#F4F0EA]"><StudioIcon name={icon} size={20} color="#25221F" /></View>
  <Text numberOfLines={1} adjustsFontSizeToFit variant="label" tone="charcoal" style={{ fontSize: 13 }}>{title}</Text>
  <Text variant="caption" tone="secondary" className="mt-1 text-center">{description}</Text>
 </View>
);
}

export function LandingScreen() {
  const { width } = useWindowDimensions();
  const compact = width < 380;

  return (
 <SafeAreaView edges={[]} style={{ flex: 1, backgroundColor: "#FAF8F4" }}>
  <StatusBar barStyle="dark-content" />
  <ScrollView className="w-full flex-1" contentContainerStyle={{ width: "100%", maxWidth: 600, alignSelf: "center", paddingHorizontal: compact ? 20 : 24, paddingTop: 16, paddingBottom: 36 }} showsVerticalScrollIndicator={false} bounces={false}>
   <View className="mb-7 w-full flex-row items-center justify-between">
    <IbdaLogo size={40} />
    <Text variant="eyebrow" tone="secondary" style={{ fontSize: 10, letterSpacing: 1.2 }}>CREATIVE STUDIO</Text>
   </View>
   <View className="items-center">
    <View className="mb-4 flex-row items-center gap-2 rounded-full bg-[#F4F0EA] px-3 py-2"><StudioIcon name="spark" size={14} color="#25221F" /><Text variant="caption" tone="plum">Autonomous Publishing</Text></View>
    <Text variant="display" tone="olive" className="text-center" style={{ fontSize: compact ? 24 : 26, lineHeight: compact ? 32 : 34 }}>Curated AI for{"\n"}modern creators.</Text>
    <Text variant="body" tone="secondary" className="mt-4 text-center">Autonomous publishing, deep brand voice{"\n"}memory, and cross-channel editorial{"\n"}intelligence.</Text>
   </View>
   <StudioCard className="mt-6 rounded-[24px] border border-[#E2D9CF] border-l-[3px] border-l-[#25221F] bg-[#F4F0EA] p-5">
    <View className="mb-4 flex-row items-center justify-between"><Text variant="eyebrow" tone="olive">Brand Voice AI</Text><StudioIcon name="brand" color="#25221F" size={24} /></View>
    <Text variant="page" tone="olive" style={{ fontSize: 18, lineHeight: 26 }}>Architectural &amp; Poetic</Text>
    <View className="mt-4 flex-row items-center gap-3 border-t border-[#E2D9CF] pt-4"><IbdaLogo size={30} wordmark={false} /><View><Text variant="label" tone="charcoal">Ibda</Text><Text variant="caption" tone="secondary">Welcome to Ibda</Text></View></View>
   </StudioCard>
   <View className="my-5 w-full flex-row gap-2">
    <FeatureTile icon="brand" title="Voice Sync" description={"Deep tone\nmemory"} />
    <FeatureTile icon="calendar" title="Rhythm" description={"Contextual\nqueue"} />
    <FeatureTile icon="spark" title="Omnichannel" description={"Native\naesthetics"} />
   </View>
   <Pressable accessibilityRole="button" onPress={() => router.push("/sign-up")} className="min-h-[48px] w-full flex-row items-center justify-center gap-2 rounded-[18px] bg-[#C24A3C] active:bg-[#A63F32] px-5"><Text variant="button" tone="white">Get Started</Text><StudioIcon name="arrow" size={19} color="#FAF8F4" /></Pressable>
   <Pressable accessibilityRole="button" onPress={() => router.push("/sign-in")} className="mt-3 min-h-[48px] w-full flex-row items-center justify-center rounded-[18px] bg-[#F4F0EA] px-3"><Text variant="label" tone="charcoal" className="text-center">Already have an account?{" "}<Text tone="coral" style={{ fontWeight: "600" }}>Sign in</Text></Text></Pressable>
   <Text variant="caption" tone="secondary" className="mt-6 text-center">Create with purpose. Grow with Ibda.</Text>
  </ScrollView>
 </SafeAreaView>
);
}
