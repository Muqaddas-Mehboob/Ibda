
import { router } from "expo-router";
import {
  Pressable,
  ScrollView,
  StatusBar,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

function FeatureTile({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <View className="min-w-0 flex-1 items-center justify-center rounded-xl bg-ibda-surface px-1 py-4">
      <Text className="mb-2 text-lg text-ibda-coral">{icon}</Text>
      <Text
        numberOfLines={1}
        adjustsFontSizeToFit
        className="max-w-full text-center text-xs font-bold text-ibda-charcoal"
      >
        {title}
      </Text>
      <Text className="mt-1 text-center text-[11px] leading-4 text-ibda-brown">
        {description}
      </Text>
    </View>
  );
}

export function LandingScreen() {
  const { width } = useWindowDimensions();
  const compact = width < 380;

  return (
    <SafeAreaView className="flex-1 bg-ibda-background" backgroundColor="#FCF9F4">
      <StatusBar barStyle="dark-content"/>

      <ScrollView
        className="w-full flex-1"
        contentContainerStyle={{
          width: "100%",
          paddingHorizontal: compact ? 16 : 24,
          paddingTop: 12,
          paddingBottom: 28,
        }}
        showsVerticalScrollIndicator={false}
        bounces={false}
      >
        {/* Brand header */}
        <View className="mb-6 w-full flex-row items-center justify-between">
          <View className="flex-row items-center">
            <View className="mr-2.5 h-9 w-9 items-center justify-center rounded-full bg-[#281D2C]">
              <Text className="text-xl font-bold text-white">i</Text>
            </View>
            <Text className="text-xl font-extrabold text-ibda-charcoal">
              ibda
            </Text>
          </View>

          <Text className="text-[10px] font-bold tracking-widest text-ibda-brown">
            CREATIVE STUDIO
          </Text>
        </View>

        {/* Hero artwork */}
        <View className="w-full overflow-hidden rounded-[28px] bg-[#E7DED1] p-4">
          <View className="h-[170px] w-full items-center justify-center">
            <View className="absolute left-2 top-2 h-24 w-16 rotate-[-8deg] bg-[#F7F2E9]" />
            <View className="absolute right-1 top-3 h-24 w-14 rotate-[6deg] bg-[#D0C3B1]" />
            <View className="absolute bottom-2 left-8 h-12 w-20 rotate-[5deg] bg-[#C6B8A5]" />

            <View className="z-10 w-[72%] items-center border border-[#D8CEC0] bg-[#FCF9F4] px-4 py-5">
              <Text className="text-2xl font-semibold text-ibda-charcoal">
                Ibda
              </Text>
              <Text className="mt-1 text-xs text-ibda-brown">
                Welcome to Ibda
              </Text>
            </View>
          </View>

          <View className="w-full flex-row items-center rounded-2xl bg-ibda-background px-3 py-3">
            <View className="mr-3 h-10 w-10 items-center justify-center rounded-full bg-[#281D2C]">
              <Text className="text-lg text-white">✦</Text>
            </View>
            <View className="min-w-0 flex-1">
              <Text className="text-sm font-bold text-ibda-brown">
                Brand Voice AI
              </Text>
              <Text
                numberOfLines={1}
                className="text-xs text-ibda-charcoal"
              >
                Architectural & Poetic
              </Text>
            </View>
          </View>
        </View>

        {/* Intro label */}
        <View className="mt-6 items-center">
          <View className="max-w-full rounded-full bg-ibda-lavender px-3 py-2">
            <Text className="text-center text-xs font-semibold text-ibda-brown">
              ✦  Autonomous Publishing
            </Text>
          </View>

          <Text
            adjustsFontSizeToFit
            className={`mt-5 w-full text-center font-extrabold tracking-tight text-ibda-charcoal ${
              compact ? "text-[32px] leading-[38px]" : "text-[38px] leading-[44px]"
            }`}
          >
            Curated AI for{"\n"}modern creators.
          </Text>

          <Text className="mt-4 w-full text-center text-sm leading-[22px] text-ibda-brown">
            Autonomous publishing, deep brand voice
            {"\n"}memory, and cross-channel editorial
            {"\n"}intelligence.
          </Text>
        </View>

        {/* Responsive feature cards */}
        <View className="mt-6 w-full flex-row gap-2">
          <FeatureTile
            icon="⚙"
            title="Voice Sync"
            description={"Deep tone\nmemory"}
          />
          <FeatureTile
            icon="▦"
            title="Rhythm"
            description={"Contextual\nqueue"}
          />
          <FeatureTile
            icon="✳"
            title="Omnichannel"
            description={"Native\naesthetics"}
          />
        </View>

        {/* Actions */}
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/sign-up")}
          className="mt-7 min-h-[54px] w-full flex-row items-center justify-center rounded-full bg-ibda-coral active:opacity-80"
        >
          <Text className="text-base font-bold text-white">
            Get Started
          </Text>
          <Text className="ml-2 text-lg text-white">→</Text>
        </Pressable>

        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/sign-in")}
          className="mt-3 min-h-[52px] w-full flex-row items-center justify-center rounded-full bg-[#ECE8E3] px-3 active:opacity-80"
        >
          <Text className="text-center text-sm font-semibold text-ibda-charcoal">
            Already have an account?{" "}
            <Text className="font-bold text-ibda-coral">Sign in</Text>
          </Text>
        </Pressable>

        {/* Footer */}
        <Text className="mt-6 text-center text-xs leading-5 text-ibda-brown">
          Create with purpose. Grow with Ibda.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}