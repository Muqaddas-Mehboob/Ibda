import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable } from "../../../components/ui/StudioControls";

import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { getBrandVoice, type BrandVoice } from "../services/brandMemory.service";
import {
  deleteBrand,
  getBrand,
} from "../../brand/services/brand.service";
import { confirmAsync } from "../../../lib/confirm";

export function BrandVoiceBlueprintScreen() {
  const { brandId } = useLocalSearchParams<{ brandId: string }>();
  const router = useRouter();
  const [voice, setVoice] = useState<BrandVoice | null>(null);
  const [brandName, setBrandName] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!brandId) {
      setError("No brand selected.");
      setLoading(false);
      return;
    }
    Promise.all([getBrandVoice(brandId), getBrand(brandId)])
      .then(([loadedVoice, brand]) => {
        setVoice(loadedVoice);
        setBrandName(brand.name);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Unable to load blueprint.")
      )
      .finally(() => setLoading(false));
  }, [brandId]);

  const deleteCurrentBrand = async () => {
    if (!brandId || deleting) return;

    const confirmed = await confirmAsync(
      "Delete this brand?",
      `"${brandName || "This brand"}" and its brand voice, content, approvals, schedules and notifications will be permanently deleted. This can't be undone.`,
      {
        confirmText: "Delete brand",
        destructive: true,
      }
    );
    if (!confirmed) return;

    setDeleting(true);
    setError("");
    try {
      await deleteBrand(brandId);
      const deletedName = brandName || "Your brand";
      setVoice(null);
      setBrandName("");
      router.dismissTo({
        pathname: "/brand-memory",
        params: { deleted: "1", deletedBrand: deletedName },
      });
    } catch (e) {
      Alert.alert(
        "Couldn’t delete brand",
        e instanceof Error
          ? e.message
          : "We couldn't delete this brand. Nothing was removed, so you can try again."
      );
    } finally {
      setDeleting(false);
    }
  };

  const item = (title: string, value?: string) => (
    <View className="mb-5 border-b border-[#E2D9CF] pb-6" key={title}>
      <Text className="mb-2 text-[12px] font-bold uppercase tracking-wider text-[#25221F]" variant="eyebrow" tone="olive">
        {title}
      </Text>
      <Text className="text-[14px] leading-6 text-[#25221F]" variant="body">
        {value?.trim() || "Not added yet"}
      </Text>
    </View>
  );

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 16, width: "100%", maxWidth: 960, alignSelf: "center" }}>
        <Pressable onPress={() => router.back()}>
          <Text className="mb-6 text-[14px] leading-[22px] text-[#25221F]" variant="button">← Back to voice</Text>
        </Pressable>
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#25221F]" variant="eyebrow" tone="olive">
          BRAND MEMORY
        </Text>
        <Text className="text-[22px] leading-[30px] tracking-[-0.4px] font-bold text-[#25221F]" variant="page" tone="olive">Voice blueprint</Text>
        <Text className="mb-7 mt-3 text-[#25221F] text-[14px] leading-[22px]" variant="body">
          A clear reference for creating consistent, on-brand content.
        </Text>

        {loading ? (
          <ActivityIndicator size="large" color="#C24A3C" />
        ) : error ? (
          <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">{error}</Text>
        ) : voice ? (
          <>
            {item("Brand tone", voice.tone)}
            {item("Target audience", voice.target_audience)}
            {item("Language", voice.language)}
            {item("Writing rules", voice.writing_guidelines)}
            {item("Example content", voice.example_content)}

            <Pressable
              onPress={() =>
                router.replace({
                  pathname: "/brand-memory/[brandId]",
                  params: { brandId },
                })
              }
              className="mb-3 items-center rounded-2xl bg-[#C24A3C] active:bg-[#A63F32] py-4"
            >
              <Text className="font-bold text-[#FAF8F4] text-[14px] leading-[22px]" variant="button">Edit brand voice</Text>
            </Pressable>

            <Pressable
              disabled={deleting}
              onPress={() => void deleteCurrentBrand()}
              accessibilityRole="button"
              accessibilityLabel="Delete current brand. Permanently delete this brand."
              className={`mb-6 items-center rounded-2xl border border-[#F4F0EA] bg-[#FAF8F4] py-4 ${
                deleting ? "opacity-60" : ""
              }`}
            >
              <Text className="font-bold text-[#25221F] text-[14px] leading-[22px]" variant="button">
                {deleting ? "Deleting brand..." : "Delete Current Brand"}
              </Text>
            </Pressable>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}
