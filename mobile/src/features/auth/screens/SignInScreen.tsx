import { signIn } from "../services/auth.service";
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

export function SignInScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const [error, setError] = useState("");

  async function handleSignIn() {
    setError("");

    if (!email.trim() || !password) {
      setError("Please enter your email address and password.");
      return;
    }

    setLoading(true);

    try {
      const result = await signIn(email, password);

      if (result.error) {
        setError(result.error);
        return;
      }

      router.replace("/onboarding");
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
        contentContainerClassName="flex-grow px-[23px] pb-8 pt-5"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View className="mb-10 flex-row items-center justify-between">
          <View className="flex-row items-center">
            <View className="mr-2.5 h-10 w-10 items-center justify-center bg-[#281D2C]">
              <Text className="text-2xl text-white">✦</Text>
            </View>

            <Text className="text-[22px] font-extrabold tracking-tight text-ibda-charcoal">
              Ibda
              <Text className="text-ibda-coral">.</Text>
            </Text>
          </View>

          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/sign-up")}
            className="flex-row items-center py-2"
          >
            <Text className="text-sm font-medium text-ibda-coral">
              Sign up →
            </Text>
          </Pressable>
        </View>

        {/* Intro */}
        <Text className="text-[27px] font-bold tracking-tight text-ibda-charcoal">
          Welcome back
        </Text>

        <Text className="mt-1 text-[15px] leading-[22px] text-ibda-brown">
          Sign in to continue managing your social{"\n"}
          presence and brand voice.
        </Text>

        {/* Google button: UI only until OAuth is connected */}
        <Pressable
          accessibilityRole="button"
          onPress={() =>
            setError("Google sign-in will be available once authentication is connected.")
          }
          className="mt-9 min-h-[63px] flex-row items-center justify-center border border-[#EEE9E3] bg-white active:opacity-80"
        >
          <Text className="mr-3 text-[23px] font-bold text-[#4285F4]">G</Text>
          <Text className="text-base font-semibold text-ibda-charcoal">
            Continue with Google
          </Text>
        </Pressable>

        {/* Divider */}
        <View className="my-6 flex-row items-center">
          <View className="h-px flex-1 bg-ibda-border" />
          <Text className="mx-3 text-xs font-bold tracking-wide text-ibda-muted">
            OR CONTINUE WITH EMAIL
          </Text>
          <View className="h-px flex-1 bg-ibda-border" />
        </View>

        {/* Email */}
        <Text className="mb-1.5 text-sm font-semibold text-ibda-charcoal">
          Email Address
        </Text>

        <View className="min-h-[42px] flex-row items-center border border-[#F0EBE5] bg-white px-3 shadow-sm">
          <Text className="mr-3 text-lg text-ibda-muted">✉</Text>

          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="alex@company.com"
            placeholderTextColor="#947D76"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            accessibilityLabel="Email address"
            className="flex-1 py-2 text-sm text-ibda-charcoal"
            returnKeyType="next"
          />
        </View>

        {/* Password */}
        <View className="mb-1.5 mt-5 flex-row items-center justify-between">
          <Text className="text-sm font-semibold text-ibda-charcoal">
            Password
          </Text>

          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/forgot-password")}
            hitSlop={8}
          >
            <Text className="text-sm font-medium text-ibda-coral">
              Forgot password?
            </Text>
          </Pressable>
        </View>

        <View className="min-h-[42px] flex-row items-center border border-[#F0EBE5] bg-white px-3 shadow-sm">
          <Text className="mr-3 text-lg text-ibda-muted">♙</Text>

          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Enter your password"
            placeholderTextColor="#947D76"
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            autoComplete="current-password"
            accessibilityLabel="Password"
            className="flex-1 py-2 text-sm text-ibda-charcoal"
            returnKeyType="done"
            onSubmitEditing={handleSignIn}
          />

          <Pressable
            accessibilityRole="button"
            accessibilityLabel={
              showPassword ? "Hide password" : "Show password"
            }
            onPress={() => setShowPassword((current) => !current)}
            hitSlop={10}
          >
            <Text className="text-base text-ibda-muted">
              {showPassword ? "◉" : "◎"}
            </Text>
          </Pressable>
        </View>

        {/* Remember me */}
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: rememberMe }}
          onPress={() => setRememberMe((current) => !current)}
          className="mt-5 flex-row items-center self-start py-1"
        >
          <View
            className={`mr-3 h-6 w-6 items-center justify-center rounded-md ${rememberMe ? "bg-ibda-coral" : "bg-[#ECE8E3]"
              }`}
          >
            {rememberMe && (
              <Text className="text-sm font-bold text-white">✓</Text>
            )}
          </View>

          <Text className="text-sm text-ibda-brown">
            Remember me on this device
          </Text>
        </Pressable>

        {/* Validation / connection message */}
        {error ? (
          <Text
            accessibilityRole="alert"
            className="mt-3 text-sm leading-5 text-ibda-coral"
          >
            {error}
          </Text>
        ) : null}

        {/* Sign in button */}
        <Pressable
          accessibilityRole="button"
          onPress={handleSignIn}
          disabled={loading}
          className="mt-6 min-h-[64px] flex-row items-center justify-center rounded-full bg-ibda-coral shadow-lg shadow-[#F76B5B]/25 active:opacity-80"
        >
          <Text className="text-base font-bold text-white">
            {loading ? "Signing in..." : "Sign In"}
          </Text>
          <Text className="ml-2 text-xl text-white">→</Text>
        </Pressable>

        {/* AI co-pilot card */}
        <View className="mt-9 flex-row items-center rounded-[32px] border border-[#F2EDE7] bg-white px-4 py-5">
          <View className="mr-4 h-12 w-12 items-center justify-center rounded-full bg-ibda-lavender">
            <Text className="text-xl text-ibda-brown">✧</Text>
          </View>

          <View className="flex-1">
            <View className="flex-row flex-wrap items-center">
              <Text className="text-sm font-semibold text-ibda-charcoal">
                AI Content Co-pilot
              </Text>

              <View className="ml-2 rounded-full bg-ibda-lavender px-2 py-0.5">
                <Text className="text-[10px] font-bold text-ibda-charcoal">
                  V2.4
                </Text>
              </View>
            </View>

            <Text
              numberOfLines={2}
              className="mt-1 text-sm leading-5 text-ibda-brown"
            >
              Ready to craft posts in your custom brand voice.
            </Text>
          </View>
        </View>

        {/* Footer */}
        <View className="mt-auto items-center pt-9">
          <View className="flex-row flex-wrap items-center justify-center">
            <Text className="text-sm text-ibda-brown">
              Don't have an account?
            </Text>

            <Pressable
              onPress={() => router.push("/sign-up")}
              accessibilityRole="button"
              className="ml-2 py-1"
            >
              <Text className="text-sm font-semibold text-ibda-coral">
                Sign up free
              </Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}