import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { AuthChangeEvent, Session } from "@supabase/supabase-js";
import { supabase } from "../../../lib/supabase";

type AuthContextValue = {
  session: Session | null;
  loading: boolean;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(
      (_event: AuthChangeEvent, currentSession: Session | null) => {
        if (mounted) {
          setSession(currentSession);
          setLoading(false);
        }
      }
    );

    supabase.auth
      .getSession()
      .then(({ data, error }: { data: { session: Session | null }; error: { message: string } | null }) => {
        if (!mounted) return;

        if (error) {
          console.error("Unable to restore session:", error.message);
          setSession(null);
        } else {
          setSession(data.session);
        }

        setLoading(false);
      })
      .catch((error: unknown) => {
        if (!mounted) return;

        console.error("Session initialization failed:", error);
        setSession(null);
        setLoading(false);
      });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}