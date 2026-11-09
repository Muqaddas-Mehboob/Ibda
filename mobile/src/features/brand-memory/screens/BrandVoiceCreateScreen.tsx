import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";
import { useState } from "react";
import { ActivityIndicator, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import {
  createBrand,
  type Brand,
} from "../../brand/services/brand.service";
import {
  saveBrandVoice,
  type BrandVoice,
} from "../services/brandMemory.service";

type BrandVoiceInput = Pick<
  BrandVoice,
  | "tone"
  | "target_audience"
  | "language"
  | "writing_guidelines"
  | "example_content"
>;

const TONES = [
  "Friendly",
  "Professional",
  "Playful",
  "Bold",
  "Educational",
];

const INDUSTRIES = [
  "Technology",
  "Fashion & Beauty",
  "Food & Beverage",
  "Education",
  "Health & Wellness",
  "Other",
];

export function BrandVoiceCreateScreen() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [website, setWebsite] = useState("");
  const [industry, setIndustry] = useState("");
  const [voice, setVoice] = useState<BrandVoiceInput>({
    tone: "Friendly",
    target_audience: "",
    language: "English",
    writing_guidelines: "",
    example_content: "",
  });
  const [createdBrand, setCreatedBrand] = useState<Brand | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const updateVoice = (field: keyof BrandVoiceInput, value: string) => {
    setVoice((current) => ({ ...current, [field]: value }));
  };

  const handleSave = async () => {
    if (saving) return;
    if (!name.trim()) {
      setError("Brand name is required.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      let brand = createdBrand;
      if (!brand) {
        brand = await createBrand({
          name: name.trim(),
          description: description.trim(),
          website: website.trim(),
          industry,
        });
        setCreatedBrand(brand);
      }

      if (!brand.id) {
        throw new Error(
          "The brand was created, but its ID was missing. Please return to Brand Memory and check your brands before trying again."
        );
      }

      await saveBrandVoice(brand.id, voice);
      router.replace({
        pathname: "/brand-memory",
        params: { created: "1" },
      });
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Unable to create this brand voice. Please try again."
      );
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    "mt-2 rounded-[18px] border border-[#E9E2DA] bg-[#F7F4EF] px-4 py-4 text-base text-[#292724]";

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 36,
          paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
        }}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
      >
        <Pressable
          onPress={() => router.back()}
          disabled={saving}
          accessibilityRole="button"
          className="mb-7 min-h-[54px] self-start justify-center rounded-[18px]"
        >
          <Text className="text-base leading-[24px] font-medium text-[#716A64]" variant="button">
            ← Back to Brand Memory
          </Text>
        </Pressable>

        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#4A523E]" variant="eyebrow" tone="olive">
          BRAND MEMORY
        </Text>
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="olive">
          Create a brand voice
        </Text>
        <Text className="mb-8 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          Add your brand details and voice so Ibda can create content that
          sounds like you.
        </Text>

        {createdBrand && (
          <View className="mb-5 rounded-2xl border border-[#E7C8A2] bg-[#FFF7EA] p-4">
            <Text className="font-semibold text-[#75562F] text-[15px] leading-[24px]" variant="label">
              {createdBrand.name} has been created. Its voice could not be
              saved yet. Retry below to save the voice without creating another
              brand.
            </Text>
          </View>
        )}

        <Text className="mb-4 text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
          Brand information
        </Text>

        <View className="mb-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Brand name <Text className="text-[#C24A3C]">*</Text>
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="e.g. Studio Bloom"
            placeholderTextColor="#716A64"
            autoCapitalize="words"
            returnKeyType="next"
            editable={!saving && !createdBrand}
            className={inputClass}
            accessibilityLabel="Brand name, required"
          />
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">Industry</Text>
          <View className="mt-3 flex-row flex-wrap gap-2">
            {INDUSTRIES.map((item) => {
              const selected = industry === item;
              return (
                <Pressable
                  key={item}
                  onPress={() => setIndustry(selected ? "" : item)}
                  disabled={saving || !!createdBrand}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  className={`min-h-[54px] justify-center rounded-[18px] border px-4 py-2 ${
                    selected
                      ? "border-[#C24A3C] bg-[#C24A3C] active:bg-[#A63F32]"
                      : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                  }`}
                >
                  <Text
                    className={`text-[15px] leading-[24px] font-medium ${
                      selected ? "text-white" : "text-[#716A64]"
                    }`} variant="button"
                  >
                    {item}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">Description</Text>
          <TextInput
            value={description}
            onChangeText={setDescription}
            placeholder="What does your brand do?"
            placeholderTextColor="#716A64"
            multiline
            textAlignVertical="top"
            editable={!saving && !createdBrand}
            className={inputClass}
            style={{ minHeight: 96 }}
          />
        </View>

        <View className="mb-8">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">Website</Text>
          <TextInput
            value={website}
            onChangeText={setWebsite}
            placeholder="https://yourbrand.com"
            placeholderTextColor="#716A64"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            editable={!saving && !createdBrand}
            className={inputClass}
          />
        </View>

        <Text className="mb-2 text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
          Brand voice
        </Text>
        <Text className="mb-4 text-[#716A64] text-[15px] leading-[24px]" variant="body">
          Set the style and rules Ibda should follow.
        </Text>

        <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">Tone</Text>
        <View className="mb-5 mt-3 flex-row flex-wrap gap-2">
          {TONES.map((tone) => {
            const selected = voice.tone === tone;
            return (
              <Pressable
                key={tone}
                onPress={() => updateVoice("tone", tone)}
                disabled={saving}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                className={`min-h-[54px] justify-center rounded-[18px] border px-4 py-2 ${
                  selected
                    ? "border-[#7F9C81] bg-[#E5EDE3]"
                    : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                }`}
              >
                <Text className="font-medium text-[#292724] text-[15px] leading-[24px]" variant="button">{tone}</Text>
              </Pressable>
            );
          })}
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Target audience
          </Text>
          <TextInput
            value={voice.target_audience}
            onChangeText={(value) => updateVoice("target_audience", value)}
            placeholder="Who are you speaking to?"
            placeholderTextColor="#716A64"
            editable={!saving}
            className={inputClass}
          />
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">Language</Text>
          <TextInput
            value={voice.language}
            onChangeText={(value) => updateVoice("language", value)}
            placeholder="e.g. English"
            placeholderTextColor="#716A64"
            autoCapitalize="words"
            editable={!saving}
            className={inputClass}
          />
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Writing guidelines
          </Text>
          <TextInput
            value={voice.writing_guidelines}
            onChangeText={(value) => updateVoice("writing_guidelines", value)}
            placeholder="Words to use or avoid, style rules, formatting..."
            placeholderTextColor="#716A64"
            multiline
            textAlignVertical="top"
            editable={!saving}
            className={inputClass}
            style={{ minHeight: 120 }}
          />
        </View>

        <View className="mb-6">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Example content
          </Text>
          <TextInput
            value={voice.example_content}
            onChangeText={(value) => updateVoice("example_content", value)}
            placeholder="Add an example that captures your brand voice"
            placeholderTextColor="#716A64"
            multiline
            textAlignVertical="top"
            editable={!saving}
            className={inputClass}
            style={{ minHeight: 130 }}
          />
        </View>

        {!!error && (
          <Text accessibilityRole="alert" className="mb-4 text-[#B04438] text-[15px] leading-[24px]" variant="body">
            {error}
          </Text>
        )}

        <Pressable
          onPress={() => void handleSave()}
          disabled={saving}
          accessibilityRole="button"
          className={`min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-4 ${
            saving ? "opacity-70" : ""
          }`}
        >
          {saving ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text className="font-bold text-white text-[15px] leading-[24px]" variant="label">
              {createdBrand ? "Retry saving voice" : "Create New Brand Voice"}
            </Text>
          )}
        </Pressable>
      </ScrollView>
    </View>
  );
}
