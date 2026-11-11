import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";
import { router } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StatusBar, View } from "react-native";
import { resetPassword } from "../services/auth.service";

export function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  async function handleResetPassword() {
    setError("");
    setSuccessMessage("");

    if (!email.trim()) {
      setError("Please enter your email address.");
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Please enter a valid email address.");
      return;
    }

    setLoading(true);

    try {
      const result = await resetPassword(email);

      if (result.error) {
        setError(result.error);
        return;
      }

      setSuccessMessage(
        "If an account exists for this email, password reset instructions will be sent."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-[#FAF8F4]"
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <StatusBar barStyle="dark-content" />

      <ScrollView
        className="flex-1"
        contentContainerClassName="flex-grow px-6 pb-12 pt-5"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false} contentContainerStyle={{ width: "100%", maxWidth: 520, alignSelf: "center" }}
      >
        <Pressable
          onPress={() => router.replace("/sign-in")}
          className="mb-8 flex-row items-center self-start"
        >
          <Text className="text-xl text-[#C24A3C]">←</Text>
          <Text className="ml-2 text-[14px] leading-[22px] font-medium text-[#25221F]" variant="button">
            Back to sign in
          </Text>
        </Pressable>

        <View className="mb-7 h-16 w-16 items-center justify-center rounded-2xl bg-[#F4F0EA]">
          <Text className="text-[22px] leading-[30px] tracking-[-0.3px] text-[#25221F]">✉</Text>
        </View>

        <Text className="text-[22px] leading-[30px] tracking-[-0.3px] font-bold tracking-tight text-[#25221F]" variant="metric">
          Forgot password?
        </Text>

        <Text className="mt-3 text-[14px] leading-6 text-[#25221F]" variant="body">
          It happens. Enter the email address associated with your account and
          we'll send you a link to reset your password.
        </Text>

        <View className="mt-6">
          <Text className="mb-2 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
            Email address
          </Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="you@company.com"
            placeholderTextColor="#25221F"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            accessibilityLabel="Email address"
            className="min-h-14 border border-[#E2D9CF] bg-[#F4F0EA] px-4 text-[14px] text-[#25221F] rounded-[18px]"
            returnKeyType="send"
            onSubmitEditing={handleResetPassword}
          />
        </View>

        {error ? (
          <Text accessibilityRole="alert" className="mt-4 text-[14px] leading-[23px] text-[#C24A3C]" variant="body">
            {error}
          </Text>
        ) : null}

        {successMessage ? (
          <Text className="mt-4 text-[14px] leading-[23px] text-ibda-green" variant="body">
            {successMessage}
          </Text>
        ) : null}

        <Pressable
          onPress={handleResetPassword}
          accessibilityRole="button"
          disabled={loading}
          className="mt-6 min-h-[48px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] active:opacity-80"
        >
          <Text className="text-[14px] leading-[22px] font-bold text-[#FAF8F4]" variant="button">
            {loading ? "Sending..." : "Send reset link"}
          </Text>
          <Text className="ml-2 text-lg text-[#FAF8F4]" variant="button">→</Text>
        </Pressable>

        <View className="mt-6 rounded-2xl bg-[#F4F0EA] p-4">
          <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
            Need help?
          </Text>
          <Text className="mt-1 text-[14px] leading-[23px] text-[#25221F]" variant="body">
            If you no longer have access to your email, contact the Ibda support
            team for assistance.
          </Text>
        </View>

        <View className="mt-auto flex-row items-center justify-center pt-10">
          <Text className="text-[14px] leading-[22px] text-[#25221F]" variant="body">
            Remember your password?
          </Text>
          <Pressable onPress={() => router.replace("/sign-in")} className="ml-1 p-1">
            <Text className="text-[14px] leading-[22px] font-semibold text-[#C24A3C]" variant="button">
              Sign in
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}