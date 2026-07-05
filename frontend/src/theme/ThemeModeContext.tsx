import { createContext, useContext } from 'react';

export type ThemeMode = 'light' | 'dark';

export interface ThemeModeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
}

export const THEME_MODE_STORAGE_KEY = 'market-agent.theme-mode.v1';

export const ThemeModeContext = createContext<ThemeModeContextValue | null>(null);

export function useThemeMode(): ThemeModeContextValue {
  const value = useContext(ThemeModeContext);
  if (!value) throw new Error('useThemeMode must be used within ThemeModeContext.Provider');
  return value;
}
