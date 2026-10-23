import { router } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  Text,
  TextInput,
  View,
} from "react-native";
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
      className="flex-1 bg-ibda-background"
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <StatusBar barStyle="dark-content" />

      <ScrollView
        className="flex-1"
        contentContainerClassName="flex-grow px-6 pb-8 pt-5"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Pressable
          onPress={() => router.replace("/sign-in")}
          className="mb-10 flex-row items-center self-start"
        >
          <Text className="text-xl text-ibda-coral">←</Text>
          <Text className="ml-2 text-sm font-medium text-ibda-brown">
            Back to sign in
          </Text>
        </Pressable>

        <View className="mb-9 h-16 w-16 items-center justify-center rounded-2xl bg-ibda-lavender">
          <Text className="text-3xl text-ibda-charcoal">✉</Text>
        </View>

        <Text className="text-3xl font-bold tracking-tight text-ibda-charcoal">
          Forgot password?
        </Text>

        <Text className="mt-3 text-base leading-6 text-ibda-brown">
          It happens. Enter the email address associated with your account and
          we'll send you a link to reset your password.
        </Text>

        <View className="mt-9">
          <Text className="mb-2 text-sm font-semibold text-ibda-charcoal">
            Email address
          </Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="you@company.com"
            placeholderTextColor="#947D76"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            accessibilityLabel="Email address"
            className="min-h-14 border border-ibda-border bg-white px-4 text-base text-ibda-charcoal"
            returnKeyType="send"
            onSubmitEditing={handleResetPassword}
          />
        </View>

        {error ? (
          <Text accessibilityRole="alert" className="mt-4 text-sm leading-5 text-ibda-coral">
            {error}
          </Text>
        ) : null}

        {successMessage ? (
          <Text className="mt-4 text-sm leading-5 text-ibda-green">
            {successMessage}
          </Text>
        ) : null}

        <Pressable
          onPress={handleResetPassword}
          accessibilityRole="button"
          disabled={loading}
          className="mt-6 min-h-14 flex-row items-center justify-center rounded-full bg-ibda-coral active:opacity-80"
        >
          <Text className="text-base font-bold text-white">
            {loading ? "Sending..." : "Send reset link"}
          </Text>
          <Text className="ml-2 text-lg text-white">→</Text>
        </Pressable>

        <View className="mt-8 rounded-2xl bg-ibda-surface p-4">
          <Text className="text-sm font-semibold text-ibda-charcoal">
            Need help?
          </Text>
          <Text className="mt-1 text-sm leading-5 text-ibda-brown">
            If you no longer have access to your email, contact the Ibda support
            team for assistance.
          </Text>
        </View>

        <View className="mt-auto flex-row items-center justify-center pt-10">
          <Text className="text-sm text-ibda-brown">
            Remember your password?
          </Text>
          <Pressable onPress={() => router.replace("/sign-in")} className="ml-1 p-1">
            <Text className="text-sm font-semibold text-ibda-coral">
              Sign in
            </Text>
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}