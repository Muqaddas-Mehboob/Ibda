import { StudioText as Text } from "../../../components/ui/StudioText";
import { StudioPressable as Pressable, StudioCard } from "../../../components/ui/StudioControls";
import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Platform, RefreshControl, ScrollView, View } from "react-native";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { router, useFocusEffect } from "expo-router";
import { BottomNavigation } from "../../../components/navigation/BottomNavigation";
import { confirmAsync } from "../../../lib/confirm";
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

const SOCIAL_RETURN_URL = "ibda://social-accounts";
type OAuthPlatform = "instagram" | "facebook_pages";
type OAuthStatus =
  | "connected"
  | "no_pages"
  | "cancelled"
  | "failed";
const OAUTH_STATUSES: OAuthStatus[] = [
  "connected",
  "no_pages",
  "cancelled",
  "failed",
];

function isOAuthPlatform(platform: SocialPlatform): platform is OAuthPlatform {
  return platform === "instagram" || platform === "facebook_pages";
}

function isOAuthStatus(value: unknown): value is OAuthStatus {
  return (
    typeof value === "string" &&
    OAUTH_STATUSES.some((status) => status === value)
  );
}

function getOAuthCallbackOrigin(
  value: string,
  platform: OAuthPlatform
): string | undefined {
  try {
    const url = new URL(value);
    const isInstagram = platform === "instagram";
    if (
      url.protocol !== "https:" ||
      url.hostname !== "www.facebook.com" ||
      url.port ||
      url.username ||
      url.password ||
      (isInstagram
        ? url.pathname !== "/dialog/oauth"
        : !/^\/v\d+\.\d+\/dialog\/oauth$/.test(url.pathname)) ||
      url.hash
    ) {
      return undefined;
    }

    const query = url.searchParams;
    if (
      !query.get("client_id") ||
      query.get("response_type") !== "code" ||
      !query.get("state") ||
      query.getAll("client_id").length !== 1 ||
      query.getAll("response_type").length !== 1 ||
      query.getAll("redirect_uri").length !== 1 ||
      query.getAll("state").length !== 1
    ) {
      return undefined;
    }

    if (isInstagram) {
      if (
        !query.get("config_id") ||
        query.getAll("config_id").length !== 1
      ) {
        return undefined;
      }
    } else if (
      !query.get("config_id") ||
      query.get("override_default_response_type") !== "true" ||
      query.getAll("config_id").length !== 1
    ) {
      return undefined;
    }

    const redirectUriValue = query.get("redirect_uri");
    if (!redirectUriValue) return undefined;
    const redirectUri = new URL(redirectUriValue);
    const validRedirectUri =
      redirectUri.protocol === "https:" &&
      Boolean(redirectUri.hostname) &&
      !redirectUri.username &&
      !redirectUri.password &&
      redirectUri.pathname ===
        (isInstagram
          ? "/api/social/oauth/instagram/callback/"
          : "/api/social/oauth/facebook_pages/callback/") &&
      !redirectUri.search &&
      !redirectUri.hash;
    return validRedirectUri ? redirectUri.origin : undefined;
  } catch {
    return undefined;
  }
}

function waitForWebOAuthCallback(
  popup: Window,
  callbackOrigin: string,
  platform: OAuthPlatform
): Promise<OAuthStatus | "closed" | "timeout"> {
  const messageType =
    platform === "instagram"
      ? "ibda-instagram-oauth"
      : "ibda-facebook-oauth";
  return new Promise((resolve) => {
    let finished = false;
    const finish = (result: OAuthStatus | "closed" | "timeout") => {
      if (finished) return;
      finished = true;
      window.removeEventListener("message", onMessage);
      window.clearInterval(closeCheck);
      window.clearTimeout(timeout);
      resolve(result);
    };
    const onMessage = (event: MessageEvent<unknown>) => {
      if (
        event.origin !== callbackOrigin ||
        event.source !== popup ||
        typeof event.data !== "object" ||
        event.data === null
      ) {
        return;
      }

      if (
        !("type" in event.data) ||
        !("status" in event.data) ||
        event.data.type !== messageType ||
        !isOAuthStatus(event.data.status)
      ) {
        return;
      }
      finish(event.data.status);
    };

    window.addEventListener("message", onMessage);
    const closeCheck = window.setInterval(() => {
      if (popup.closed) finish("closed");
    }, 500);
    const timeout = window.setTimeout(() => finish("timeout"), 10 * 60 * 1000);
  });
}

function getOAuthCallbackStatus(
  callbackUrl: string
): OAuthStatus | undefined {
  try {
    const parsedUrl = new URL(callbackUrl);
    if (
      parsedUrl.protocol !== "ibda:" ||
      parsedUrl.hostname !== "social-accounts" ||
      parsedUrl.pathname !== "" ||
      parsedUrl.username ||
      parsedUrl.password ||
      parsedUrl.port ||
      parsedUrl.searchParams.getAll("status").length !== 1
    ) {
      return undefined;
    }

    const parsed = Linking.parse(callbackUrl);
    const status = parsed.queryParams?.status;
    return isOAuthStatus(status) ? status : undefined;
  } catch {
    return undefined;
  }
}

