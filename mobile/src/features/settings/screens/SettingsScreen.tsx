import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioInput as TextInput } from "../../../components/ui/StudioControls";
import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { confirmAsync } from "../../../lib/confirm";
import { supabase } from "../../../lib/supabase";
import { deleteAccount, signOut as signOutUser } from "../../auth/services/auth.service";

const SUPPORT_EMAIL = process.env.EXPO_PUBLIC_SUPPORT_EMAIL?.trim();
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
          destructive ? "bg-[#FFF0EC]" : "bg-[#F4F0EA]"
        }`}
      >
        <Text
          className={`text-[14px] leading-[22px] font-bold ${
            destructive ? "text-[#25221F]" : "text-[#25221F]"
          }`} variant="label"
        >
          {icon}
        </Text>
      </View>
      <View className="flex-1">
        <Text
          className={`font-semibold ${
            destructive ? "text-[#25221F]" : "text-[#25221F]"
          }`} variant="controlTitle"
        >
          {title}
        </Text>
        <Text className="mt-1 text-[14px] leading-[23px] text-[#25221F]" variant="body">
          {description}
        </Text>
      </View>
      <Text className="text-lg text-[#25221F]" variant="button">›</Text>
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
      const result = await signOutUser("global");
      if (result.error) {
        throw new Error(result.error);
      }
      router.replace("/sign-in");
    } catch (error) {
      Alert.alert(
        "Couldn’t sign out",
        error instanceof Error ? error.message : "Please try again."
      );
    } finally {
      setSigningOut(false);
    }
  };

  const confirmSignOut = async () => {
    const confirmed = await confirmAsync(
      "Sign out?",
      "You’ll need to sign in again to access Ibda.",
      {
        confirmText: "Sign out",
        cancelText: "Cancel",
        destructive: true,
      }
    );
    if (!confirmed) return;
    await signOut();
  };

  const confirmDeleteAccount = async () => {
    const confirmed = await confirmAsync(
      "Delete your account?",
      "This permanently removes your Ibda account and related data after the backend confirms deletion. Continue only if you want to permanently delete your account.",
      {
        confirmText: "Delete account",
        cancelText: "Close",
        destructive: true,
      }
    );
    if (!confirmed) return;

    try {
      const result = await deleteAccount();
      if (result.error) {
        Alert.alert("Couldn’t delete account", result.error);
        return;
      }
      router.replace("/sign-in");
    } catch (error) {
      Alert.alert(
        "Couldn’t delete account",
        error instanceof Error ? error.message : "Please try again."
      );
    }
  };

  return (
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
        }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Pressable
        onPress={() =>
          router.canGoBack() ? router.back() : router.replace("/dashboard")
        }
        accessibilityRole="button"
        accessibilityLabel="Go back"
        className="mb-4 h-11 w-11 items-center justify-center rounded-full border border-[#E2D9CF] bg-[#FAF8F4] active:bg-[#F4F0EA]"
      >
        <Text className="text-xl text-[#25221F]">‹</Text>
      </Pressable>
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="secondary">
          YOUR WORKSPACE
        </Text>
        <Text className="text-[22px] leading-[30px] tracking-[-0.4px] font-bold text-[#25221F]" variant="page" tone="olive">Settings</Text>
        <Text className="mb-7 mt-3 text-[14px] leading-6 text-[#25221F]" variant="body">
          Manage your account and how you use Ibda.
        </Text>

        {loadError ? (
          <View className="mb-5 rounded-2xl border border-[#F4796B] bg-[#FAF8F4] p-4">
            <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">{loadError}</Text>
          </View>
        ) : null}

        <Section title="Account">
          {loadingAccount ? (
            <View className="flex-row items-center gap-3 px-4 py-4">
              <ActivityIndicator size="small" color="#C24A3C" />
              <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">Loading account details...</Text>
            </View>
          ) : null}
          <View className="px-4 pb-4 pt-4">
            <Text className="mb-2 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
              Display name
            </Text>
            <TextInput
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="Your name"
              placeholderTextColor="#25221F"
              maxLength={100}
              autoCapitalize="words"
              accessibilityLabel="Display name"
              className="min-h-12 rounded-[18px] border border-[#E2D9CF] bg-[#FAF8F4] px-4 text-[#25221F]"
            />
            {displayName.trim() !== savedName ? (
              <Pressable
                onPress={() => void saveProfile()}
                disabled={savingProfile}
                accessibilityRole="button"
                className="mt-3 min-h-[48px] flex-row items-center justify-center rounded-[18px] bg-[#C24A3C] shadow-sm shadow-[#C24A3C]/15 active:bg-[#A63F32] px-4"
              >
                {savingProfile ? (
                  <ActivityIndicator color="#FAF8F4" />
                ) : (
                  <Text className="font-bold text-[#FAF8F4] text-[14px] leading-[22px]" variant="label">Save profile</Text>
                )}
              </Pressable>
            ) : null}
          </View>
          <View className="border-t border-[#E2D9CF] px-4 py-4">
            <Text className="mb-1 text-[14px] leading-[22px] font-semibold text-[#25221F]" variant="label">
              Email address
            </Text>
            <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">
              {email || "Email unavailable"}
            </Text>
          </View>
        </Section>

        <Section title="Preferences">
          <SettingRow
            icon="$"
            title="Plans & billing"
            description="View your plan, billing history, and available plans"
            onPress={() => router.push("/subscription")}
          />
          <View className="border-t border-[#E2D9CF]">
          <SettingRow
            icon="◎"
            title="Connected accounts"
            description="Manage social media account connections"
            onPress={() => router.push("/social-accounts")}
          />
          </View>
          <View className="border-t border-[#E2D9CF] px-4 py-4">
            <Text className="text-[#25221F] text-[14px] leading-[22px]" variant="body">
              Notification preferences and theme selection aren’t configurable
              yet. Notifications are currently delivered in-app.
            </Text>
          </View>
        </Section>

        <Section title="Support">
          <SettingRow
            icon="?"
            title="Contact support"
            description={
              SUPPORT_EMAIL || "Write a message to the Ibda support team"
            }
            onPress={() => router.push("/contact-support")}
          />
          <View className="border-t border-[#E2D9CF]">
            <SettingRow
              icon="i"
              title="Privacy policy"
              description="Open Ibda’s privacy information"
              onPress={() => router.push("/privacy-policy")}
            />
          </View>
          <View className="border-t border-[#E2D9CF]">
            <SettingRow
              icon="§"
              title="Terms of service"
              description="Open Ibda’s terms"
              onPress={() => router.push("/terms-of-service")}
            />
          </View>
        </Section>

        <Section title="Account actions">
          <SettingRow
            icon="↪"
            title={signingOut ? "Signing out..." : "Sign out"}
            description="Sign out of this device"
            disabled={signingOut}
            onPress={() => void confirmSignOut()}
          />
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
      <Text className="mb-3 text-[14px] leading-[22px] font-bold uppercase tracking-wide text-[#25221F]" variant="eyebrow" tone="secondary">
        {title}
      </Text>
      <View className="overflow-hidden rounded-3xl border border-[#25221F]/30 bg-[#F4F0EA]">
        {children}
      </View>
    </View>
  );
}
