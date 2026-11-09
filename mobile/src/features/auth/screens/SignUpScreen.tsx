import { StudioText as Text } from "../../../components/ui/StudioText";
import { IbdaLogo } from "../../../components/brand/IbdaLogo";
import { StudioInputFrame, StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";
import { router } from "expo-router";
import { signInWithGoogle } from "../services/google-auth.service";
import { useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, ScrollView, StatusBar, View } from "react-native";
import { signUp } from "../services/auth.service";

export function SignUpScreen() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [googleLoading, setGoogleLoading] = useState(false);

  const handleGoogleSignUp = async () => {
    setGoogleLoading(true);

    try {
      const error = await signInWithGoogle();

      if (error) {
        if (Platform.OS === "web") {
          window.alert(error);
        } else {
          Alert.alert("Google Sign-Up Failed", error);
        }
      }
    } finally {
      setGoogleLoading(false);
    }
  };

  async function handleSignUp() {
    setError("");
    setSuccessMessage("");

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

    setLoading(true);

    try {
      const result = await signUp(name, email, password);

      if (result.error) {
        setError(result.error);
        return;
      }

      setSuccessMessage(
        "Account request submitted. Check your email if confirmation is required."
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
          onPress={() => router.replace("/")}
          className="mb-8 flex-row items-center self-start"
        >
          <Text className="text-xl text-[#C24A3C]">←</Text>
          <Text className="ml-2 text-[15px] leading-[24px] font-medium text-[#716A64]" variant="button">
            Back to home
          </Text>
        </Pressable>

        <View className="mb-8 flex-row items-center">
          <IbdaLogo size={44} />
        </View>

        <Text className="text-[30px] leading-[37px] tracking-[-0.6px] font-bold tracking-tight text-[#292724]" variant="metric">
          Create your account
        </Text>
        <Text className="mt-2 text-base leading-6 text-[#716A64]" variant="body">
          Start building a consistent social presence with your AI-powered
          creative studio.
        </Text>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Sign up with Google"
          onPress={handleGoogleSignUp}
          disabled={googleLoading}
          className={`mt-5 min-h-[54px] flex-row items-center justify-center border border-[#E9E2DA] bg-white active:bg-[#F1E9DF] rounded-[18px] ${googleLoading ? "opacity-60" : ""
            }`}
        >
          <Text className="mr-3 text-[23px] font-bold text-[#4285F4]">
            G
          </Text>

          <Text className="text-base leading-[24px] font-semibold text-[#292724]" variant="button">
            {googleLoading ? "Connecting to Google..." : "Continue with Google"}
          </Text>
        </Pressable>

         
        {/* Divider */}
        <View className="my-6 flex-row items-center">
          <View className="h-px flex-1 bg-[#E9E2DA]" />
          <Text className="mx-3 text-[12px] font-bold tracking-wide text-[#716A64]" variant="caption">
            OR CONTINUE WITH EMAIL
          </Text>
          <View className="h-px flex-1 bg-[#E9E2DA]" />
        </View>

        <View className="mt-6">
          <Text className="mb-2 text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
            Full name
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Your full name"
            placeholderTextColor="#716A64"
            autoCapitalize="words"
            autoComplete="name"
            accessibilityLabel="Full name"
            className="min-h-14 border border-[#E9E2DA] bg-[#F7F4EF] px-4 text-base text-[#292724] rounded-[18px]"
          />
        </View>

        <View className="mt-5">
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
          />
        </View>

        <View className="mt-5">
          <Text className="mb-2 text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
            Password
          </Text>
          <StudioInputFrame className="min-h-14 flex-row items-center border border-[#E9E2DA] bg-white px-4">
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="At least 8 characters"
              placeholderTextColor="#716A64"
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              autoComplete="new-password"
              accessibilityLabel="Password"
              className="flex-1 py-4 text-base text-[#292724] rounded-[18px]"
            />
            <Pressable onPress={() => setShowPassword(!showPassword)}>
              <Text className="ml-2 text-[15px] leading-[24px] text-[#716A64]" variant="button">
                {showPassword ? "Hide" : "Show"}
              </Text>
            </Pressable>
          </StudioInputFrame>
        </View>

        <View className="mt-5">
          <Text className="mb-2 text-[15px] leading-[24px] font-semibold text-[#292724]" variant="label">
            Confirm password
          </Text>
          <TextInput
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            placeholder="Enter your password again"
            placeholderTextColor="#716A64"
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            autoComplete="new-password"
            accessibilityLabel="Confirm password"
            className="min-h-14 border border-[#E9E2DA] bg-[#F7F4EF] px-4 text-base text-[#292724] rounded-[18px]"
          />
        </View>

        {error ? (
          <Text accessibilityRole="alert" className="mt-4 text-[15px] leading-[23px] text-[#C24A3C]" variant="body">
            {error}
          </Text>
        ) : null}

        {successMessage ? (
          <Text accessibilityRole="alert" className="mt-4 text-[15px] leading-[23px] text-ibda-green" variant="body">
            {successMessage}
          </Text>
        ) : null}

        <Pressable
          onPress={handleSignUp}
          disabled={loading}
          accessibilityRole="button"
          className={`mt-7 min-h-[54px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] ${loading ? "opacity-60" : "active:opacity-80"
            }`}
        >
          <Text className="text-base leading-[24px] font-bold text-white" variant="button">
            {loading ? "Creating account..." : "Create account"}
          </Text>
          {!loading && <Text className="ml-2 text-lg text-white">→</Text>}
        </Pressable>

        <View className="mt-7 flex-row flex-wrap items-center justify-center">
          <Text className="text-[15px] leading-[24px] text-[#716A64]" variant="body">
            Already have an account?
          </Text>
          <Pressable onPress={() => router.replace("/sign-in")} className="ml-1 p-1">
            <Text className="text-[15px] leading-[24px] font-semibold text-[#C24A3C]" variant="button">
              Sign in
            </Text>
          </Pressable>
        </View>

        <Text className="mt-auto pt-8 text-center text-[12px] leading-[23px] text-[#716A64]" variant="caption">
          By creating an account, you agree to our Terms of Service and Privacy
          Policy.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}