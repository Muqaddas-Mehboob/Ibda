function unsupportedPlatformError(): Error {
  return new Error(
    "Supabase session storage is supported only on iOS, Android, and web."
  );
}

export const supabaseStorage = {
  async getItem(): Promise<string | null> {
    throw unsupportedPlatformError();
  },

  async setItem(): Promise<void> {
    throw unsupportedPlatformError();
  },

  async removeItem(): Promise<void> {
    throw unsupportedPlatformError();
  },
};
