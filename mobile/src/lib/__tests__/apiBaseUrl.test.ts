import { describe, expect, it } from "@jest/globals";
import { resolveApiBaseUrl } from "../apiBaseUrl";

describe("resolveApiBaseUrl", () => {
  it("keeps the development web loopback URL unchanged", () => {
    expect(
      resolveApiBaseUrl({
        platform: "web",
        isDevelopment: true,
      })
    ).toBe("http://127.0.0.1:8000/api");
  });

  it("replaces Android loopback with Expo's current host", () => {
    expect(
      resolveApiBaseUrl({
        platform: "android",
        isDevelopment: true,
        expoHostUri: "expo-host.example:8081",
      })
    ).toBe("http://expo-host.example:8000/api");
  });

  it("uses the same resolved host for an explicitly configured local API", () => {
    expect(
      resolveApiBaseUrl({
        configuredUrl: "http://localhost:8000/api/",
        platform: "android",
        isDevelopment: true,
        expoHostUri: "exp://expo-host.example:8081",
      })
    ).toBe("http://expo-host.example:8000/api");
  });

  it("allows an Android-specific development URL for non-LAN Expo modes", () => {
    expect(
      resolveApiBaseUrl({
        configuredUrl: "http://backend.dev:8000/api",
        platform: "android",
        isDevelopment: true,
        expoHostUri: "exp.direct:80",
      })
    ).toBe("http://backend.dev:8000/api");
  });

  it("preserves explicitly configured production API URLs", () => {
    expect(
      resolveApiBaseUrl({
        configuredUrl: "https://api.ibda.example/api/",
        platform: "android",
        isDevelopment: false,
      })
    ).toBe("https://api.ibda.example/api");
  });

  it("refuses device loopback in production", () => {
    expect(() =>
      resolveApiBaseUrl({
        configuredUrl: "http://127.0.0.1:8000/api",
        platform: "android",
        isDevelopment: false,
      })
    ).toThrow("Configure EXPO_PUBLIC_API_URL with the production backend URL.");
  });

  it("fails clearly when Expo does not expose a reachable development host", () => {
    expect(() =>
      resolveApiBaseUrl({
        platform: "android",
        isDevelopment: true,
      })
    ).toThrow("Expo did not provide a development host.");
  });
});
