import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
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
      Alert.alert("Choose an industry", "Select the industry that best fits your brand.");
      return;
    }

    if (!description.trim()) {
      Alert.alert("Tell us about your brand", "Add a short description of your brand.");
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

      Alert.alert(
        "Brand created!",
        "Your brand details have been saved successfully.",
        [
          {
            text: "Continue",
            onPress: () => router.replace("/dashboard"),
          },
        ]
      );
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
    "mt-2 rounded-2xl border border-[#E7E0D7] bg-white px-4 py-4 text-base text-[#29251F]";

  return (
    <ScrollView
      className="flex-1 bg-[#F7F5EF]"
      contentContainerStyle={{
        paddingHorizontal: 24,
        paddingTop: 24,
        paddingBottom: 40,
      }}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      <Pressable
        onPress={() => router.back()}
        className="mb-7 self-start rounded-full border border-[#E7E0D7] bg-white px-4 py-2"
      >
        <Text className="text-sm font-medium text-[#29251F]">
          ← Back
        </Text>
      </Pressable>

      <View className="mb-8">
        <Text className="mb-3 text-sm font-semibold uppercase tracking-[3px] text-[#B66A58]">
          LET'S GET STARTED
        </Text>

        <Text className="text-4xl font-bold leading-[44px] text-[#29251F]">
          Tell us about{"\n"}your brand.
        </Text>

        <Text className="mt-4 text-base leading-6 text-[#756D64]">
          Help Ibda understand your business so it can create content that
          feels like you.
        </Text>
      </View>

      <View className="mb-6">
        <Text className="text-sm font-semibold text-[#29251F]">
          Brand name *
        </Text>

        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="e.g. Studio Bloom"
          placeholderTextColor="#A39A90"
          className={inputClass}
          autoCapitalize="words"
          returnKeyType="next"
          editable={!loading}
        />
      </View>

      <View className="mb-6">
        <Text className="text-sm font-semibold text-[#29251F]">
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
                className={`rounded-full border px-4 py-3 ${
                  selected
                    ? "border-[#FF6B5F] bg-[#FF6B5F]"
                    : "border-[#E7E0D7] bg-white"
                }`}
              >
                <Text
                  className={`text-sm font-medium ${
                    selected ? "text-white" : "text-[#51483F]"
                  }`}
                >
                  {item}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View className="mb-6">
        <Text className="text-sm font-semibold text-[#29251F]">
          About your brand *
        </Text>

        <TextInput
          value={description}
          onChangeText={setDescription}
          placeholder="What do you do? Who are your customers? What makes your brand special?"
          placeholderTextColor="#A39A90"
          multiline
          textAlignVertical="top"
          className={inputClass}
          style={{ minHeight: 130 }}
          editable={!loading}
        />

        <Text className="mt-2 text-xs leading-5 text-[#8A8177]">
          A few sentences will help Ibda create more relevant content.
        </Text>
      </View>

      <View className="mb-8">
        <Text className="text-sm font-semibold text-[#29251F]">
          Website
          <Text className="font-normal text-[#8A8177]"> (optional)</Text>
        </Text>

        <TextInput
          value={website}
          onChangeText={setWebsite}
          placeholder="https://yourbrand.com"
          placeholderTextColor="#A39A90"
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
        className={`min-h-14 flex-row items-center justify-center rounded-2xl bg-[#FF6B5F] px-5 py-4 ${
          loading ? "opacity-70" : ""
        }`}
      >
        {loading ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text className="text-base font-bold text-white">
            Create my brand →
          </Text>
        )}
      </Pressable>

      <Text className="mt-4 text-center text-xs leading-5 text-[#8A8177]">
        You can update your brand details anytime.
      </Text>
    </ScrollView>
  );
}