export function ConnectedAccountsScreen() {
  const [data, setData] = useState<ConnectedAccountsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [workingPlatform, setWorkingPlatform] = useState<SocialPlatform | "">(
    ""
  );
  const [disconnectingId, setDisconnectingId] = useState("");
  const [notice, setNotice] = useState("");

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
    const oauthPlatform = isOAuthPlatform(provider.platform)
      ? provider.platform
      : undefined;
    const webPopup =
      oauthPlatform && Platform.OS === "web"
        ? window.open("about:blank", "_blank")
        : null;
    if (
      oauthPlatform &&
      Platform.OS === "web" &&
      !webPopup
    ) {
      setError(
        `Your browser blocked the ${provider.name} login window. Allow pop-ups for this site and try again.`
      );
      return;
    }

    setWorkingPlatform(provider.platform);
    setError("");
    try {
      const responseMode = Platform.OS === "web" ? "web" : "native";
      const result = await startSocialConnection(
        provider.platform,
        oauthPlatform ? responseMode : undefined
      );
      if (oauthPlatform) {
        const callbackOrigin = getOAuthCallbackOrigin(
          result.authorization_url,
          oauthPlatform
        );
        if (!callbackOrigin) {
          setError(`The ${provider.name} authorization link was invalid.`);
          return;
        }

        let callbackStatus:
          | OAuthStatus
          | "closed"
          | "timeout"
          | undefined;
        if (Platform.OS === "web" && webPopup) {
          webPopup.location.replace(result.authorization_url);
          callbackStatus = await waitForWebOAuthCallback(
            webPopup,
            callbackOrigin,
            oauthPlatform
          );
        } else {
          const authResult = await WebBrowser.openAuthSessionAsync(
            result.authorization_url,
            SOCIAL_RETURN_URL
          );
          if (authResult.type !== "success") {
            setError(
              authResult.type === "cancel" || authResult.type === "dismiss"
                ? `${provider.name} connection was cancelled.`
                : `${provider.name} connection did not complete.`
            );
            return;
          }
          callbackStatus = getOAuthCallbackStatus(authResult.url);
        }

        switch (callbackStatus) {
          case "connected":
            Alert.alert(
              `${provider.name} connected`,
              oauthPlatform === "instagram"
                ? "Your Instagram professional account is now connected."
                : "Your authorized Facebook Pages are now connected."
            );
            await load(true);
            return;
          case "no_pages":
            Alert.alert(
              "No Facebook Pages found",
              "No Facebook Pages were available for the account you authorized."
            );
            return;
          case "cancelled":
            setError(`${provider.name} connection was cancelled.`);
            return;
          case "failed":
          default:
            setError(
              callbackStatus === "closed"
                ? `${provider.name} connection was cancelled.`
                : `Unable to connect ${provider.name}. Please try again.`
            );
            return;
        }
      }

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
      if (webPopup && !webPopup.closed) webPopup.close();
      setWorkingPlatform("");
    }
  };

  const disconnect = async (account: SocialAccount) => {
    if (disconnectingId) return;

    const accountName = account.display_name || account.platform_account_id;
    // React Native Web renders Alert.alert as a no-op, so web needs the
    // window.confirm() fallback that confirmAsync provides.
    const confirmed = await confirmAsync(
      "Disconnect account?",
      `Ibda will remove its saved connection to ${accountName}.`,
      { confirmText: "Disconnect", destructive: true }
    );
    if (!confirmed) return;

    setDisconnectingId(account.id);
    setError("");
    setNotice("");
    try {
      await disconnectSocialAccount(account.id);
      setNotice(`${accountName} was disconnected.`);
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
    <View className="flex-1 bg-[#FAF8F4]">
      <ScrollView
        contentContainerStyle={{
          padding: 24,
          paddingTop: 40,
          paddingBottom: 48, width: "100%", maxWidth: 960, alignSelf: "center",
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor="#C24A3C"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <Pressable
                onPress={() =>
                  router.canGoBack() ? router.back() : router.replace("/settings")
                }
                accessibilityRole="button"
                accessibilityLabel="Go back"
                className="mb-8 h-11 w-11 items-center justify-center rounded-full border border-[#E9E2DA] bg-white active:bg-[#F1E9DF]"
              >
                <Text className="text-xl text-[#716A64]">‹</Text>
              </Pressable>
        <Text className="mb-2 text-[12px] font-bold uppercase tracking-[2px] text-[#C24A3C]" variant="eyebrow" tone="secondary">
          PUBLISHING SETUP
        </Text>
        <Text className="text-[32px] leading-[39px] tracking-[-0.8px] font-bold text-[#292724]" variant="page" tone="charcoal">
          Connected Accounts
        </Text>
        <Text className="mb-6 mt-3 text-base leading-6 text-[#716A64]" variant="body">
          Manage the social accounts associated with your workspace. A platform
          is shown as connected only when the backend has a saved account.
        </Text>

        {error ? (
          <View className="mb-5 rounded-2xl border border-[#F0C5BE] bg-white p-4">
            <Text className="text-[#A33D34] text-[15px] leading-[24px]" variant="body">{error}</Text>
            {data ? (
              <Pressable
                onPress={() => void load(true)}
                accessibilityRole="button"
                className="mt-2 min-h-[54px] self-start justify-center px-2 rounded-[18px]"
              >
                <Text className="font-semibold text-[#C24A3C] text-[15px] leading-[24px]" variant="button">Try again</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {notice ? (
          <View className="mb-5 rounded-2xl border border-[#BFDCCB] bg-white p-4">
            <Text className="text-[#287D54] text-[15px] leading-[24px]" variant="body">{notice}</Text>
          </View>
        ) : null}

        {loading ? (
          <View className="items-center py-14">
            <ActivityIndicator size="large" color="#C24A3C" />
            <Text className="mt-3 text-[#716A64] text-[15px] leading-[24px]" variant="body">
              Checking account connections...
            </Text>
          </View>
        ) : error && !data ? (
          <StudioCard className="rounded-3xl border border-[#E9E2DA] bg-white p-5">
            <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
              Couldn’t load connected accounts
            </Text>
            <Pressable
              onPress={() => void load()}
              accessibilityRole="button"
              className="mt-4 min-h-[54px] self-start justify-center rounded-[18px] bg-[#292724] px-4"
            >
              <Text className="font-semibold text-white text-[15px] leading-[24px]" variant="button">Try again</Text>
            </Pressable>
          </StudioCard>
        ) : data ? (
          <View className="gap-4">
            {data.providers.map((provider) => {
              const meta = PLATFORM_META[provider.platform];
              const accounts = accountGroups.get(provider.platform) ?? [];
              return (
                <StudioCard
                  key={provider.platform}
                  className="rounded-3xl border border-[#E9E2DA] bg-white p-5"
                >
                  <View className="flex-row items-start gap-4">
                    <View className="h-12 w-12 items-center justify-center rounded-2xl bg-[#F1E9DF]">
                      <Text className="text-[21px] leading-[28px] tracking-[-0.3px] font-bold text-[#716A64]" variant="section">
                        {meta.icon}
                      </Text>
                    </View>
                    <View className="flex-1">
                      <Text className="text-[19px] leading-[26px] font-bold text-[#292724]" variant="cardTitle">
                        {provider.name}
                      </Text>
                      <Text className="mt-1 text-[15px] leading-[23px] text-[#716A64]" variant="body">
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
                            className="rounded-2xl border border-[#E9E2DA] bg-[#FAF8F4] p-4"
                          >
                            <View className="flex-row items-center justify-between gap-3">
                              <View className="flex-1">
                                <Text className="font-semibold text-[#292724] text-[15px] leading-[24px]" variant="label">
                                  {account.display_name ||
                                    account.platform_account_id}
                                </Text>
                                <Text
                                  className={`mt-1 text-[15px] leading-[24px] ${
                                    connected
                                      ? "text-[#477B64]"
                                      : "text-[#A35E36]"
                                  }`} variant="body"
                                >
                                  {connected
                                    ? "Connected"
                                    : account.status === "expired"
                                      ? "Connection expired"
                                      : "Disconnected"}
                                </Text>
                              </View>
                              <Pressable
                                onPress={() => void disconnect(account)}
                                disabled={disconnectingId === account.id}
                                accessibilityRole="button"
                                accessibilityLabel={`Disconnect ${
                                  account.display_name ||
                                  account.platform_account_id
                                }`}
                                className="min-h-[54px] justify-center rounded-[18px] border border-[#E9E2DA] px-3"
                              >
                                {disconnectingId === account.id ? (
                                  <ActivityIndicator
                                    size="small"
                                    color="#C24A3C"
                                  />
                                ) : (
                                  <Text className="font-semibold text-[#A33D34] text-[15px] leading-[24px]" variant="label">
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
                    <View className="mt-4 flex-row items-center gap-2 rounded-xl bg-[#F1E9DF] px-3 py-3">
                      <View className="h-2.5 w-2.5 rounded-full bg-[#A79D94]" />
                      <Text className="text-[15px] leading-[24px] font-semibold text-[#716A64]" variant="label">
                        Not connected
                      </Text>
                    </View>
                  )}

                  {!provider.configured ? (
                    <Text className="mt-3 text-[15px] leading-[23px] text-[#716A64]" variant="body">
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
                    className={`mt-4 min-h-[54px] flex-row items-center justify-center rounded-[18px] px-4 ${
                      provider.configured
                        ? "bg-[#C24A3C] active:bg-[#A63F32]"
                        : "bg-[#E9E2DA]"
                    }`}
                  >
                    {workingPlatform === provider.platform ? (
                      <ActivityIndicator color="#FFFFFF" />
                    ) : (
                      <Text
                        className={`font-bold ${
                          provider.configured
                            ? "text-white"
                            : "text-[#716A64]"
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
                </StudioCard>
              );
            })}
          </View>
        ) : null}
      </ScrollView>
      <BottomNavigation />
    </View>
  );
}
