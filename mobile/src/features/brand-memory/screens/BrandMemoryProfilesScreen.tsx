import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, RefreshControl, ScrollView, View } from "react-native";
import {
  useFocusEffect,
  useLocalSearchParams,
  useRouter,
} from "expo-router";
import {
  getMemoryBrands,
  type BrandMemoryProfile,
} from "../services/brandMemory.service";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { deleteAllBrands } from "../../brand/services/brand.service";
import { confirmAsync } from "../../../lib/confirm";

export function BrandMemoryProfilesScreen() {
  const router = useRouter();
  const { created, deleted, deletedBrand } = useLocalSearchParams<{
    created?: string;
    deleted?: string;
    deletedBrand?: string;
  }>();
  const [brands, setBrands] = useState<BrandMemoryProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    setError("");
    try {
      setBrands(await getMemoryBrands());
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load your brand voices."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );
  const deleteAll = async () => {
          if (deleting) return;
  
          const confirmed = await confirmAsync(
              "Delete all brands?",
              "Every brand in your account and all of their brand-specific data — brand voices, content, approvals, schedules and notifications — will be permanently deleted. This can't be undone.",
              {
                  confirmText: "Delete all brands",
                  destructive: true,
              }
          );
          if (!confirmed) return;
  
          setDeleting(true);
          setError("");
          try {
              await deleteAllBrands();
              Alert.alert(
                  "Brands deleted",
                  "All of your brands and their brand-specific data were permanently deleted."
              );
              router.dismissTo({
                  pathname: "/brand-memory",
                  params: { deleted: "all" },
              });
          } catch (e) {
              Alert.alert(
                  "Couldn’t delete brands",
                  e instanceof Error
                      ? e.message
                      : "We couldn't delete your brands. Nothing was removed, so you can try again."
              );
          } finally {
              setDeleting(false);
          }
      };

  return (
    
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 40, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#C24A3C"
          />
        }
        keyboardShouldPersistTaps="handled"
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
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#4A523E]" variant="eyebrow" tone="olive">
          YOUR WORKSPACE
        </Text>
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="olive">
          Brand Memory
        </Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          Saved brand voices keep your tone, audience, and writing guidelines
          consistent across every piece of content.
        </Text>

        <Pressable
          onPress={() => router.push("/brand-memory/create")}
          accessibilityRole="button"
          className="mb-7 min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-4"
        >
          <Text className="mr-2 text-xl font-semibold text-white">+</Text>
          <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">Create New Brand Voice</Text>
        </Pressable>

        {created === "1" && (
          <View className="mb-6 rounded-2xl border border-[#BBD8C3] bg-[#EFF7F0] p-4">
            <Text className="font-semibold text-[#287D54] text-[15px] leading-[24px]" variant="label">
              Brand voice created successfully.
            </Text>
          </View>
        )}

        {deleted && (
          <View className="mb-6 rounded-2xl border border-[#BBD8C3] bg-[#EFF7F0] p-4">
            <Text className="font-semibold text-[#287D54] text-[15px] leading-[24px]" variant="label">
              {deleted === "all"
                ? "All your brands were deleted successfully."
                : deletedBrand
                  ? `"${deletedBrand}" was deleted successfully.`
                  : "Brand deleted successfully."}
            </Text>
          </View>
        )}

         <Pressable
                            disabled={deleting}
                            onPress={() => void deleteAll()}
                            accessibilityRole="button"
                            accessibilityLabel="Delete all brands. Permanently delete every brand in your account."
                            className={`mt-8 items-center rounded-2xl border border-[#E0B4AE] bg-white py-4 ${
                                deleting ? "opacity-60" : ""
                            }`}
                        >
                            <Text className="font-bold text-[#B04438] text-[15px] leading-[24px]" variant="button">
                                {deleting ? "Deleting all brands..." : "Delete All Brands"}
                            </Text>
                        </Pressable>

        <Text className="mb-4 text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
          Your brand voices
        </Text>

        {loading ? (
          <View className="items-center py-12">
            <ActivityIndicator color="#C24A3C" size="large" />
            <Text className="mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Loading your brand voices...
            </Text>
          </View>
        ) : error ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn&apos;t load brand voices
            </Text>
            <Text className="mt-2 text-[#B04438] text-[15px] leading-[24px]" variant="body">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-[54px] self-start justify-center rounded-[18px] bg-[#292724] px-4 py-2"
            >
              <Text className="font-semibold text-white text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </StudioCard>
        ) : brands.length === 0 ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#292724]" variant="section">
              No brand voices yet
            </Text>
            <Text className="mt-2 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Create a brand voice to give Ibda the details it needs to make
              content feel like you.
            </Text>
            <Pressable
              onPress={() => router.push("/brand-memory/create")}
              accessibilityRole="button"
              className="mt-5 min-h-[54px] self-start justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-5 py-3"
            >
              <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                + Create New Brand Voice
              </Text>
            </Pressable>
          </StudioCard>
        ) : (
          <View className="gap-4">
            {brands.map((brand, index) => (
              <Pressable
                key={brand.id}
                onPress={() =>
                  router.push({
                    pathname: "/brand-memory/[brandId]",
                    params: { brandId: brand.id },
                  })
                }
                accessibilityRole="button"
                accessibilityLabel={`Edit ${brand.name} brand voice`}
                className="rounded-3xl border border-[#E9E2DA] border-l-[3px] border-l-[#7F9C81] bg-white shadow-sm shadow-[#292724]/5 active:bg-[#F1E9DF] p-6"
              >
                <View className="flex-row items-center">
                  <View
                    className={`mr-4 h-14 w-14 items-center justify-center rounded-2xl ${
                      index % 2 === 0 ? "bg-[#E5EDE3]" : "bg-[#E5EDE3]"
                    }`}
                  >
                    <Text className="text-2xl font-bold text-[#4A523E]">
                      {(brand.name.trim()[0] || "B").toUpperCase()}
                    </Text>
                  </View>
                  <View className="flex-1">
                    <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                      {brand.name}
                    </Text>
                    <Text className="mt-1 text-[15px] leading-[24px] text-[#716A64]" variant="body">
                      {brand.industry || "Industry not specified"}
                    </Text>
                  </View>
                  <Text className="text-xl text-[#C24A3C]">→</Text>
                </View>

                {brand.description ? (
                  <Text
                    numberOfLines={2}
                    className="mt-4 text-[#716A64] text-[15px] leading-[24px]" variant="body"
                  >
                    {brand.description}
                  </Text>
                ) : null}

                <View className="mt-4 gap-2 border-t border-[#E9E2DA] pt-4">
                  <Text className="text-[15px] leading-[24px] text-[#716A64]" variant="body">
                    <Text className="font-semibold text-[15px] leading-[24px]" variant="label">Tone: </Text>
                    {brand.voice?.tone || "Not set"}
                  </Text>
                  <Text className="text-[15px] leading-[24px] text-[#716A64]" variant="body">
                    <Text className="font-semibold text-[15px] leading-[24px]" variant="label">Audience: </Text>
                    {brand.voice?.target_audience || "Not set"}
                  </Text>
                  <Text className="text-[15px] leading-[24px] text-[#716A64]" variant="body">
                    <Text className="font-semibold text-[15px] leading-[24px]" variant="label">Language: </Text>
                    {brand.voice?.language || "Not set"}
                  </Text>
                  {!brand.voice && (
                    <Text className="text-[15px] leading-[24px] font-medium text-[#B66A58]" variant="label">
                      Voice profile not configured — tap to set it up.
                    </Text>
                  )}
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
