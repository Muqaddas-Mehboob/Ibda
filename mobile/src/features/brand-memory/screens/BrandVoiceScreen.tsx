
import { useCallback, useEffect, useState } from "react";
import {
    ActivityIndicator,
    Alert,
    Pressable,
    ScrollView,
    Text,
    TextInput,
    View,
} from "react-native";
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
            <Text className="mb-2 text-sm font-semibold text-[#24221F]">{label}</Text>
            <TextInput
                value={voice[key]}
                onChangeText={(value) => update(key, value)}
                placeholder={placeholder}
                placeholderTextColor="#A39A91"
                multiline={multiline}
                textAlignVertical={multiline ? "top" : "center"}
                className={`rounded-2xl border border-[#EAE4DC] bg-white px-4 py-4 text-[#24221F] ${multiline ? "min-h-28" : ""
                    }`}
            />
        </View>
    );

    return (
        <View className="flex-1 bg-[#FCF9F4]">
            <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 30, paddingBottom: 40 }}>
                <Pressable onPress={() => router.back()}>
                    <Text className="mb-6 text-base text-[#705B52]">← Back to profiles</Text>
                </Pressable>

                <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
                    VOICE & MEMORY
                </Text>
                <Text className="text-4xl font-bold text-[#24221F]">Brand voice</Text>
                <Text className="mb-7 mt-3 leading-6 text-[#827970]">
                    Teach Ibda how your brand sounds, who it speaks to and which rules
                    every piece of content should follow.
                </Text>

                {loading ? (
                    <ActivityIndicator size="large" color="#FF6B5F" />
                ) : (
                    <>
                        {error ? (
                            <Text className="mb-4 text-sm text-red-600">{error}</Text>
                        ) : null}

                        <Text className="mb-3 text-lg font-bold text-[#24221F]">
                            Choose a tone
                        </Text>
                        <View className="mb-6 flex-row flex-wrap gap-2">
                            {tones.map((tone) => (
                                <Pressable
                                    key={tone}
                                    onPress={() => update("tone", tone)}
                                    className={`rounded-full border px-4 py-3 ${voice.tone === tone
                                            ? "border-[#FF6B5F] bg-[#F8E3DF]"
                                            : "border-[#EAE4DC] bg-white"
                                        }`}
                                >
                                    <Text className="font-medium text-[#24221F]">{tone}</Text>
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
                            className="items-center rounded-full bg-[#FF6B5F] py-4"
                        >
                            <Text className="font-bold text-white">
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
                            className="mt-3 items-center rounded-full border border-[#EAE4DC] bg-white py-4"
                        >
                            <Text className="font-semibold text-[#24221F]">
                                View voice blueprint →
                            </Text>
                        </Pressable>
                    </>
                )}
            </ScrollView>
        </View>
    );
}
