import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";

function storageError(operation: string): Error {
  return new Error(`Secure session storage ${operation} failed.`);
}

export const supabaseStorage = {
  async getItem(key: string): Promise<string | null> {
    let secureValue: string | null;
    try {
      secureValue = await SecureStore.getItemAsync(key);
    } catch {
      throw storageError("read");
    }

    if (secureValue !== null) {
      return secureValue;
    }

    let legacyValue: string | null;
    try {
      legacyValue = await AsyncStorage.getItem(key);
    } catch {
      throw storageError("migration read");
    }

    if (legacyValue === null) {
      return null;
    }

    try {
      await SecureStore.setItemAsync(key, legacyValue);
    } catch {
      throw storageError("migration write");
    }

    try {
      await AsyncStorage.removeItem(key);
    } catch {
      let rollbackFailed = false;
      try {
        await SecureStore.deleteItemAsync(key);
      } catch {
        rollbackFailed = true;
      }

      throw storageError(
        rollbackFailed ? "migration rollback" : "migration cleanup"
      );
    }

    return legacyValue;
  },

  async setItem(key: string, value: string): Promise<void> {
    try {
      await SecureStore.setItemAsync(key, value);
    } catch {
      throw storageError("write");
    }

    try {
      await AsyncStorage.removeItem(key);
    } catch {
      throw storageError("legacy cleanup");
    }
  },

  async removeItem(key: string): Promise<void> {
    let secureStoreFailed = false;
    let legacyCleanupFailed = false;

    try {
      await SecureStore.deleteItemAsync(key);
    } catch {
      secureStoreFailed = true;
    }

    try {
      await AsyncStorage.removeItem(key);
    } catch {
      legacyCleanupFailed = true;
    }

    if (secureStoreFailed || legacyCleanupFailed) {
      throw storageError("delete or legacy cleanup");
    }
  },
};
