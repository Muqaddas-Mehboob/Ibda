import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
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
    "mt-2 rounded-2xl border border-[#EAE4DC] bg-white px-4 py-3 text-base text-[#24221F]";

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 32,
          paddingBottom: 48,
        }}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
      >
        <Pressable
          onPress={() => router.back()}
          disabled={saving}
          accessibilityRole="button"
          className="mb-7 min-h-11 self-start justify-center"
        >
          <Text className="text-base font-medium text-[#705B52]">
            ← Back to Brand Memory
          </Text>
        </Pressable>

        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          BRAND MEMORY
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">
          Create a brand voice
        </Text>
        <Text className="mb-8 mt-3 text-base leading-6 text-[#827970]">
          Add your brand details and voice so Ibda can create content that
          sounds like you.
        </Text>

        {createdBrand && (
          <View className="mb-5 rounded-2xl border border-[#E7C8A2] bg-[#FFF7EA] p-4">
            <Text className="font-semibold text-[#75562F]">
              {createdBrand.name} has been created. Its voice could not be
              saved yet. Retry below to save the voice without creating another
              brand.
            </Text>
          </View>
        )}

        <Text className="mb-4 text-xl font-bold text-[#24221F]">
          Brand information
        </Text>

        <View className="mb-5">
          <Text className="font-semibold text-[#24221F]">
            Brand name <Text className="text-[#FF6B5F]">*</Text>
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="e.g. Studio Bloom"
            placeholderTextColor="#A39A91"
            autoCapitalize="words"
            returnKeyType="next"
            editable={!saving && !createdBrand}
            className={inputClass}
            accessibilityLabel="Brand name, required"
          />
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#24221F]">Industry</Text>
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
                  className={`min-h-11 justify-center rounded-full border px-4 py-2 ${
                    selected
                      ? "border-[#FF6B5F] bg-[#FF6B5F]"
                      : "border-[#EAE4DC] bg-white"
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

        <View className="mb-5">
          <Text className="font-semibold text-[#24221F]">Description</Text>
          <TextInput
            value={description}
            onChangeText={setDescription}
            placeholder="What does your brand do?"
            placeholderTextColor="#A39A91"
            multiline
            textAlignVertical="top"
            editable={!saving && !createdBrand}
            className={inputClass}
            style={{ minHeight: 96 }}
          />
        </View>

        <View className="mb-8">
          <Text className="font-semibold text-[#24221F]">Website</Text>
          <TextInput
            value={website}
            onChangeText={setWebsite}
            placeholder="https://yourbrand.com"
            placeholderTextColor="#A39A91"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            editable={!saving && !createdBrand}
            className={inputClass}
          />
        </View>

        <Text className="mb-2 text-xl font-bold text-[#24221F]">
          Brand voice
        </Text>
        <Text className="mb-4 leading-5 text-[#827970]">
          Set the style and rules Ibda should follow.
        </Text>

        <Text className="font-semibold text-[#24221F]">Tone</Text>
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
                className={`min-h-11 justify-center rounded-full border px-4 py-2 ${
                  selected
                    ? "border-[#FF6B5F] bg-[#F8E3DF]"
                    : "border-[#EAE4DC] bg-white"
                }`}
              >
                <Text className="font-medium text-[#24221F]">{tone}</Text>
              </Pressable>
            );
          })}
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#24221F]">
            Target audience
          </Text>
          <TextInput
            value={voice.target_audience}
            onChangeText={(value) => updateVoice("target_audience", value)}
            placeholder="Who are you speaking to?"
            placeholderTextColor="#A39A91"
            editable={!saving}
            className={inputClass}
          />
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#24221F]">Language</Text>
          <TextInput
            value={voice.language}
            onChangeText={(value) => updateVoice("language", value)}
            placeholder="e.g. English"
            placeholderTextColor="#A39A91"
            autoCapitalize="words"
            editable={!saving}
            className={inputClass}
          />
        </View>

        <View className="mb-5">
          <Text className="font-semibold text-[#24221F]">
            Writing guidelines
          </Text>
          <TextInput
            value={voice.writing_guidelines}
            onChangeText={(value) => updateVoice("writing_guidelines", value)}
            placeholder="Words to use or avoid, style rules, formatting..."
            placeholderTextColor="#A39A91"
            multiline
            textAlignVertical="top"
            editable={!saving}
            className={inputClass}
            style={{ minHeight: 120 }}
          />
        </View>

        <View className="mb-6">
          <Text className="font-semibold text-[#24221F]">
            Example content
          </Text>
          <TextInput
            value={voice.example_content}
            onChangeText={(value) => updateVoice("example_content", value)}
            placeholder="Add an example that captures your brand voice"
            placeholderTextColor="#A39A91"
            multiline
            textAlignVertical="top"
            editable={!saving}
            className={inputClass}
            style={{ minHeight: 130 }}
          />
        </View>

        {!!error && (
          <Text accessibilityRole="alert" className="mb-4 text-[#B04438]">
            {error}
          </Text>
        )}

        <Pressable
          onPress={() => void handleSave()}
          disabled={saving}
          accessibilityRole="button"
          className={`min-h-14 flex-row items-center justify-center rounded-2xl bg-[#FF6B5F] px-5 py-4 ${
            saving ? "opacity-70" : ""
          }`}
        >
          {saving ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text className="font-bold text-white">
              {createdBrand ? "Retry saving voice" : "Create New Brand Voice"}
            </Text>
          )}
        </Pressable>
      </ScrollView>
    </View>
  );
}
