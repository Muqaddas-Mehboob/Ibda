function getBrowserStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    throw new Error("Browser session storage is unavailable.");
  }
}

export const supabaseStorage = {
  async getItem(key: string): Promise<string | null> {
    const storage = getBrowserStorage();
    if (!storage) {
      return null;
    }

    try {
      return storage.getItem(key);
    } catch {
      throw new Error("Browser session storage read failed.");
    }
  },

  async setItem(key: string, value: string): Promise<void> {
    const storage = getBrowserStorage();
    if (!storage) {
      throw new Error("Browser session storage is unavailable outside the browser.");
    }

    try {
      storage.setItem(key, value);
    } catch {
      throw new Error("Browser session storage write failed.");
    }
  },

  async removeItem(key: string): Promise<void> {
    const storage = getBrowserStorage();
    if (!storage) {
      throw new Error("Browser session storage is unavailable outside the browser.");
    }

    try {
      storage.removeItem(key);
    } catch {
      throw new Error("Browser session storage deletion failed.");
    }
  },
};
