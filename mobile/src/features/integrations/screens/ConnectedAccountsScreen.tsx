import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import {
  disconnectSocialAccount,
  getConnectedAccounts,
  startSocialConnection,
  type ConnectedAccountsResponse,
  type SocialAccount,
  type SocialPlatform,
  type SocialProvider,
} from "../services/socialAccount.service";

const PLATFORM_META: Record<
  SocialPlatform,
  { icon: string; description: string }
> = {
  instagram: {
    icon: "◎",
    description: "Connect a professional Instagram account.",
  },
  facebook_pages: {
    icon: "f",
    description: "Connect a Facebook Page you manage.",
  },
  linkedin: {
    icon: "in",
    description: "Connect your LinkedIn presence.",
  },
  tiktok: {
    icon: "♪",
    description: "Connect a TikTok account.",
  },
};

export function ConnectedAccountsScreen() {
  const [data, setData] = useState<ConnectedAccountsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [workingPlatform, setWorkingPlatform] = useState<SocialPlatform | "">(
    ""
  );
  const [disconnectingId, setDisconnectingId] = useState("");

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      setData(await getConnectedAccounts());
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load connected accounts."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load])
  );

  const accountGroups = useMemo(() => {
    const groups = new Map<SocialPlatform, SocialAccount[]>();
    for (const account of data?.accounts ?? []) {
      const accounts = groups.get(account.platform) ?? [];
      accounts.push(account);
      groups.set(account.platform, accounts);
    }
    return groups;
  }, [data]);

  const connect = async (provider: SocialProvider) => {
    if (!provider.configured || workingPlatform) return;
    setWorkingPlatform(provider.platform);
    setError("");
    try {
      const result = await startSocialConnection(provider.platform);
      Alert.alert(
        "Connection unavailable",
        result.authorization_url
          ? "The provider authorization flow is not available in this app yet."
          : "No authorization URL was returned."
      );
    } catch (connectError) {
      setError(
        connectError instanceof Error
          ? connectError.message
          : "Unable to start the connection."
      );
    } finally {
      setWorkingPlatform("");
    }
  };

  const disconnect = (account: SocialAccount) => {
    Alert.alert(
      "Disconnect account?",
      `Ibda will remove its saved connection to ${account.display_name || account.platform_account_id}.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Disconnect",
          style: "destructive",
          onPress: () => void confirmDisconnect(account),
        },
      ]
    );
  };

  const confirmDisconnect = async (account: SocialAccount) => {
    setDisconnectingId(account.id);
    setError("");
    try {
      await disconnectSocialAccount(account.id);
      await load(true);
    } catch (disconnectError) {
      setError(
        disconnectError instanceof Error
          ? disconnectError.message
          : "Unable to disconnect this account."
      );
    } finally {
      setDisconnectingId("");
    }
  };

  return (
    <View className="flex-1 bg-[#FCF9F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 32,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#FF6B5F"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <Text className="mb-2 text-xs font-bold uppercase tracking-[3px] text-[#FF6B5F]">
          PUBLISHING SETUP
        </Text>
        <Text className="text-4xl font-bold text-[#24221F]">
          Connected Accounts
        </Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#827970]">
          Manage the social accounts associated with your workspace. A platform
          is shown as connected only when the backend has a saved account.
        </Text>

        {error ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text className="leading-5 text-[#A33D34]">{error}</Text>
            {data ? (
              <Pressable
                onPress={() => void load(true)}
                accessibilityRole="button"
                className="mt-2 min-h-11 self-start justify-center px-2"
              >
                <Text className="font-semibold text-[#FF6B5F]">Try again</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator size="large" color="#FF6B5F" />
            <Text className="mt-3 text-[#827970]">
              Checking account connections...
            </Text>
          </View>
        ) : error && !data ? (
          <View className="rounded-3xl border border-[#EAE4DC] bg-white p-5">
            <Text className="font-semibold text-[#24221F]">
              Couldn’t load connected accounts
            </Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-11 self-start justify-center rounded-xl bg-[#24221F] px-4"
            >
              <Text className="font-semibold text-white">Try again</Text>
            </Pressable>
          </View>
        ) : data ? (
          <View className="gap-4">
            {data.providers.map((provider) => {
              const meta = PLATFORM_META[provider.platform];
              const accounts = accountGroups.get(provider.platform) ?? [];
              return (
                <View
                  key={provider.platform}
                  className="rounded-3xl border border-[#EAE4DC] bg-white p-5"
                >
                  <View className="flex-row items-start gap-4">
                    <View className="h-12 w-12 items-center justify-center rounded-2xl bg-[#F3EEE8]">
                      <Text className="text-xl font-bold text-[#51483F]">
                        {meta.icon}
                      </Text>
                    </View>
                    <View className="flex-1">
                      <Text className="text-lg font-bold text-[#24221F]">
                        {provider.name}
                      </Text>
                      <Text className="mt-1 text-sm leading-5 text-[#827970]">
                        {meta.description}
                      </Text>
                    </View>
                  </View>

                  {accounts.length > 0 ? (
                    <View className="mt-4 gap-3">
                      {accounts.map((account) => {
                        const connected = account.status === "connected";
                        return (
                          <View
                            key={account.id}
                            className="rounded-2xl border border-[#EAE4DC] bg-[#FCF9F4] p-4"
                          >
                            <View className="flex-row items-center justify-between gap-3">
                              <View className="flex-1">
                                <Text className="font-semibold text-[#24221F]">
                                  {account.display_name ||
                                    account.platform_account_id}
                                </Text>
                                <Text
                                  className={`mt-1 text-sm ${
                                    connected
                                      ? "text-[#477B64]"
                                      : "text-[#A35E36]"
                                  }`}
                                >
                                  {connected
                                    ? "Connected"
                                    : account.status === "expired"
                                      ? "Connection expired"
                                      : "Disconnected"}
                                </Text>
                              </View>
                              <Pressable
                                onPress={() => disconnect(account)}
                                disabled={disconnectingId === account.id}
                                accessibilityRole="button"
                                className="min-h-11 justify-center rounded-xl border border-[#EAE4DC] px-3"
                              >
                                {disconnectingId === account.id ? (
                                  <ActivityIndicator
                                    size="small"
                                    color="#FF6B5F"
                                  />
                                ) : (
                                  <Text className="font-semibold text-[#A33D34]">
                                    Disconnect
                                  </Text>
                                )}
                              </Pressable>
                            </View>
                          </View>
                        );
                      })}
                    </View>
                  ) : (
                    <View className="mt-4 flex-row items-center gap-2 rounded-xl bg-[#F3EEE8] px-3 py-3">
                      <View className="h-2.5 w-2.5 rounded-full bg-[#A79D94]" />
                      <Text className="text-sm font-semibold text-[#827970]">
                        Not connected
                      </Text>
                    </View>
                  )}

                  {!provider.configured ? (
                    <Text className="mt-3 text-sm leading-5 text-[#827970]">
                      {provider.reason}
                    </Text>
                  ) : null}
                  <Pressable
                    onPress={() => void connect(provider)}
                    disabled={
                      !provider.configured ||
                      workingPlatform === provider.platform
                    }
                    accessibilityRole="button"
                    accessibilityState={{
                      disabled: !provider.configured,
                    }}
                    className={`mt-4 min-h-11 flex-row items-center justify-center rounded-xl px-4 ${
                      provider.configured
                        ? "bg-[#FF6B5F]"
                        : "bg-[#EAE4DC]"
                    }`}
                  >
                    {workingPlatform === provider.platform ? (
                      <ActivityIndicator color="#FFFFFF" />
                    ) : (
                      <Text
                        className={`font-bold ${
                          provider.configured
                            ? "text-white"
                            : "text-[#827970]"
                        }`}
                      >
                        {provider.configured
                          ? accounts.some(
                              (account) => account.status === "expired"
                            )
                            ? "Reconnect"
                            : "Connect"
                          : "Not configured"}
                      </Text>
                    )}
                  </Pressable>
                </View>
              );
            })}
          </View>
        ) : null}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
