
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
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
      Alert.alert(
        "Brand deleted",
        `"${deletedName}" and its brand-specific data were permanently deleted.`
      );
      router.dismissTo({
        pathname: "/brand-memory",
        params: { deleted: "1" },
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
    <View className="mb-4 rounded-2xl border border-[#EAE4DC] bg-white p-5" key={title}>
      <Text className="mb-2 text-xs font-bold uppercase tracking-wider text-[#FF6B5F]">
        {title}
      </Text>
      <Text className="text-base leading-6 text-[#24221F]">
        {value?.trim() || "Not added yet"}
      </Text>
    </View>
  );

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 30 }}>
        <Pressable onPress={() => router.back()}>
          <Text className="mb-6 text-base text-[#705B52]">← Back to voice</Text>
        </Pressable>
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          BRAND MEMORY
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">Voice blueprint</Text>
        <Text className="mb-7 mt-3 leading-6 text-[#827970]">
          A clear reference for creating consistent, on-brand content.
        </Text>

        {loading ? (
          <ActivityIndicator size="large" color="#FF6B5F" />
        ) : error ? (
          <Text className="text-red-600">{error}</Text>
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
              className="mb-3 items-center rounded-full bg-[#FF6B5F] py-4"
            >
              <Text className="font-bold text-white">Edit brand voice</Text>
            </Pressable>

            <Pressable
              disabled={deleting}
              onPress={() => void deleteCurrentBrand()}
              accessibilityRole="button"
              accessibilityLabel="Delete current brand. Permanently delete this brand."
              className={`mb-6 items-center rounded-full border border-[#E0B4AE] bg-white py-4 ${
                deleting ? "opacity-60" : ""
              }`}
            >
              <Text className="font-bold text-[#B04438]">
                {deleting ? "Deleting brand..." : "Delete Current Brand"}
              </Text>
            </Pressable>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}
