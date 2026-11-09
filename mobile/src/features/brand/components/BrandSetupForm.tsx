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
    "mt-2 rounded-[18px] border border-[#E9E2DA] bg-[#F7F4EF] px-4 py-4 text-base text-[#292724]";

  return (
    <ScrollView
      className="flex-1 bg-[#FAF8F4]"
      contentContainerStyle={{
        paddingHorizontal: 24,
        paddingTop: 36,
        paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
      }}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      <View className="mb-6 flex-row items-center justify-between">
        <Pressable
          onPress={() => router.back()}
          accessibilityRole="button"
          className="h-11 w-11 items-center justify-center rounded-full border border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
        >
          <Text className="text-2xl text-[#292724]">←</Text>
        </Pressable>

        <Pressable
          onPress={() => router.replace("/dashboard")}
          accessibilityRole="button"
          className="rounded-2xl px-4 py-3"
        >
          <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="button">
            Skip for now
          </Text>
        </Pressable>
      </View>

      <View className="mb-8">
        <Text className="mb-3 text-[15px] leading-[24px] font-semibold uppercase tracking-[2px] text-[#4A523E]" variant="eyebrow" tone="olive">
          LET&apos;S GET STARTED
        </Text>

        <Text className="text-[32px] tracking-[-0.8px] font-bold leading-[44px] text-[#292724]" variant="page" tone="olive">
          Tell us about{"\n"}your brand.
        </Text>

        <Text className="mt-4 text-base leading-6 text-[#716A64]" variant="body">
          Help Ibda understand your business so it can create content that
          feels like you.
        </Text>
      </View>

      <View className="mb-6">
        <Text className="text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
          Brand name *
        </Text>

        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="e.g. Studio Bloom"
          placeholderTextColor="#716A64"
          className={inputClass}
          autoCapitalize="words"
          returnKeyType="next"
          editable={!loading}
        />
      </View>

      <View className="mb-6">
        <Text className="text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
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
                    ? "border-[#C24A3C] bg-[#C24A3C] active:bg-[#A63F32]"
                    : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                  }`}
              >
                <Text
                  className={`text-[15px] leading-[24px] font-medium ${selected ? "text-white" : "text-[#716A64]"
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
        <Text className="text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
          About your brand *
        </Text>

        <TextInput
          value={description}
          onChangeText={setDescription}
          placeholder="What do you do? Who are your customers? What makes your brand special?"
          placeholderTextColor="#716A64"
          multiline
          textAlignVertical="top"
          className={inputClass}
          style={{ minHeight: 130 }}
          editable={!loading}
        />

        <Text className="mt-2 text-[12px] leading-[23px] text-[#716A64]" variant="caption">
          A few sentences will help Ibda create more relevant content.
        </Text>
      </View>

      <View className="mb-8">
        <Text className="text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
          Website
          <Text className="font-normal text-[#716A64] text-[15px] leading-[24px]" variant="label"> (optional)</Text>
        </Text>

        <TextInput
          value={website}
          onChangeText={setWebsite}
          placeholder="https://yourbrand.com"
          placeholderTextColor="#716A64"
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
        className={`min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-4 ${loading ? "opacity-70" : ""
          }`}
      >
        {loading ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text className="text-base leading-[24px] font-bold text-white" variant="label">
            Create my brand →
          </Text>
        )}
      </Pressable>

      <Text className="mt-4 text-center text-[12px] leading-[23px] text-[#716A64]" variant="caption">
        You can update your brand details anytime.
      </Text>
    </ScrollView>
  );
}
