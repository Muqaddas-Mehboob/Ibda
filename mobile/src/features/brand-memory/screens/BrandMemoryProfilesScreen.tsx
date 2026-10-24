import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
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

export function BrandMemoryProfilesScreen() {
  const router = useRouter();
  const { created } = useLocalSearchParams<{ created?: string }>();
  const [brands, setBrands] = useState<BrandMemoryProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

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

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingTop: 40, paddingBottom: 32 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#FF6B5F"
          />
        }
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          YOUR WORKSPACE
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">
          Brand Memory
        </Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#827970]">
          Saved brand voices keep your tone, audience, and writing guidelines
          consistent across every piece of content.
        </Text>

        <Pressable
          onPress={() => router.push("/brand-memory/create")}
          accessibilityRole="button"
          className="mb-7 min-h-14 flex-row items-center justify-center rounded-2xl bg-[#FF6B5F] px-5 py-4"
        >
          <Text className="mr-2 text-xl font-semibold text-white">+</Text>
          <Text className="font-bold text-white">Create New Brand Voice</Text>
        </Pressable>

        {created === "1" && (
          <View className="mb-6 rounded-2xl border border-[#BBD8C3] bg-[#EFF7F0] p-4">
            <Text className="font-semibold text-[#287D54]">
              Brand voice created successfully.
            </Text>
          </View>
        )}

        <Text className="mb-4 text-xl font-bold text-[#24221F]">
          Your brand voices
        </Text>

        {loading ? (
          <View className="items-center py-12">
            <ActivityIndicator color="#FF6B5F" size="large" />
            <Text className="mt-3 text-[#827970]">
              Loading your brand voices...
            </Text>
          </View>
        ) : error ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
            <Text className="font-semibold text-[#24221F]">
              Couldn&apos;t load brand voices
            </Text>
            <Text className="mt-2 leading-5 text-[#B04438]">{error}</Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-11 self-start justify-center rounded-xl bg-[#24221F] px-4 py-2"
            >
              <Text className="font-semibold text-white">Try again</Text>
            </Pressable>
          </View>
        ) : brands.length === 0 ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-6">
            <Text className="text-xl font-bold text-[#24221F]">
              No brand voices yet
            </Text>
            <Text className="mt-2 leading-6 text-[#827970]">
              Create a brand voice to give Ibda the details it needs to make
              content feel like you.
            </Text>
            <Pressable
              onPress={() => router.push("/brand-memory/create")}
              accessibilityRole="button"
              className="mt-5 min-h-12 self-start justify-center rounded-full bg-[#FF6B5F] px-5 py-3"
            >
              <Text className="font-bold text-white">
                + Create New Brand Voice
              </Text>
            </Pressable>
          </View>
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
                className="rounded-3xl border border-[#EAE4DC] bg-white p-5"
              >
                <View className="flex-row items-center">
                  <View
                    className={`mr-4 h-14 w-14 items-center justify-center rounded-2xl ${
                      index % 2 === 0 ? "bg-[#F8E3DF]" : "bg-[#EDE3F2]"
                    }`}
                  >
                    <Text className="text-2xl font-bold text-[#24221F]">
                      {(brand.name.trim()[0] || "B").toUpperCase()}
                    </Text>
                  </View>
                  <View className="flex-1">
                    <Text className="text-lg font-bold text-[#24221F]">
                      {brand.name}
                    </Text>
                    <Text className="mt-1 text-sm text-[#827970]">
                      {brand.industry || "Industry not specified"}
                    </Text>
                  </View>
                  <Text className="text-xl text-[#FF6B5F]">→</Text>
                </View>

                {brand.description ? (
                  <Text
                    numberOfLines={2}
                    className="mt-4 leading-5 text-[#827970]"
                  >
                    {brand.description}
                  </Text>
                ) : null}

                <View className="mt-4 gap-2 border-t border-[#EAE4DC] pt-4">
                  <Text className="text-sm text-[#51483F]">
                    <Text className="font-semibold">Tone: </Text>
                    {brand.voice?.tone || "Not set"}
                  </Text>
                  <Text className="text-sm text-[#51483F]">
                    <Text className="font-semibold">Audience: </Text>
                    {brand.voice?.target_audience || "Not set"}
                  </Text>
                  <Text className="text-sm text-[#51483F]">
                    <Text className="font-semibold">Language: </Text>
                    {brand.voice?.language || "Not set"}
                  </Text>
                  {!brand.voice && (
                    <Text className="text-sm font-medium text-[#B66A58]">
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
