import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { supabase } from "../../../lib/supabase";

const SUPPORT_EMAIL = process.env.EXPO_PUBLIC_SUPPORT_EMAIL?.trim();
const PRIVACY_POLICY_URL = process.env.EXPO_PUBLIC_PRIVACY_POLICY_URL?.trim();
const TERMS_URL = process.env.EXPO_PUBLIC_TERMS_URL?.trim();

function SettingRow({
  icon,
  title,
  description,
  onPress,
  destructive = false,
  disabled = false,
}: {
  icon: string;
  title: string;
  description: string;
  onPress: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${description}`}
      className={`min-h-[68px] flex-row items-center gap-3 px-4 py-3 ${
        disabled ? "opacity-50" : ""
      }`}
    >
      <View
        className={`h-10 w-10 items-center justify-center rounded-2xl ${
          destructive ? "bg-[#FFF0ED]" : "bg-[#F3EEE8]"
        }`}
      >
        <Text
          className={`text-base font-bold ${
            destructive ? "text-[#B04438]" : "text-[#827970]"
          }`}
        >
          {icon}
        </Text>
      </View>
      <View className="flex-1">
        <Text
          className={`font-semibold ${
            destructive ? "text-[#B04438]" : "text-[#24221F]"
          }`}
        >
          {title}
        </Text>
        <Text className="mt-1 text-sm leading-5 text-[#827970]">
          {description}
        </Text>
      </View>
      <Text className="text-lg text-[#A79D94]">›</Text>
    </Pressable>
  );
}

export function SettingsScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [savedName, setSavedName] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [sendingReset, setSendingReset] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [updatingPassword, setUpdatingPassword] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [loadingAccount, setLoadingAccount] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadAccount() {
      try {
        const { data, error } = await supabase.auth.getUser();
        if (!active) return;
        if (error) {
          setLoadError(`Unable to load your account: ${error.message}`);
          return;
        }
        const userEmail = data.user?.email ?? "";
        const metadata = data.user?.user_metadata ?? {};
        const name =
          typeof metadata.full_name === "string"
            ? metadata.full_name
            : typeof metadata.name === "string"
              ? metadata.name
              : "";
        setEmail(userEmail);
        setDisplayName(name);
        setSavedName(name);
      } catch (error) {
        if (active) {
          setLoadError(
            `Unable to load your account: ${
              error instanceof Error ? error.message : "Please try again."
            }`
          );
        }
      } finally {
        if (active) setLoadingAccount(false);
      }
    }

    void loadAccount();
    return () => {
      active = false;
    };
  }, []);

  const contactSupport = async () => {
    if (!SUPPORT_EMAIL) {
      Alert.alert(
        "Support unavailable",
        "A support email address has not been configured for this app."
      );
      return;
    }
    try {
      await Linking.openURL(`mailto:${SUPPORT_EMAIL}`);
    } catch (error) {
      Alert.alert(
        "Unable to open email",
        error instanceof Error
          ? error.message
          : `Please email ${SUPPORT_EMAIL} for assistance.`
      );
    }
  };

  const openConfiguredLink = async (url: string | undefined, label: string) => {
    if (!url) {
      Alert.alert(
        `${label} unavailable`,
        `A public ${label.toLowerCase()} URL has not been configured yet.`
      );
      return;
    }
    try {
      await Linking.openURL(url);
    } catch (error) {
      Alert.alert(
        `Unable to open ${label.toLowerCase()}`,
        error instanceof Error ? error.message : "Please try again later."
      );
    }
  };

  const saveProfile = async () => {
    const name = displayName.trim();
    if (name.length < 2 || name.length > 100) {
      Alert.alert(
        "Check your name",
        "Display name must be between 2 and 100 characters."
      );
      return;
    }
    if (savingProfile) return;

    setSavingProfile(true);
    try {
      const { data, error } = await supabase.auth.updateUser({
        data: { full_name: name },
      });
      if (error) throw error;
      const saved =
        typeof data.user.user_metadata.full_name === "string"
          ? data.user.user_metadata.full_name
          : name;
      setDisplayName(saved);
      setSavedName(saved);
      Alert.alert("Profile updated", "Your display name has been saved.");
    } catch (error) {
      Alert.alert(
        "Couldn’t update profile",
        error instanceof Error ? error.message : "Please try again."
      );
    } finally {
      setSavingProfile(false);
    }
  };

  const sendPasswordReset = async () => {
    if (!email || sendingReset) {
      if (!email) Alert.alert("Email unavailable", "Your account email could not be loaded.");
      return;
    }

    setSendingReset(true);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email);
      if (error) throw error;
      Alert.alert(
        "Check your email",
        `Password reset instructions were sent to ${email}.`
      );
    } catch (error) {
      Alert.alert(
        "Couldn’t send reset email",
        error instanceof Error ? error.message : "Please try again."
      );
    } finally {
      setSendingReset(false);
    }
  };

  const updatePassword = async () => {
    if (updatingPassword) return;
    if (password.length < 8) {
      Alert.alert(
        "Choose a stronger password",
        "Your password must be at least 8 characters."
      );
      return;
    }
    if (password !== confirmPassword) {
      Alert.alert("Passwords don’t match", "Enter the same password twice.");
      return;
    }

    setUpdatingPassword(true);
    try {
      const {
        data: { session },
        error: sessionError,
      } = await supabase.auth.getSession();
      if (sessionError) throw sessionError;
      if (!session?.access_token) {
        throw new Error("Please sign in again before changing your password.");
      }

      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;

      setPassword("");
      setConfirmPassword("");
      Alert.alert("Password updated", "Your password has been changed.");
    } catch (error) {
      Alert.alert(
        "Couldn’t update password",
        error instanceof Error ? error.message : "Please try again."
      );
    } finally {
      setUpdatingPassword(false);
    }
  };

  const signOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
      router.replace("/sign-in");
    } catch (error) {
      setSigningOut(false);
      Alert.alert(
        "Couldn’t sign out",
        error instanceof Error ? error.message : "Please try again."
      );
    }
  };

  const confirmSignOut = () => {
    Alert.alert("Sign out?", "You’ll need to sign in again to access Ibda.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Sign out",
        style: "destructive",
        onPress: () => void signOut(),
      },
    ]);
  };

  const confirmDeleteAccount = () => {
    Alert.alert(
      "Delete your account?",
      "Account deletion permanently removes access to your account and associated data. Continue only if you want to request permanent deletion.",
      [
        { text: "Close", style: "cancel" },
        {
          text: "Continue",
          style: "destructive",
          onPress: () => {
            Alert.alert(
              "Account deletion unavailable",
              "Secure account deletion is not configured in this app. No account data has been deleted. Deletion requires a protected backend endpoint with a server-side Supabase service-role credential.",
              [
                { text: "Close", style: "cancel" },
                {
                  text: "Contact support",
                  onPress: () => void contactSupport(),
                },
              ]
            );
          },
        },
      ]
    );
  };

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 32,
        }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          YOUR WORKSPACE
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">Settings</Text>
        <Text className="mb-7 mt-3 text-base leading-6 text-[#827970]">
          Manage your account and how you use Ibda.
        </Text>

        {loadError ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text className="text-[#A33D34]">{loadError}</Text>
          </View>
        ) : null}

        <Section title="Account">
          {loadingAccount ? (
            <View className="flex-row items-center gap-3 px-4 py-4">
              <ActivityIndicator size="small" color="#FF6B5F" />
              <Text className="text-[#827970]">Loading account details...</Text>
            </View>
          ) : null}
          <View className="px-4 pb-4 pt-4">
            <Text className="mb-2 text-sm font-semibold text-[#51483F]">
              Display name
            </Text>
            <TextInput
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="Your name"
              placeholderTextColor="#A79D94"
              maxLength={100}
              autoCapitalize="words"
              accessibilityLabel="Display name"
              className="min-h-12 rounded-xl border border-[#EAE4DC] bg-[#FCF9F4] px-4 text-[#24221F]"
            />
            {displayName.trim() !== savedName ? (
              <Pressable
                onPress={() => void saveProfile()}
                disabled={savingProfile}
                accessibilityRole="button"
                className="mt-3 min-h-11 flex-row items-center justify-center rounded-xl bg-[#FF6B5F] px-4"
              >
                {savingProfile ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <Text className="font-bold text-white">Save profile</Text>
                )}
              </Pressable>
            ) : null}
          </View>
          <View className="border-t border-[#EAE4DC] px-4 py-4">
            <Text className="mb-1 text-sm font-semibold text-[#51483F]">
              Email address
            </Text>
            <Text className="text-[#827970]">
              {email || "Email unavailable"}
            </Text>
          </View>
          <View className="border-t border-[#EAE4DC]">
            <SettingRow
              icon="↻"
              title="Reset password"
              description={
                sendingReset ? "Sending instructions..." : "Email a secure reset link"
              }
              disabled={sendingReset}
              onPress={() => void sendPasswordReset()}
            />
          </View>
          <View className="border-t border-[#EAE4DC] px-4 py-4">
            <Text className="mb-2 text-sm font-semibold text-[#51483F]">
              New password
            </Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="At least 8 characters"
              placeholderTextColor="#A79D94"
              secureTextEntry
              autoCapitalize="none"
              autoComplete="new-password"
              textContentType="newPassword"
              accessibilityLabel="New password"
              className="min-h-12 rounded-xl border border-[#EAE4DC] bg-[#FCF9F4] px-4 text-[#24221F]"
            />
            <Text className="mb-2 mt-3 text-sm font-semibold text-[#51483F]">
              Confirm new password
            </Text>
            <TextInput
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              placeholder="Enter it again"
              placeholderTextColor="#A79D94"
              secureTextEntry
              autoCapitalize="none"
              autoComplete="new-password"
              textContentType="newPassword"
              accessibilityLabel="Confirm new password"
              className="min-h-12 rounded-xl border border-[#EAE4DC] bg-[#FCF9F4] px-4 text-[#24221F]"
            />
            <Pressable
              onPress={() => void updatePassword()}
              disabled={updatingPassword || !password || !confirmPassword}
              accessibilityRole="button"
              className={`mt-3 min-h-11 flex-row items-center justify-center rounded-xl px-4 ${
                updatingPassword || !password || !confirmPassword
                  ? "bg-[#D7CEC5]"
                  : "bg-[#24221F]"
              }`}
            >
              {updatingPassword ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text className="font-bold text-white">Update password</Text>
              )}
            </Pressable>
          </View>
        </Section>

        <Section title="Preferences">
          <SettingRow
            icon="$"
            title="Plans & billing"
            description="View your plan, billing history, and available plans"
            onPress={() => router.push("/subscription")}
          />
          <View className="border-t border-[#EAE4DC]">
          <SettingRow
            icon="◎"
            title="Connected accounts"
            description="Manage social media account connections"
            onPress={() => router.push("/social-accounts")}
          />
          </View>
          <View className="border-t border-[#EAE4DC] px-4 py-4">
            <Text className="leading-5 text-[#827970]">
              Notification preferences and theme selection aren’t configurable
              yet. Notifications are currently delivered in-app.
            </Text>
          </View>
        </Section>

        <Section title="Support">
          <SettingRow
            icon="?"
            title="Contact support"
            description={SUPPORT_EMAIL || "Support contact not configured"}
            onPress={() => void contactSupport()}
          />
          <View className="border-t border-[#EAE4DC]">
            <SettingRow
              icon="i"
              title="Privacy policy"
              description="Open Ibda’s privacy information"
              onPress={() =>
                void openConfiguredLink(PRIVACY_POLICY_URL, "Privacy policy")
              }
            />
          </View>
          <View className="border-t border-[#EAE4DC]">
            <SettingRow
              icon="§"
              title="Terms of service"
              description="Open Ibda’s terms"
              onPress={() => void openConfiguredLink(TERMS_URL, "Terms of service")}
            />
          </View>
        </Section>

        <Section title="Account actions">
          <SettingRow
            icon="↪"
            title={signingOut ? "Signing out..." : "Sign out"}
            description="Sign out of this device"
            disabled={signingOut}
            onPress={confirmSignOut}
          />
          <View className="border-t border-[#EAE4DC]">
            <SettingRow
              icon="×"
              title="Delete account"
              description="Permanently remove your Ibda account"
              destructive
              onPress={confirmDeleteAccount}
            />
          </View>
        </Section>
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View className="mb-6">
      <Text className="mb-3 text-sm font-bold uppercase tracking-wide text-[#827970]">
        {title}
      </Text>
      <View className="overflow-hidden rounded-3xl border border-[#EAE4DC] bg-white">
        {children}
      </View>
    </View>
  );
}
