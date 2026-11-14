import Constants from "expo-constants";
import { Platform } from "react-native";

const DEFAULT_API_URL = "http://127.0.0.1:8000/api";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

type ApiPlatform = "web" | "android" | "ios" | "windows" | "macos";

export function resolveApiBaseUrl({
  configuredUrl,
  platform,
  isDevelopment,
  expoHostUri,
}: {
  configuredUrl?: string;
  platform: ApiPlatform;
  isDevelopment: boolean;
  expoHostUri?: string | null;
}): string {
  const url = new URL((configuredUrl || DEFAULT_API_URL).trim());
  const isLoopback = LOOPBACK_HOSTS.has(url.hostname.toLowerCase());

  // On web, loopback means the developer's computer. On a physical device it
  // means the device itself, so resolve the Expo development server's host.
  if (platform === "web" || !isLoopback) {
    return url.toString().replace(/\/+$/, "");
  }

  if (!isDevelopment) {
    throw new Error(
      "The API URL points to this device. Configure EXPO_PUBLIC_API_URL with the production backend URL."
    );
  }

  if (!expoHostUri) {
    throw new Error(
      "Expo did not provide a development host. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }

  let developmentHost: string;
  try {
    const hostUri = expoHostUri.includes("://")
      ? expoHostUri
      : `http://${expoHostUri}`;
    developmentHost = new URL(hostUri).hostname;
  } catch {
    throw new Error(
      "Unable to resolve Expo's development host. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }

  if (!developmentHost || LOOPBACK_HOSTS.has(developmentHost.toLowerCase())) {
    throw new Error(
      "Expo's development host is not reachable by this device. Set EXPO_PUBLIC_API_URL to a reachable backend URL."
    );
  }

  url.hostname = developmentHost;
  return url.toString().replace(/\/+$/, "");
}

export function getApiBaseUrl(): string {
  const androidDevelopmentUrl =
    Platform.OS === "android" && __DEV__
      ? process.env.EXPO_PUBLIC_API_URL_ANDROID
      : undefined;
  return resolveApiBaseUrl({
    configuredUrl:
      androidDevelopmentUrl || process.env.EXPO_PUBLIC_API_URL,
    platform: Platform.OS as ApiPlatform,
    isDevelopment: __DEV__,
    expoHostUri: Constants.expoConfig?.hostUri,
  });
}
