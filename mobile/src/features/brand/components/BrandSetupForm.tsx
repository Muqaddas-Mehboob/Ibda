import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";
import { useState } from "react";
import { ActivityIndicator, Alert, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import {
  createBrand,
  type BrandInput,
} from "../services/brand.service";

const INDUSTRIES = [
  "Technology",
  "Fashion & Beauty",
  "Food & Beverage",
  "Education",
  "Health & Wellness",
  "Other",
];

export function BrandSetupForm() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [description, setDescription] = useState("");
  const [website, setWebsite] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert("Brand name required", "Please enter your brand name.");
      return;
    }

    if (!industry) {
      Alert.alert(
        "Choose an industry",
        "Select the industry that best fits your brand."
      );
      return;
    }

    if (!description.trim()) {
      Alert.alert(
        "Tell us about your brand",
        "Add a short description of your brand."
      );
      return;
    }

    const brandData: BrandInput = {
      name: name.trim(),
      industry,
      description: description.trim(),
      website: website.trim(),
    };

    try {
      setLoading(true);
      await createBrand(brandData);
      router.replace("/dashboard");
    } catch (error) {
      Alert.alert(
        "Couldn't save your brand",
        error instanceof Error
          ? error.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    "mt-2 rounded-[18px] border border-[#E2D9CF] bg-[#F4F0EA] px-4 py-4 text-base text-[#25221F]";

  return (
    <ScrollView
      className="flex-1 bg-[#FAF8F4]"
      contentContainerStyle={{
        paddingHorizontal: 24,
        paddingTop: 16,
        paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
      }}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      <View className="mb-6 flex-row items-center justify-between">
        <Pressable
          onPress={() => router.back()}
          accessibilityRole="button"
          className="h-11 w-11 items-center justify-center rounded-full border border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA]"
        >
          <Text className="text-2xl text-[#25221F]">←</Text>
        </Pressable>

        <Pressable
          onPress={() => router.replace("/dashboard")}
          accessibilityRole="button"
          className="rounded-2xl px-4 py-3"
        >
          <Text className="font-semibold text-[#25221F] text-[14px] leading-[22px]" variant="button">
            Skip for now
          </Text>
        </Pressable>
      </View>

      <View className="mb-6 rounded-[24px] bg-[#F4F0EA] p-5">
        <Text className="mb-3 text-[14px] leading-[22px] font-semibold uppercase tracking-[2px] text-[#25221F]" variant="eyebrow" tone="olive">
          LET&apos;S GET STARTED
        </Text>

        <Text className="text-[22px] tracking-[-0.3px] font-bold leading-[30px] text-[#25221F]" variant="page" tone="olive">
          Tell us about{"\n"}your brand.
        </Text>

        <Text className="mt-4 text-[14px] leading-6 text-[#25221F]" variant="body">
          Help Ibda understand your business so it can create content that
          feels like you.
        </Text>
      </View>

      <View className="mb-6">
        <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
          Brand name *
        </Text>

        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="e.g. Studio Bloom"
          placeholderTextColor="#25221F"
          className={inputClass}
          autoCapitalize="words"
          returnKeyType="next"
          editable={!loading}
        />
      </View>

      <View className="mb-6">
        <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
          What industry are you in? *
        </Text>

        <View className="mt-3 flex-row flex-wrap gap-2">
          {INDUSTRIES.map((item) => {
            const selected = industry === item;

            return (
              <Pressable
                key={item}
                onPress={() => setIndustry(item)}
                disabled={loading}
                className={`rounded-2xl border px-4 py-3 ${selected
                    ? "border-[#C24A3C] bg-[#C24A3C] active:bg-[#25221F]"
                    : "border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA]"
                  }`}
              >
                <Text
                  className={`text-[14px] leading-[22px] font-medium ${selected ? "text-[#FAF8F4]" : "text-[#25221F]"
                    }`} variant="button"
                >
                  {item}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View className="mb-6">
        <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
          About your brand *
        </Text>

        <TextInput
          value={description}
          onChangeText={setDescription}
          placeholder="What do you do? Who are your customers? What makes your brand special?"
          placeholderTextColor="#25221F"
          multiline
          textAlignVertical="top"
          className={inputClass}
          style={{ minHeight: 130 }}
          editable={!loading}
        />

        <Text className="mt-2 text-[12px] leading-[23px] text-[#25221F]" variant="caption">
          A few sentences will help Ibda create more relevant content.
        </Text>
      </View>

      <View className="mb-6 rounded-[24px] bg-[#F4F0EA] p-5">
        <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
          Website
          <Text className="font-normal text-[#25221F] text-[14px] leading-[22px]" variant="label"> (optional)</Text>
        </Text>

        <TextInput
          value={website}
          onChangeText={setWebsite}
          placeholder="https://yourbrand.com"
          placeholderTextColor="#25221F"
          className={inputClass}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          editable={!loading}
        />
      </View>

      <Pressable
        onPress={handleSave}
        disabled={loading}
        className={`min-h-[48px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-3 ${loading ? "opacity-70" : ""
          }`}
      >
        {loading ? (
          <ActivityIndicator color="#FAF8F4" />
        ) : (
          <Text className="text-[14px] leading-[22px] font-bold text-[#FAF8F4]" variant="label">
            Create my brand →
          </Text>
        )}
      </Pressable>

      <Text className="mt-4 text-center text-[12px] leading-[23px] text-[#25221F]" variant="caption">
        You can update your brand details anytime.
      </Text>
    </ScrollView>
  );
}
