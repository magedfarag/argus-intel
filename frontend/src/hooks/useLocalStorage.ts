import { useState, useEffect } from "react";

const PREFIX = "geoint:";

/**
 * Like useState but persists to localStorage under a namespaced key.
 * Falls back to `initialValue` when nothing is stored or the stored
 * value cannot be parsed.
 */
export function useLocalStorage<T>(key: string, initialValue: T) {
  const storageKey = PREFIX + key;

  const [value, setValue] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored !== null ? (JSON.parse(stored) as T) : initialValue;
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      // quota exceeded — silently ignore
    }
  }, [storageKey, value]);

  return [value, setValue] as const;
}