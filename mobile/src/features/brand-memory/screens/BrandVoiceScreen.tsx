import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";

import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
    getBrandVoice,
    saveBrandVoice,
    type BrandVoice,
} from "../services/brandMemory.service";

const emptyVoice = {
    tone: "Friendly",
    target_audience: "",
    language: "English",
    writing_guidelines: "",
    example_content: "",
};

const tones = ["Friendly", "Professional", "Playful", "Bold", "Minimal", "Inspirational"];

export function BrandVoiceScreen() {
    const { brandId } = useLocalSearchParams<{ brandId: string }>();
    const router = useRouter();
    const [voice, setVoice] = useState(emptyVoice);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const update = (key: keyof typeof emptyVoice, value: string) =>
        setVoice((current) => ({ ...current, [key]: value }));

    const load = useCallback(async () => {
        if (!brandId) {
            setError("A brand must be selected first.");
            setLoading(false);
            return;
        }
        try {
            const result: BrandVoice = await getBrandVoice(brandId);
            setVoice({
                tone: result.tone || "Friendly",
                target_audience: result.target_audience || "",
                language: result.language || "English",
                writing_guidelines: result.writing_guidelines || "",
                example_content: result.example_content || "",
            });
        } catch (e) {
            setError(e instanceof Error ? e.message : "Unable to load brand voice.");
        } finally {
            setLoading(false);
        }
    }, [brandId]);

    // Load once when this brand's editor opens.
    useEffect(() => {
        void load();
    }, [load]);

    const save = async () => {
        if (!brandId) return;
        setSaving(true);
        setError("");
        try {
            await saveBrandVoice(brandId, voice);
            Alert.alert("Saved", "Your brand voice has been updated.");
        } catch (e) {
            setError(e instanceof Error ? e.message : "Unable to save brand voice.");
        } finally {
            setSaving(false);
        }
    };

    

    const field = (
        label: string,
        key: keyof typeof emptyVoice,
        placeholder: string,
        multiline = false,
    ) => (
        <View className="mb-5" key={key}>
            <Text className="mb-2 text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">{label}</Text>
            <TextInput
                value={voice[key]}
                onChangeText={(value) => update(key, value)}
                placeholder={placeholder}
                placeholderTextColor="#716A64"
                multiline={multiline}
                textAlignVertical={multiline ? "top" : "center"}
                className={`rounded-[18px] border border-[#E9E2DA] bg-[#F7F4EF] px-4 py-4 text-[#292724] ${multiline ? "min-h-28 rounded-[18px]" : " rounded-[18px]"
                    }`}
            />
        </View>
    );

    return (
        <View className="flex-1 bg-[#FAF8F4]">
            <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 36, paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center" }}>
                <Pressable onPress={() => router.back()}>
                    <Text className="mb-6 text-base leading-[24px] text-[#716A64]" variant="button">← Back to profiles</Text>
                </Pressable>

                <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#4A523E]" variant="eyebrow" tone="olive">
                    VOICE & MEMORY
                </Text>
                <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="olive">Brand voice</Text>
                <Text className="mb-7 mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">
                    Teach Ibda how your brand sounds, who it speaks to and which rules
                    every piece of content should follow.
                </Text>

                {loading ? (
                    <ActivityIndicator size="large" color="#C24A3C" />
                ) : (
                    <>
                        {error ? (
                            <Text className="mb-4 text-[15px] leading-[24px] text-red-600" variant="body">{error}</Text>
                        ) : null}

                        <Text className="mb-3 text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                            Choose a tone
                        </Text>
                        <View className="mb-6 flex-row flex-wrap gap-2">
                            {tones.map((tone) => (
                                <Pressable
                                    key={tone}
                                    onPress={() => update("tone", tone)}
                                    className={`rounded-2xl border px-4 py-3 ${voice.tone === tone
                                            ? "border-[#7F9C81] bg-[#E5EDE3]"
                                            : "border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
                                        }`}
                                >
                                    <Text className="font-medium text-[#292724] text-[15px] leading-[24px]" variant="button">{tone}</Text>
                                </Pressable>
                            ))}
                        </View>

                        {field("Target audience", "target_audience", "Who are you speaking to?", true)}
                        {field("Content language", "language", "e.g. English, Urdu")}
                        {field("Writing guidelines", "writing_guidelines", "Words to use or avoid, style rules, formatting...", true)}
                        {field("Example content", "example_content", "Paste an example that sounds like your brand...", true)}

                        <Pressable
                            disabled={saving}
                            onPress={() => void save()}
                            className="items-center rounded-2xl bg-[#C24A3C] active:bg-[#A63F32] py-4"
                        >
                            <Text className="font-bold text-white text-[15px] leading-[24px]" variant="button">
                                {saving ? "Saving..." : "Save brand voice"}
                            </Text>
                        </Pressable>

                        <Pressable
                            onPress={() =>
                                router.push({
                                    pathname: "/brand-memory/blueprint/[brandId]",
                                    params: { brandId },
                                })
                            }
                            className="mt-3 items-center rounded-2xl border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] py-4"
                        >
                            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="button">
                                View voice blueprint →
                            </Text>
                        </Pressable>
                    </>
                )}
            </ScrollView>
        </View>
    );
}
