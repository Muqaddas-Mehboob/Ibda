import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioInputFrame, StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";
import { IbdaLogo } from "../../../components/brand/IbdaLogo";
import { signInWithGoogle } from "../services/google-auth.service";
import { signIn } from "../services/auth.service";
import { AUTHENTICATED_ROUTE } from "../utils/auth-redirect";
import { router } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StatusBar, View, Alert } from "react-native";

export function SignInScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleGoogleSignIn() {
    setError("");
    setGoogleLoading(true);

    try {
      const authError = await signInWithGoogle();

      if (authError) {
        setError(authError);

        if (Platform.OS !== "web") {
          Alert.alert("Google sign-in failed", authError);
        }
      }
      // AuthProvider/AuthGate handles navigation after a session is created.
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Unable to sign in with Google. Please try again.";

      setError(message);

      if (Platform.OS !== "web") {
        Alert.alert("Google sign-in failed", message);
      }
    } finally {
      setGoogleLoading(false);
    }
  }

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

      router.replace(AUTHENTICATED_ROUTE);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to sign in. Please try again."
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
        contentContainerClassName="flex-grow px-[23px] pb-12 pt-5"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false} contentContainerStyle={{ width: "100%", maxWidth: 520, alignSelf: "center" }}
      >
        {/* Header */}
        <View className="mb-8 flex-row items-center justify-between">
          <View className="flex-row items-center">
            <IbdaLogo size={44} />
          </View>

          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/sign-up")}
            className="flex-row items-center py-2"
          >
            <Text className="text-[14px] leading-[22px] font-medium text-[#C24A3C]" variant="button">
              Sign up →
            </Text>
          </Pressable>
        </View>

        {/* Intro */}
        <Text className="text-[26px] leading-[34px] font-bold tracking-tight text-[#25221F]" variant="display" tone="olive">
          Welcome back
        </Text>

        <Text className="mt-1 text-[14px] leading-[22px] text-[#25221F]" variant="body">
          Sign in to continue managing your social{"\n"}
          presence and brand voice.
        </Text>

        {/* Google sign-in */}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Continue with Google"
          onPress={handleGoogleSignIn}
          disabled={googleLoading || loading}
          className={`mt-9 min-h-[48px] flex-row items-center justify-center border border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA] rounded-[18px] active:opacity-80 ${googleLoading || loading ? "opacity-60" : ""
            }`}
        >
          <Text className="mr-3 text-[23px] font-bold text-[#C24A3C]">
            G
          </Text>

          <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="button">
            {googleLoading ? "Connecting to Google..." : "Continue with Google"}
          </Text>
        </Pressable>

        {/* Divider */}
        <View className="my-6 flex-row items-center">
          <View className="h-px flex-1 bg-[#E2D9CF]" />
          <Text className="mx-3 text-[12px] font-bold tracking-wide text-[#25221F]" variant="caption">
            OR CONTINUE WITH EMAIL
          </Text>
          <View className="h-px flex-1 bg-[#E2D9CF]" />
        </View>

        {/* Email */}
        <Text className="mb-1.5 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
          Email Address
        </Text>

        <StudioInputFrame className="min-h-[42px] rounded-2xl flex-row items-center border border-[#E2D9CF] bg-[#F4F0EA] px-3 shadow-sm">
          <Text className="mr-3 text-lg text-[#25221F]">✉</Text>

          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="alex@company.com"
            placeholderTextColor="#25221F"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            accessibilityLabel="Email address"
            className="flex-1 py-4 text-[14px] text-[#25221F] rounded-[18px]"
            returnKeyType="next"
          />
        </StudioInputFrame>

        {/* Password */}
        <View className="mb-1.5 mt-5 flex-row items-center justify-between">
          <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
            Password
          </Text>

          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/forgot-password")}
            hitSlop={8}
          >
            <Text className="text-[14px] leading-[22px] font-medium text-[#C24A3C]" variant="button">
              Forgot password?
            </Text>
          </Pressable>
        </View>

        <StudioInputFrame className="min-h-[42px] rounded-2xl flex-row items-center border border-[#E2D9CF] bg-[#F4F0EA] px-3 shadow-sm">
          <Text className="mr-3 text-lg text-[#25221F]">♙</Text>

          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Enter your password"
            placeholderTextColor="#25221F"
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            autoComplete="current-password"
            accessibilityLabel="Password"
            className="flex-1 py-4 text-[14px] text-[#25221F] rounded-[18px]"
            returnKeyType="done"
            onSubmitEditing={handleSignIn}
          />

          <Pressable
            accessibilityRole="button"
            accessibilityLabel={showPassword ? "Hide password" : "Show password"}
            onPress={() => setShowPassword((current) => !current)}
            hitSlop={10}
          >
            <Text className="text-[14px] leading-[22px] text-[#25221F]" variant="button">
              {showPassword ? "◉" : "◎"}
            </Text>
          </Pressable>
        </StudioInputFrame>

        {/* Remember me */}
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: rememberMe }}
          onPress={() => setRememberMe((current) => !current)}
          className="mt-5 flex-row items-center self-start py-1"
        >
          <View
            className={`mr-3 h-6 w-6 items-center justify-center rounded-md ${rememberMe ? "bg-[#C24A3C]" : "bg-[#F4F0EA]"
              }`}
          >
            {rememberMe && (
              <Text className="text-[14px] leading-[22px] font-bold text-[#FAF8F4]" variant="label">✓</Text>
            )}
          </View>

          <Text className="text-[14px] leading-[22px] text-[#25221F]" variant="button">
            Remember me on this device
          </Text>
        </Pressable>

        {/* Validation / connection message */}
        {error ? (
          <Text
            accessibilityRole="alert"
            className="mt-3 text-[14px] leading-[23px] text-[#C24A3C]" variant="body"
          >
            {error}
          </Text>
        ) : null}

        {/* Email sign-in */}
        <Pressable
          accessibilityRole="button"
          onPress={handleSignIn}
          disabled={loading || googleLoading}
          className={`mt-8 min-h-[48px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] active:bg-[#A63F32] shadow-sm shadow-[#C24A3C]/10 active:opacity-80 ${loading || googleLoading ? "opacity-60" : ""
            }`}
        >
          <Text className="text-[14px] leading-[22px] font-bold text-[#FAF8F4]" variant="button">
            {loading ? "Signing in..." : "Sign In"}
          </Text>
          <Text className="ml-2 text-xl text-[#FAF8F4]">→</Text>
        </Pressable>

        {/* AI co-pilot card */}
        <View className="mt-6 flex-row items-center rounded-[24px] border border-[#E2D9CF] bg-[#F4F0EA] px-4 py-5">
          <View className="mr-4 h-12 w-12 items-center justify-center rounded-full bg-[#F4F0EA]">
            <Text className="text-xl text-[#25221F]">✧</Text>
          </View>

          <View className="flex-1">
            <View className="flex-row flex-wrap items-center">
              <Text className="text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
                AI Content Co-pilot
              </Text>

              <View className="ml-2 rounded-full bg-[#F4F0EA] px-2 py-0.5">
                <Text className="text-[11px] font-bold text-[#25221F]" variant="caption">
                  V2.4
                </Text>
              </View>
            </View>

            <Text
              numberOfLines={2}
              className="mt-1 text-[14px] leading-[23px] text-[#25221F]" variant="body"
            >
              Ready to craft posts in your custom brand voice.
            </Text>
          </View>
        </View>

        {/* Footer */}
        <View className="mt-auto items-center pt-9">
          <View className="flex-row flex-wrap items-center justify-center">
            <Text className="text-[14px] leading-[22px] text-[#25221F]" variant="body">
              Don&apos;t have an account?
            </Text>

            <Pressable
              onPress={() => router.push("/sign-up")}
              accessibilityRole="button"
              className="ml-2 py-1"
            >
              <Text className="text-[14px] leading-[22px] font-semibold text-[#C24A3C]" variant="button">
                Sign up free
              </Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
