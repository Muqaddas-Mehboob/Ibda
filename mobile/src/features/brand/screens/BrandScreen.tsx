import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable } from "../../../components/ui/StudioControls";
import { useCallback, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { getBrands, type Brand } from "../services/brand.service";
import { BottomNavigation } from "@/components/navigation/BottomNavigation";

const COLORS = {
    background: "#FAF8F4",
    surface: "#F4F0EA",
    text: "#25221F",
    muted: "#25221F",
    coral: "#C24A3C",
    border: "#E2D9CF",
    soft: "#F4F0EA",
};

export function BrandScreen() {
    const router = useRouter();

    const [brands, setBrands] = useState<Brand[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState("");

    const loadBrands = useCallback(async (isRefresh = false) => {
        if (isRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }

        setError("");

        try {
            const result = await getBrands();
            setBrands(result);
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "We couldn't load your brands. Please try again."
            );
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useFocusEffect(
        useCallback(() => {
            void loadBrands();
        }, [loadBrands])
    );

    const openBrandSetup = () => router.push("/brand-memory");

    return (
        <View className="flex-1" style={{ backgroundColor: COLORS.background }}>
            <Pressable
                onPress={() => router.replace("/dashboard")}
                accessibilityRole="button"
                accessibilityLabel="Back to dashboard"
                className="ml-6 mt-3 h-11 w-11 items-center justify-center rounded-full border"
                style={{
                    backgroundColor: COLORS.surface,
                    borderColor: COLORS.border,
                }}
            >
                <Text className="text-2xl" style={{ color: COLORS.text }}>
                    ←
                </Text>
            </Pressable>
            <ScrollView
                className="flex-1"
                contentContainerStyle={{ padding: 24, paddingTop: 16, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}
                refreshControl={
                    <RefreshControl
                        refreshing={refreshing}
                        onRefresh={() => void loadBrands(true)}
                        tintColor={COLORS.coral}
                    />
                }
                showsVerticalScrollIndicator={false}
            >
                <View className="mb-8 flex-row items-start justify-between">
                    <View className="mr-3 flex-1">
                        <Text
                            className="mb-2 text-[12px] font-bold uppercase tracking-[2px]"
                            style={{ color: "#25221F" }} variant="eyebrow" tone="olive"
                        >
                            YOUR WORKSPACE
                        </Text>

                        <Text
                            className="text-[22px] leading-[30px] tracking-[-0.4px] font-bold"
                            style={{ color: COLORS.text }} variant="page" tone="olive"
                        >
                            Your brands
                        </Text>

                        <Text
                            className="mt-2 text-[14px] leading-6"
                            style={{ color: COLORS.muted }} variant="body"
                        >
                            Keep every brand's identity, voice and content in one place.
                        </Text>
                    </View>

                    <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Add a brand"
                        onPress={openBrandSetup}
                        className="h-12 w-12 items-center justify-center rounded-2xl"
                        style={{ backgroundColor: COLORS.coral }}
                    >
                        <Text className="text-[22px] leading-[30px] tracking-[-0.3px] font-normal text-[#FAF8F4]" variant="button">+</Text>
                    </Pressable>
                </View>

                <View
                    className="mb-6 rounded-3xl p-6"
                    style={{ backgroundColor: "#F4F0EA" }}
                >
                    <Text
                        className="text-[14px] leading-[22px] font-bold"
                        style={{ color: "#25221F" }} variant="cardTitle"
                    >
                        Your brand workspace
                    </Text>

                    <Text className="mt-2 text-[14px] leading-[23px]" style={{ color: "#25221F" }} variant="body">
                        Your saved brands are loaded from your Ibda account. Add another
                        brand whenever you're ready to grow.
                    </Text>

                    <View className="mt-4 flex-row items-center">
                        <View
                            className="mr-2 h-2 w-2 rounded-full"
                            style={{ backgroundColor: "#25221F" }}
                        />
                        <Text className="text-[14px] leading-[22px]" style={{ color: "#25221F" }} variant="body">
                            {brands.length} {brands.length === 1 ? "brand" : "brands"} saved
                        </Text>
                    </View>
                </View>

                {loading ? (
                    <View className="items-center py-16">
                        <ActivityIndicator size="large" color={COLORS.coral} />
                        <Text className="mt-4 text-[14px] leading-[22px]" style={{ color: COLORS.muted }} variant="body">
                            Loading your brands...
                        </Text>
                    </View>
                ) : error ? (
                    <View
                        className="rounded-3xl border p-6"
                        style={{ backgroundColor: COLORS.surface, borderColor: COLORS.border }}
                    >
                        <Text className="text-[14px] leading-[22px] font-bold" style={{ color: COLORS.text }} variant="cardTitle">
                            Couldn't load your brands
                        </Text>
                        <Text className="mt-2 text-[14px] leading-[23px]" style={{ color: COLORS.muted }} variant="body">
                            {error}
                        </Text>
                        <Pressable
                            onPress={() => void loadBrands()}
                            className="mt-5 self-start rounded-2xl px-5 py-3"
                            style={{ backgroundColor: COLORS.text }}
                        >
                            <Text className="font-semibold text-[#FAF8F4] text-[14px] leading-[22px]" variant="button">Try again</Text>
                        </Pressable>
                    </View>
                ) : brands.length === 0 ? (
                    <View
                        className="items-center rounded-3xl border px-6 py-10"
                        style={{ backgroundColor: COLORS.surface, borderColor: COLORS.border }}
                    >
                        <View
                            className="mb-5 h-16 w-16 items-center justify-center rounded-2xl"
                            style={{ backgroundColor: COLORS.soft }}
                        >
                            <Text className="text-3xl" style={{ color: "#25221F" }}>
                                ◇
                            </Text>
                        </View>

                        <Text
                            className="text-center text-[14px] leading-[23px] tracking-[-0.3px] font-bold"
                            style={{ color: COLORS.text }} variant="section"
                        >
                            Your first brand starts here
                        </Text>

                        <Text
                            className="mt-2 text-center text-[14px] leading-[23px]"
                            style={{ color: COLORS.muted }} variant="body"
                        >
                            Add a brand to start organizing its identity, content and voice.
                        </Text>

                        <Pressable
                            onPress={openBrandSetup}
                            className="mt-6 rounded-2xl px-6 py-4"
                            style={{ backgroundColor: COLORS.coral }}
                        >
                            <Text className="font-bold text-[#FAF8F4] text-[14px] leading-[22px]" variant="button">Create your first brand</Text>
                        </Pressable>
                    </View>
                ) : (
                    <View className="gap-4">
                        <View className="mb-1 flex-row items-center justify-between">
                            <Text className="text-[14px] leading-[23px] tracking-[-0.3px] font-bold" style={{ color: COLORS.text }} variant="section">
                                All brands
                            </Text>
                            <Text className="text-[14px] leading-[22px]" style={{ color: COLORS.muted }} variant="body">
                                {brands.length} total
                            </Text>
                        </View>

                        {brands.map((brand, index) => (
                            <View
                                key={brand.id}
                                className="rounded-3xl border p-6"
                                style={{
                                    backgroundColor: COLORS.surface,
                                    borderColor: "rgba(155,174,159,0.3)",
                                }}
                            >
                                <View className="flex-row items-start">
                                    <View
                                        className="mr-4 h-14 w-14 items-center justify-center rounded-2xl"
                                        style={{
                                            backgroundColor: index % 2 === 0 ? "rgba(155,174,159,0.2)" : "rgba(155,174,159,0.2)",
                                        }}
                                    >
                                        <Text
                                            className="text-2xl font-bold"
                                            style={{ color: "#4A523E" }}
                                        >
                                            {(brand.name.trim()[0] || "B").toUpperCase()}
                                        </Text>
                                    </View>

                                    <View className="flex-1">
                                        <Text
                                            className="text-[14px] leading-[22px] font-bold"
                                            style={{ color: "#4A523E" }} variant="cardTitle"
                                        >
                                            {brand.name}
                                        </Text>

                                        <Text className="mt-1 text-[14px] leading-[22px]" style={{ color: COLORS.muted }} variant="body">
                                            {brand.industry || "Industry not specified"}
                                        </Text>
                                    </View>

                                    <View
                                        className="rounded-full px-3 py-1"
                                        style={{ backgroundColor: "rgba(155,174,159,0.2)" }}
                                    >
                                        <Text className="text-[12px] font-semibold" style={{ color: "#4A523E" }} variant="caption">
                                            Saved
                                        </Text>
                                    </View>
                                </View>

                                {brand.description ? (
                                    <Text
                                        numberOfLines={3}
                                        className="mt-4 text-[14px] leading-[23px]"
                                        style={{ color: COLORS.muted }} variant="body"
                                    >
                                        {brand.description}
                                    </Text>
                                ) : null}

                                {brand.website ? (
                                    <Text
                                        numberOfLines={1}
                                        className="mt-3 text-[14px] leading-[22px]"
                                        style={{ color: "#25221F" }} variant="body"
                                    >
                                        {brand.website}
                                    </Text>
                                ) : null}

                                <View
                                    className="mt-5 border-t pt-4"
                                    style={{ borderColor: COLORS.border }}
                                >
                                    <Text className="text-[12px]" style={{ color: COLORS.muted }} variant="caption">
                                        Created{" "}
                                        {Number.isNaN(Date.parse(brand.created_at))
                                            ? "in your workspace"
                                            : new Date(brand.created_at).toLocaleDateString()}
                                    </Text>
                                </View>
                            </View>
                        ))}

                        <Pressable
                            onPress={openBrandSetup}
                            className="items-center rounded-2xl border border-dashed py-5"
                            style={{ borderColor: COLORS.coral }}
                        >
                            <Text className="font-bold text-[14px] leading-[22px]" style={{ color: "#25221F" }} variant="button">
                                + Add another brand
                            </Text>
                        </Pressable>
                    </View>
                )}
            </ScrollView>
            <BottomNavigation />
        </View>
    );
}
