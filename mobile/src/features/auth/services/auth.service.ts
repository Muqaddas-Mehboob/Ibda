import { supabase } from "../../../lib/supabase";

export type AuthResult = {
  error: string | null;
};

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}

export async function signIn(
  email: string,
  password: string
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim().toLowerCase(),
      password,
    });

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function signUp(
  name: string,
  email: string,
  password: string
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.signUp({
      email: email.trim().toLowerCase(),
      password,
      options: {
        data: {
          full_name: name.trim(),
        },
      },
    });

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function resetPassword(
  email: string
): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.resetPasswordForEmail(
      email.trim().toLowerCase()
    );

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}

export async function signOut(): Promise<AuthResult> {
  try {
    const { error } = await supabase.auth.signOut();

    return { error: error?.message ?? null };
  } catch (error) {
    return { error: getErrorMessage(error) };
  }
}