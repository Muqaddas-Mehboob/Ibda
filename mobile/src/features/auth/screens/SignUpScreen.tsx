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

export function SignUpScreen() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  function handleSignUp() {
    setError("");

    if (!name.trim() || !email.trim() || !password || !confirmPassword) {
      setError("Please complete all fields.");
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Please enter a valid email address.");
      return;
    }

    if (password.length < 8) {
      setError("Your password must contain at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Your passwords do not match.");
      return;
    }

    setError("Account creation is not connected to Supabase yet.");
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
          onPress={() => router.replace("/")}
          className="mb-8 flex-row items-center self-start"
        >
          <Text className="text-xl text-ibda-coral">←</Text>
          <Text className="ml-2 text-sm font-medium text-ibda-brown">
            Back to home
          </Text>
        </Pressable>

        <View className="mb-8 flex-row items-center">
          <View className="mr-3 h-10 w-10 items-center justify-center bg-[#281D2C]">
            <Text className="text-2xl text-white">✦</Text>
          </View>
          <Text className="text-2xl font-extrabold text-ibda-charcoal">
            Ibda<Text className="text-ibda-coral">.</Text>
          </Text>
        </View>

        <Text className="text-3xl font-bold tracking-tight text-ibda-charcoal">
          Create your account
        </Text>
        <Text className="mt-2 text-base leading-6 text-ibda-brown">
          Start building a consistent social presence with your AI-powered
          creative studio.
        </Text>

        <View className="mt-8">
          <Text className="mb-2 text-sm font-semibold text-ibda-charcoal">
            Full name
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Your full name"
            placeholderTextColor="#947D76"
            autoCapitalize="words"
            autoComplete="name"
            accessibilityLabel="Full name"
            className="min-h-14 border border-ibda-border bg-white px-4 text-base text-ibda-charcoal"
          />
        </View>

        <View className="mt-5">
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
          />
        </View>

        <View className="mt-5">
          <Text className="mb-2 text-sm font-semibold text-ibda-charcoal">
            Password
          </Text>
          <View className="min-h-14 flex-row items-center border border-ibda-border bg-white px-4">
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="At least 8 characters"
              placeholderTextColor="#947D76"
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              autoComplete="new-password"
              accessibilityLabel="Password"
              className="flex-1 py-3 text-base text-ibda-charcoal"
            />
            <Pressable onPress={() => setShowPassword(!showPassword)}>
              <Text className="ml-2 text-sm text-ibda-brown">
                {showPassword ? "Hide" : "Show"}
              </Text>
            </Pressable>
          </View>
        </View>

        <View className="mt-5">
          <Text className="mb-2 text-sm font-semibold text-ibda-charcoal">
            Confirm password
          </Text>
          <TextInput
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            placeholder="Enter your password again"
            placeholderTextColor="#947D76"
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            autoComplete="new-password"
            accessibilityLabel="Confirm password"
            className="min-h-14 border border-ibda-border bg-white px-4 text-base text-ibda-charcoal"
          />
        </View>

        {error ? (
          <Text accessibilityRole="alert" className="mt-4 text-sm leading-5 text-ibda-coral">
            {error}
          </Text>
        ) : null}

        <Pressable
          onPress={handleSignUp}
          accessibilityRole="button"
          className="mt-7 min-h-14 flex-row items-center justify-center rounded-full bg-ibda-coral active:opacity-80"
        >
          <Text className="text-base font-bold text-white">Create account</Text>
          <Text className="ml-2 text-lg text-white">→</Text>
        </Pressable>

        <View className="mt-7 flex-row flex-wrap items-center justify-center">
          <Text className="text-sm text-ibda-brown">
            Already have an account?
          </Text>
          <Pressable onPress={() => router.replace("/sign-in")} className="ml-1 p-1">
            <Text className="text-sm font-semibold text-ibda-coral">
              Sign in
            </Text>
          </Pressable>
        </View>

        <Text className="mt-auto pt-8 text-center text-xs leading-5 text-ibda-muted">
          By creating an account, you agree to our Terms of Service and Privacy
          Policy.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}