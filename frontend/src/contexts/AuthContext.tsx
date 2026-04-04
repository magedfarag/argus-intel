import React, { createContext, useContext, useState } from "react";
import { getApiKey, setApiKey as persistKey } from "../api/client";

interface AuthContextValue {
  apiKey: string;
  setApiKey: (key: string) => void;
}

const AuthContext = createContext<AuthContextValue>({ apiKey: "", setApiKey: () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string>(getApiKey);
  function setApiKey(key: string) {
    persistKey(key);
    setApiKeyState(key);
  }
  return <AuthContext.Provider value={{ apiKey, setApiKey }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
