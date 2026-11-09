import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput, StudioCard } from "../../../components/ui/StudioControls";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, View } from "react-native";
import { Image } from "expo-image";
import {
  launchImageLibraryAsync,
  type ImagePickerAsset,
} from "expo-image-picker";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
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
  uploadContentImage,
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
  const router = useRouter();
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
  const [selectedImage, setSelectedImage] =
    useState<ImagePickerAsset | null>(null);

  const [savedPost, setSavedPost] =
    useState<ContentPost | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [loadingBrands, setLoadingBrands] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [geoResult, setGeoResult] =
    useState<GEOOptimizeResult | null>(null);
  const [error, setError] = useState("");

  const canEdit = !generating && !saving && !optimizing && !uploadingImage;

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

  const handleSelectImage = async () => {
    if (!canEdit) return;
    setError("");

    try {
      const result = await launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsEditing: true,
        quality: 0.9,
      });
      const asset = result.assets?.[0];
      if (result.canceled || !asset) return;
      if (asset.mimeType && asset.mimeType.toLowerCase() !== "image/jpeg") {
        setError("Instagram feed posts require a JPEG image.");
        return;
      }

      setSelectedImage(asset);
      setSubmitted(false);
    } catch (pickerError) {
      setError(
        getErrorMessage(pickerError, "Unable to select this image.")
      );
    }
  };

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

    let post = savedPost
      ? await updateContent(savedPost.id, input)
      : await saveContent({ ...input, brand_id: brandId });

    if (selectedImage) {
      setSavedPost(post);
      setUploadingImage(true);
      try {
        post = await uploadContentImage(post.id, selectedImage);
        setSelectedImage(null);
      } finally {
        setUploadingImage(false);
      }
    }

    return post;
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
        post.content_type !== contentType ||
        selectedImage !== null
      ) {
        post = await saveDraft();
      }

      if (!post) return;
      if (platform === "instagram" && !post.image_url) {
        setError("Attach a JPEG image before submitting an Instagram post.");
        return;
      }

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
          onPress={() =>
            router.canGoBack() ? router.back() : router.replace("/dashboard")
          }
          accessibilityRole="button"
          accessibilityLabel="Go back"
          className="mb-8 h-11 w-11 items-center justify-center rounded-full border border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
        >
          <Text className="text-xl text-[#716A64]">‹</Text>
        </Pressable>
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="coral">
          IBDA WORKSPACE
        </Text>

        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
          AI Content Studio
        </Text>

        <Text className="mb-7 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          Create on-brand social content with your saved brand
          details and voice.
        </Text>

        <StudioCard className="rounded-[24px] border border-[#E9E2DA] bg-white p-5">
        <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
          Brand
        </Text>

        {loadingBrands ? (
          <View className="mt-3 flex-row items-center rounded-2xl border border-[#E9E2DA] bg-white p-4">
            <ActivityIndicator color="#C24A3C" />
            <Text className="ml-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Loading your brands...
            </Text>
          </View>
        ) : error && brands.length === 0 ? (
          <View className="mt-2 rounded-2xl border border-[#EAC5BE] bg-white p-4">
            <Text
              accessibilityRole="alert"
              className="text-[#A33D34] text-[15px] leading-[24px]" variant="body"
            >
              {error}
            </Text>

            <Pressable
              onPress={() => void loadBrands()}
              className="mt-3 min-h-[54px] self-start justify-center rounded-[18px]"
            >
              <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="button">
                Retry loading brands
              </Text>
            </Pressable>
          </View>
        ) : brands.length === 0 ? (
          <View className="mt-2 rounded-2xl border border-[#E9E2DA] bg-white p-4">
            <Text className="text-[#716A64] text-[15px] leading-[24px]" variant="body">
              You need a saved brand before you can generate content.
            </Text>

            <Pressable
              onPress={() => void loadBrands()}
              className="mt-3 self-start"
            >
              <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="button">
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
                  className={`min-h-[54px] justify-center rounded-[18px] border px-4 py-2 ${
                    selected
                      ? "border-[#C24A3C] bg-[#C24A3C] active:bg-[#A63F32]"
                      : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                  }`}
                >
                  <Text
                    className={`font-medium ${
                      selected
                        ? "text-white"
                        : "text-[#716A64]"
                    }`} variant="button"
                  >
                    {brand.name}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        )}

        {selectedBrand && (
          <Text className="mt-2 text-[15px] leading-[24px] text-[#716A64]" variant="body">
            Voice defaults:{" "}
            {selectedBrand.voice?.tone || "Friendly"} ·{" "}
            {selectedBrand.voice?.language || "English"}
          </Text>
        )}

        <Text className="mt-6 font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
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
                  if (item.value !== "instagram") setSelectedImage(null);
                }}
                disabled={!canEdit}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                className={`min-h-[54px] justify-center rounded-[18px] border px-4 py-2 ${
                  selected
                    ? "border-[#C24A3C] bg-[#F8E3DF]"
                    : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                }`}
              >
                <Text className="font-medium text-[#292724] text-[15px] leading-[24px]" variant="button">
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text className="mt-6 font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
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
                className={`min-h-[54px] justify-center rounded-[18px] border px-4 py-2 ${
                  selected
                    ? "border-[#C24A3C] bg-[#F8E3DF]"
                    : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                }`}
              >
                <Text className="font-medium text-[#292724] text-[15px] leading-[24px]" variant="button">
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        </StudioCard>

        <StudioCard className="mt-6 rounded-[24px] border border-[#E9E2DA] bg-white p-5">
        <View>
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Topic or campaign{" "}
            <Text className="text-[#C24A3C]">*</Text>
          </Text>

          <TextInput
            value={topic}
            onChangeText={setTopic}
            placeholder="What should this post be about?"
            placeholderTextColor="#716A64"
            editable={canEdit}
            maxLength={300}
            returnKeyType="next"
            className={fieldClass}
          />
        </View>

        <View className="mt-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Keywords
          </Text>

          <TextInput
            value={keywords}
            onChangeText={setKeywords}
            placeholder="Add keywords separated by commas"
            placeholderTextColor="#716A64"
            editable={canEdit}
            maxLength={720}
            autoCapitalize="none"
            className={fieldClass}
          />
        </View>

        <View className="mt-5">
          <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
            Call to action
          </Text>

          <TextInput
            value={callToAction}
            onChangeText={setCallToAction}
            placeholder="e.g. Explore the collection"
            placeholderTextColor="#716A64"
            editable={canEdit}
            maxLength={300}
            className={fieldClass}
          />
        </View>

        <View className="mt-5 flex-row gap-3">
          <View className="flex-1">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Tone
            </Text>

            <TextInput
              value={tone}
              onChangeText={setTone}
              placeholder="Friendly"
              placeholderTextColor="#716A64"
              editable={canEdit}
              className={fieldClass}
            />
          </View>

          <View className="flex-1">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Language
            </Text>

            <TextInput
              value={language}
              onChangeText={setLanguage}
              placeholder="English"
              placeholderTextColor="#716A64"
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
          className={`mt-7 min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-4 ${
            !canEdit || loadingBrands || brands.length === 0
              ? "opacity-70"
              : ""
          }`}
        >
          {generating ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text className="font-bold text-white text-[15px] leading-[24px]" variant="label">
              {content
                ? "Regenerate Content"
                : "Generate Content"}
            </Text>
          )}
        </Pressable>

        </StudioCard>

        {!!error && (
          <View className="mt-5 rounded-2xl border border-[#EAC5BE] bg-white p-4">
            <Text
              accessibilityRole="alert"
              className="text-[#A33D34] text-[15px] leading-[24px]" variant="body"
            >
              {error}
            </Text>
          </View>
        )}

        {!!content && (
          <StudioCard className="mt-6 rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="mb-3 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="coral">
              CONTENT PREVIEW
            </Text>

            {savedPost && (
              <Text className="mb-3 text-[15px] leading-[24px] font-medium text-[#716A64]" variant="label">
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
              className="min-h-40 rounded-[18px] border border-[#E9E2DA] bg-[#FAF8F4] px-4 py-4 text-base leading-6 text-[#292724]"
            />

            <Text className="mt-2 text-[12px] text-[#716A64]" variant="caption">
              Edit the text above before saving or submitting.
            </Text>

            {platform === "instagram" ? (
              <View className="mt-5 rounded-2xl border border-[#E9E2DA] bg-[#FAF8F4] p-4">
                <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                  Instagram feed image
                </Text>
                <Text className="mt-1 text-[15px] leading-[23px] text-[#716A64]" variant="body">
                  Choose a JPEG image up to 8 MB. It will be stored in a public
                  Supabase bucket so Instagram can fetch it.
                </Text>

                {selectedImage?.uri || savedPost?.image_url ? (
                  <Image
                    source={{
                      uri: selectedImage?.uri || savedPost?.image_url || "",
                    }}
                    contentFit="cover"
                    className="mt-3 h-56 w-full rounded-xl"
                    accessibilityLabel="Instagram feed image preview"
                  />
                ) : (
                  <Text className="mt-3 rounded-xl bg-white p-3 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                    Add one image before submitting this Instagram post for
                    approval.
                  </Text>
                )}

                <Pressable
                  onPress={() => void handleSelectImage()}
                  disabled={!canEdit}
                  accessibilityRole="button"
                  className={`mt-3 min-h-[54px] items-center justify-center rounded-[18px] border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-4 py-3 ${
                    !canEdit ? "opacity-60" : ""
                  }`}
                >
                  <Text className="font-semibold text-[#716A64] text-[15px] leading-[24px]" variant="button">
                    {selectedImage
                      ? "Choose another JPEG"
                      : savedPost?.image_url
                        ? "Replace image"
                        : "Choose JPEG"}
                  </Text>
                </Pressable>
                {uploadingImage ? (
                  <View className="mt-3 flex-row items-center">
                    <ActivityIndicator color="#C24A3C" />
                    <Text className="ml-2 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      Uploading image...
                    </Text>
                  </View>
                ) : null}
              </View>
            ) : null}

            <Pressable
              onPress={() => void handleOptimizeGEO()}
              disabled={!canEdit || !brandId || !content.trim()}
              accessibilityRole="button"
              className={`mt-4 min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#51445F] active:bg-[#40354B] px-4 py-3 ${
                !canEdit || !brandId || !content.trim()
                  ? "opacity-60"
                  : ""
              }`}
            >
              {optimizing ? (
                <>
                  <ActivityIndicator color="#FFFFFF" />
                  <Text className="ml-2 font-bold text-white text-[15px] leading-[24px]" variant="label">
                    Optimizing for GEO...
                  </Text>
                </>
              ) : (
                <Text className="font-bold text-white text-[15px] leading-[24px]" variant="label">
                  Optimize for GEO
                </Text>
              )}
            </Pressable>

            {geoResult && (
              <View className="mt-6 rounded-[24px] border border-[#EEE7F1] border-l-[3px] border-l-[#826C8B] bg-[#EEE7F1] p-5">
                <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle" tone="plum">
                  GEO Improvements
                </Text>

                {geoResult.improvements.length === 0 ? (
                  <Text className="mt-2 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                    No major improvements were identified.
                  </Text>
                ) : (
                  geoResult.improvements.map(
                    (improvement, index) => (
                      <Text
                        key={index}
                        className="mt-3 text-[15px] leading-6 text-[#716A64]" variant="body"
                      >
                        {index + 1}. {improvement}
                      </Text>
                    )
                  )
                )}

                {geoResult.optimized_content.trim() ? (
                  <>
                    <Text className="mt-6 font-bold text-[#292724] text-[15px] leading-[24px]" variant="label">
                      GEO-Refined Content
                    </Text>

                    <View className="mt-3 rounded-xl border border-[#E9E2DA] bg-white p-5">
                      <Text
                        selectable
                        className="text-base leading-6 text-[#292724]" variant="body"
                      >
                        {geoResult.optimized_content}
                      </Text>
                    </View>

                    <Pressable
                      onPress={handleApplyGEO}
                      disabled={!canEdit}
                      accessibilityRole="button"
                      className={`mt-4 min-h-[54px] items-center justify-center rounded-[18px] bg-[#292724] px-4 py-3 ${
                        !canEdit ? "opacity-60" : ""
                      }`}
                    >
                      <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                        Apply Optimized Content
                      </Text>
                    </Pressable>
                  </>
                ) : (
                  <View className="mt-5 rounded-xl border border-[#E9E2DA] bg-white p-5">
                    <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                      Additional Brand Details Needed
                    </Text>

                    <Text className="mt-2 text-[15px] leading-6 text-[#716A64]" variant="body">
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
              <Text className="mt-4 font-semibold text-[#287D54] text-[15px] leading-[24px]" variant="label">
                Submitted to Approval Inbox successfully.
              </Text>
            )}

            {!submitted && (
              <View className="mt-4 gap-3">
                <Pressable
                  onPress={() => void handleSave()}
                  disabled={!canEdit}
                  accessibilityRole="button"
                  className={`min-h-[54px] items-center justify-center rounded-[18px] border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] px-4 py-3 ${
                    !canEdit ? "opacity-60" : ""
                  }`}
                >
                  <Text className="font-bold text-[#716A64] text-[15px] leading-[24px]" variant="button">
                    {saving ? "Saving..." : "Save Draft"}
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() => void handleSubmitForApproval()}
                  disabled={!canEdit}
                  accessibilityRole="button"
                  className={`min-h-[54px] items-center justify-center rounded-[18px] bg-[#292724] px-4 py-3 ${
                    !canEdit ? "opacity-60" : ""
                  }`}
                >
                  <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                    {saving
                      ? "Saving..."
                      : "Submit for Approval"}
                  </Text>
                </Pressable>
              </View>
            )}
          </StudioCard>
        )}
      </ScrollView>

      <BottomNavigation />
    </View>
  );
}
