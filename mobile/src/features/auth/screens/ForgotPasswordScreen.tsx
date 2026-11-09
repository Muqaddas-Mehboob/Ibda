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
        contentContainerClassName="flex-grow px-6 pb-12 pt-8"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false} contentContainerStyle={{ width: "100%", maxWidth: 520, alignSelf: "center" }}
      >
        <Pressable
          onPress={() => router.replace("/sign-in")}
          className="mb-8 flex-row items-center self-start"
        >
          <Text className="text-xl text-[#C24A3C]">←</Text>
          <Text className="ml-2 text-[15px] leading-[24px] font-medium text-[#716A64]" variant="button">
            Back to sign in
          </Text>
        </Pressable>

        <View className="mb-7 h-16 w-16 items-center justify-center rounded-2xl bg-[#EEE7F1]">
          <Text className="text-[30px] leading-[37px] tracking-[-0.6px] text-[#292724]">✉</Text>
        </View>

        <Text className="text-[30px] leading-[37px] tracking-[-0.6px] font-bold tracking-tight text-[#292724]" variant="metric">
          Forgot password?
        </Text>

        <Text className="mt-3 text-base leading-6 text-[#716A64]" variant="body">
          It happens. Enter the email address associated with your account and
          we'll send you a link to reset your password.
        </Text>

        <View className="mt-6">
          <Text className="mb-2 text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
            Email address
          </Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="you@company.com"
            placeholderTextColor="#716A64"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            accessibilityLabel="Email address"
            className="min-h-14 border border-[#E9E2DA] bg-[#F7F4EF] px-4 text-base text-[#292724] rounded-[18px]"
            returnKeyType="send"
            onSubmitEditing={handleResetPassword}
          />
        </View>

        {error ? (
          <Text accessibilityRole="alert" className="mt-4 text-[15px] leading-[23px] text-[#C24A3C]" variant="body">
            {error}
          </Text>
        ) : null}

        {successMessage ? (
          <Text className="mt-4 text-[15px] leading-[23px] text-ibda-green" variant="body">
            {successMessage}
          </Text>
        ) : null}

        <Pressable
          onPress={handleResetPassword}
          accessibilityRole="button"
          disabled={loading}
          className="mt-6 min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] active:opacity-80"
        >
          <Text className="text-base leading-[24px] font-bold text-white" variant="button">
            {loading ? "Sending..." : "Send reset link"}
          </Text>
          <Text className="ml-2 text-lg text-white" variant="button">→</Text>
        </Pressable>

        <View className="mt-6 rounded-2xl bg-[#F1E9DF] p-4">
          <Text className="text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
            Need help?
          </Text>
          <Text className="mt-1 text-[15px] leading-[23px] text-[#716A64]" variant="body">
            If you no longer have access to your email, contact the Ibda support
            team for assistance.
          </Text>
        </View>

        <View className="mt-auto flex-row items-center justify-center pt-10">
          <Text className="text-[15px] leading-[24px] text-[#716A64]" variant="body">
            Remember your password?
          </Text>
          <Pressable onPress={() => router.replace("/sign-in")} className="ml-1 p-1">
            <Text className="text-[15px] leading-[24px] font-semibold text-[#C24A3C]" variant="button">
              Sign in
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}