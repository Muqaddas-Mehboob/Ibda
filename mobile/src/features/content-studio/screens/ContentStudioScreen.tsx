
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  getMemoryBrands,
  type BrandMemoryProfile,
} from "../../brand-memory/services/brandMemory.service";
import {
  generateContent,
  optimizeContentForGEO,
  saveContent,
  submitForApproval,
  updateContent,
  type ContentPost,
  type ContentType,
  type GEOOptimizeResult,
  type SocialPlatform,
} from "../services/content.service";

const PLATFORMS: { label: string; value: SocialPlatform }[] = [
  { label: "Instagram", value: "instagram" },
  { label: "Facebook", value: "facebook" },
  { label: "LinkedIn", value: "linkedin" },
  { label: "TikTok", value: "tiktok" },
  { label: "X", value: "x" },
  { label: "Other", value: "other" },
];

const CONTENT_TYPES: { label: string; value: ContentType }[] = [
  { label: "Caption", value: "caption" },
  { label: "Promotional", value: "promotional" },
  { label: "Educational", value: "educational" },
  { label: "Announcement", value: "announcement" },
];

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function ContentStudioScreen() {
  const { topic: initialTopic } =
    useLocalSearchParams<{ topic?: string }>();

  const [brands, setBrands] = useState<BrandMemoryProfile[]>([]);
  const [brandId, setBrandId] = useState("");
  const [platform, setPlatform] =
    useState<SocialPlatform>("instagram");
  const [contentType, setContentType] =
    useState<ContentType>("caption");

  const [topic, setTopic] = useState(
    typeof initialTopic === "string" ? initialTopic : ""
  );
  const [keywords, setKeywords] = useState("");
  const [callToAction, setCallToAction] = useState("");
  const [tone, setTone] = useState("Friendly");
  const [language, setLanguage] = useState("English");
  const [content, setContent] = useState("");

  const [savedPost, setSavedPost] =
    useState<ContentPost | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [loadingBrands, setLoadingBrands] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [geoResult, setGeoResult] =
    useState<GEOOptimizeResult | null>(null);
  const [error, setError] = useState("");

  const canEdit = !generating && !saving && !optimizing;

  const selectedBrand = useMemo(
    () => brands.find((brand) => brand.id === brandId) ?? null,
    [brands, brandId]
  );

  const loadBrands = useCallback(async () => {
    setLoadingBrands(true);
    setError("");

    try {
      const results = await getMemoryBrands();
      setBrands(results);
      setBrandId((current) =>
        current && results.some((brand) => brand.id === current)
          ? current
          : (results[0]?.id ?? "")
      );
    } catch (loadError) {
      setError(
        getErrorMessage(loadError, "Unable to load your brands.")
      );
    } finally {
      setLoadingBrands(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadBrands();
    }, [loadBrands])
  );

  useEffect(() => {
    if (selectedBrand) {
      setTone(selectedBrand.voice?.tone || "Friendly");
      setLanguage(selectedBrand.voice?.language || "English");
    }
  }, [selectedBrand]);

  const handleGenerate = async () => {
    if (generating || saving || optimizing) return;

    if (!brandId) {
      setError("Create or select a brand before generating content.");
      return;
    }

    if (!topic.trim()) {
      setError("Enter a topic or campaign before generating content.");
      return;
    }

    setGenerating(true);
    setError("");
    setSubmitted(false);
    setGeoResult(null);

    try {
      const result = await generateContent({
        brand_id: brandId,
        platform,
        content_type: contentType,
        topic: topic.trim(),
        tone: tone.trim(),
        language: language.trim(),
        keywords: keywords
          .split(",")
          .map((keyword) => keyword.trim())
          .filter(Boolean),
        call_to_action: callToAction.trim(),
      });

      setContent(result.content);
      setSavedPost(null);
    } catch (generationError) {
      setError(
        getErrorMessage(
          generationError,
          "Unable to generate content. Please try again."
        )
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleOptimizeGEO = async () => {
    if (optimizing || generating || saving) return;

    if (!brandId || !content.trim()) {
      setError("Generate content before optimizing for GEO.");
      return;
    }

    setOptimizing(true);
    setError("");
    setGeoResult(null);

    try {
      const result = await optimizeContentForGEO({
        brand_id: brandId,
        platform,
        content: content.trim(),
      });

      setGeoResult(result);
    } catch (optimizationError) {
      setError(
        getErrorMessage(
          optimizationError,
          "Unable to optimize content for GEO."
        )
      );
    } finally {
      setOptimizing(false);
    }
  };

  const handleApplyGEO = () => {
    if (
      !geoResult ||
      !geoResult.optimized_content.trim() ||
      !canEdit
    ) {
      return;
    }

    setContent(geoResult.optimized_content);
    setGeoResult(null);
    setError("");
    setSubmitted(false);
  };

  const saveDraft = async (): Promise<ContentPost | null> => {
    if (!brandId || !content.trim()) {
      setError("Generate or enter content before saving.");
      return null;
    }

    const title =
      CONTENT_TYPES.find((item) => item.value === contentType)?.label ??
      "Social post";

    const input = {
      title,
      body: content.trim(),
      platform,
      content_type: contentType,
    };

    if (savedPost) {
      return updateContent(savedPost.id, input);
    }

    return saveContent({ ...input, brand_id: brandId });
  };

  const handleSave = async () => {
    if (!canEdit) return;

    setSaving(true);
    setError("");
    setSubmitted(false);

    try {
      const post = await saveDraft();
      if (post) setSavedPost(post);
    } catch (saveError) {
      setError(
        getErrorMessage(saveError, "Unable to save this draft.")
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitForApproval = async () => {
    if (!canEdit) return;

    setSaving(true);
    setError("");
    setSubmitted(false);

    try {
      let post = savedPost;

      if (
        !post ||
        post.body !== content.trim() ||
        post.platform !== platform ||
        post.content_type !== contentType
      ) {
        post = await saveDraft();
      }

      if (!post) return;

      setSavedPost(post);
      await submitForApproval(post.id);
      setSubmitted(true);
      setSavedPost(null);
    } catch (submitError) {
      setError(
        getErrorMessage(
          submitError,
          "Unable to submit this content for approval."
        )
      );
    } finally {
      setSaving(false);
    }
  };

  const fieldClass =
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
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          IBDA WORKSPACE
        </Text>

        <Text className="text-4xl font-bold text-[#24221F]">
          AI Content Studio
        </Text>

        <Text className="mb-7 mt-3 text-base leading-6 text-[#827970]">
          Create on-brand social content with your saved brand
          details and voice.
        </Text>

        <Text className="font-semibold text-[#24221F]">
          Brand
        </Text>

        {loadingBrands ? (
          <View className="mt-3 flex-row items-center rounded-2xl border border-[#EAE4DC] bg-white p-4">
            <ActivityIndicator color="#FF6B5F" />
            <Text className="ml-3 text-[#827970]">
              Loading your brands...
            </Text>
          </View>
        ) : error && brands.length === 0 ? (
          <View className="mt-2 rounded-2xl border border-[#EAC5BE] bg-white p-4">
            <Text
              accessibilityRole="alert"
              className="leading-5 text-[#A33D34]"
            >
              {error}
            </Text>

            <Pressable
              onPress={() => void loadBrands()}
              className="mt-3 min-h-11 self-start justify-center"
            >
              <Text className="font-semibold text-[#FF6B5F]">
                Retry loading brands
              </Text>
            </Pressable>
          </View>
        ) : brands.length === 0 ? (
          <View className="mt-2 rounded-2xl border border-[#EAE4DC] bg-white p-4">
            <Text className="leading-5 text-[#827970]">
              You need a saved brand before you can generate content.
            </Text>

            <Pressable
              onPress={() => void loadBrands()}
              className="mt-3 self-start"
            >
              <Text className="font-semibold text-[#FF6B5F]">
                Retry loading brands
              </Text>
            </Pressable>
          </View>
        ) : (
          <View className="mt-3 flex-row flex-wrap gap-2">
            {brands.map((brand) => {
              const selected = brand.id === brandId;

              return (
                <Pressable
                  key={brand.id}
                  onPress={() => {
                    setBrandId(brand.id);
                    setGeoResult(null);
                    setSavedPost(null);
                    setSubmitted(false);
                  }}
                  disabled={!canEdit}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  className={`min-h-11 justify-center rounded-full border px-4 py-2 ${
                    selected
                      ? "border-[#FF6B5F] bg-[#FF6B5F]"
                      : "border-[#EAE4DC] bg-white"
                  }`}
                >
                  <Text
                    className={`font-medium ${
                      selected
                        ? "text-white"
                        : "text-[#51483F]"
                    }`}
                  >
                    {brand.name}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        )}

        {selectedBrand && (
          <Text className="mt-2 text-sm text-[#827970]">
            Voice defaults:{" "}
            {selectedBrand.voice?.tone || "Friendly"} ·{" "}
            {selectedBrand.voice?.language || "English"}
          </Text>
        )}

        <Text className="mt-6 font-semibold text-[#24221F]">
          Platform
        </Text>

        <View className="mt-3 flex-row flex-wrap gap-2">
          {PLATFORMS.map((item) => {
            const selected = platform === item.value;

            return (
              <Pressable
                key={item.value}
                onPress={() => {
                  setPlatform(item.value);
                  setGeoResult(null);
                }}
                disabled={!canEdit}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                className={`min-h-11 justify-center rounded-full border px-4 py-2 ${
                  selected
                    ? "border-[#FF6B5F] bg-[#F8E3DF]"
                    : "border-[#EAE4DC] bg-white"
                }`}
              >
                <Text className="font-medium text-[#24221F]">
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text className="mt-6 font-semibold text-[#24221F]">
          Content type
        </Text>

        <View className="mt-3 flex-row flex-wrap gap-2">
          {CONTENT_TYPES.map((item) => {
            const selected = contentType === item.value;

            return (
              <Pressable
                key={item.value}
                onPress={() => {
                  setContentType(item.value);
                  setGeoResult(null);
                }}
                disabled={!canEdit}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                className={`min-h-11 justify-center rounded-full border px-4 py-2 ${
                  selected
                    ? "border-[#FF6B5F] bg-[#F8E3DF]"
                    : "border-[#EAE4DC] bg-white"
                }`}
              >
                <Text className="font-medium text-[#24221F]">
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <View className="mt-6">
          <Text className="font-semibold text-[#24221F]">
            Topic or campaign{" "}
            <Text className="text-[#FF6B5F]">*</Text>
          </Text>

          <TextInput
            value={topic}
            onChangeText={setTopic}
            placeholder="What should this post be about?"
            placeholderTextColor="#A39A91"
            editable={canEdit}
            maxLength={300}
            returnKeyType="next"
            className={fieldClass}
          />
        </View>

        <View className="mt-5">
          <Text className="font-semibold text-[#24221F]">
            Keywords
          </Text>

          <TextInput
            value={keywords}
            onChangeText={setKeywords}
            placeholder="Add keywords separated by commas"
            placeholderTextColor="#A39A91"
            editable={canEdit}
            maxLength={720}
            autoCapitalize="none"
            className={fieldClass}
          />
        </View>

        <View className="mt-5">
          <Text className="font-semibold text-[#24221F]">
            Call to action
          </Text>

          <TextInput
            value={callToAction}
            onChangeText={setCallToAction}
            placeholder="e.g. Explore the collection"
            placeholderTextColor="#A39A91"
            editable={canEdit}
            maxLength={300}
            className={fieldClass}
          />
        </View>

        <View className="mt-5 flex-row gap-3">
          <View className="flex-1">
            <Text className="font-semibold text-[#24221F]">
              Tone
            </Text>

            <TextInput
              value={tone}
              onChangeText={setTone}
              placeholder="Friendly"
              placeholderTextColor="#A39A91"
              editable={canEdit}
              className={fieldClass}
            />
          </View>

          <View className="flex-1">
            <Text className="font-semibold text-[#24221F]">
              Language
            </Text>

            <TextInput
              value={language}
              onChangeText={setLanguage}
              placeholder="English"
              placeholderTextColor="#A39A91"
              editable={canEdit}
              className={fieldClass}
            />
          </View>
        </View>

        <Pressable
          onPress={() => void handleGenerate()}
          disabled={
            generating ||
            saving ||
            optimizing ||
            loadingBrands ||
            brands.length === 0
          }
          accessibilityRole="button"
          className={`mt-7 min-h-14 flex-row items-center justify-center rounded-2xl bg-[#FF6B5F] px-5 py-4 ${
            !canEdit || loadingBrands || brands.length === 0
              ? "opacity-70"
              : ""
          }`}
        >
          {generating ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text className="font-bold text-white">
              {content
                ? "Regenerate Content"
                : "Generate Content"}
            </Text>
          )}
        </Pressable>

        {!!error && (
          <View className="mt-5 rounded-2xl border border-[#EAC5BE] bg-white p-4">
            <Text
              accessibilityRole="alert"
              className="leading-5 text-[#A33D34]"
            >
              {error}
            </Text>
          </View>
        )}

        {!!content && (
          <View className="mt-8 rounded-3xl border border-[#EAE4DC] bg-white p-5">
            <Text className="mb-3 text-xs font-bold uppercase tracking-[2px] text-[#FF6B5F]">
              CONTENT PREVIEW
            </Text>

            {savedPost && (
              <Text className="mb-3 text-sm font-medium text-[#827970]">
                Draft saved · {savedPost.status}
              </Text>
            )}

            <TextInput
              value={content}
              onChangeText={(value) => {
                setContent(value);
                setGeoResult(null);

                if (submitted) {
                  setSubmitted(false);
                  setSavedPost(null);
                }
              }}
              multiline
              textAlignVertical="top"
              editable={canEdit}
              accessibilityLabel="Generated content preview. Editable."
              className="min-h-40 rounded-2xl border border-[#EAE4DC] bg-[#FCF9F4] px-4 py-4 text-base leading-6 text-[#24221F]"
            />

            <Text className="mt-2 text-xs text-[#827970]">
              Edit the text above before saving or submitting.
            </Text>

            <Pressable
              onPress={() => void handleOptimizeGEO()}
              disabled={!canEdit || !brandId || !content.trim()}
              accessibilityRole="button"
              className={`mt-4 min-h-12 flex-row items-center justify-center rounded-2xl bg-[#287D54] px-4 py-3 ${
                !canEdit || !brandId || !content.trim()
                  ? "opacity-60"
                  : ""
              }`}
            >
              {optimizing ? (
                <>
                  <ActivityIndicator color="#FFFFFF" />
                  <Text className="ml-2 font-bold text-white">
                    Optimizing for GEO...
                  </Text>
                </>
              ) : (
                <Text className="font-bold text-white">
                  Optimize for GEO
                </Text>
              )}
            </Pressable>

            {geoResult && (
              <View className="mt-4 rounded-2xl border border-[#D5E9DB] bg-[#F1FAF3] p-4">
                <Text className="text-lg font-bold text-[#24221F]">
                  GEO Improvements
                </Text>

                {geoResult.improvements.length === 0 ? (
                  <Text className="mt-2 text-sm text-[#51483F]">
                    No major improvements were identified.
                  </Text>
                ) : (
                  geoResult.improvements.map(
                    (improvement, index) => (
                      <Text
                        key={index}
                        className="mt-3 text-sm leading-6 text-[#51483F]"
                      >
                        {index + 1}. {improvement}
                      </Text>
                    )
                  )
                )}

                {geoResult.optimized_content.trim() ? (
                  <>
                    <Text className="mt-6 font-bold text-[#24221F]">
                      GEO-Refined Content
                    </Text>

                    <View className="mt-3 rounded-xl border border-[#D5E9DB] bg-white p-4">
                      <Text
                        selectable
                        className="text-base leading-6 text-[#24221F]"
                      >
                        {geoResult.optimized_content}
                      </Text>
                    </View>

                    <Pressable
                      onPress={handleApplyGEO}
                      disabled={!canEdit}
                      accessibilityRole="button"
                      className={`mt-4 min-h-12 items-center justify-center rounded-2xl bg-[#24221F] px-4 py-3 ${
                        !canEdit ? "opacity-60" : ""
                      }`}
                    >
                      <Text className="font-bold text-white">
                        Apply Optimized Content
                      </Text>
                    </Pressable>
                  </>
                ) : (
                  <View className="mt-5 rounded-xl border border-[#D5E9DB] bg-white p-4">
                    <Text className="font-semibold text-[#24221F]">
                      Additional Brand Details Needed
                    </Text>

                    <Text className="mt-2 text-sm leading-6 text-[#51483F]">
                      Meaningful GEO refinement requires more verified
                      brand information. Add details such as your
                      location, specific products, services, or unique
                      offerings to improve the content.
                    </Text>
                  </View>
                )}
              </View>
            )}

            {!!submitted && (
              <Text className="mt-4 font-semibold text-[#287D54]">
                Submitted to Approval Inbox successfully.
              </Text>
            )}

            {!submitted && (
              <View className="mt-4 gap-3">
                <Pressable
                  onPress={() => void handleSave()}
                  disabled={!canEdit}
                  accessibilityRole="button"
                  className={`min-h-12 items-center justify-center rounded-2xl border border-[#EAE4DC] bg-white px-4 py-3 ${
                    !canEdit ? "opacity-60" : ""
                  }`}
                >
                  <Text className="font-bold text-[#24221F]">
                    {saving ? "Saving..." : "Save Draft"}
                  </Text>
                </Pressable>

                <Pressable
                  onPress={() => void handleSubmitForApproval()}
                  disabled={!canEdit}
                  accessibilityRole="button"
                  className={`min-h-12 items-center justify-center rounded-2xl bg-[#24221F] px-4 py-3 ${
                    !canEdit ? "opacity-60" : ""
                  }`}
                >
                  <Text className="font-bold text-white">
                    {saving
                      ? "Saving..."
                      : "Submit for Approval"}
                  </Text>
                </Pressable>
              </View>
            )}
          </View>
        )}
      </ScrollView>

      <BottomNavigation />
    </View>
  );
}
