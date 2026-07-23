"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"

type Theme = "light" | "dark"

type ThemeContextValue = {
  theme: Theme
  toggleTheme: () => void
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

function applyTheme(theme: Theme) {
  const root = document.documentElement
  if (theme === "dark") {
    root.classList.add("dark")
  } else {
    root.classList.remove("dark")
  }
  root.classList.add("theme-locked")
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "light"
  try {
    const saved = localStorage.getItem("theme")
    if (saved === "dark" || saved === "light") return saved
    const prefersDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    return prefersDark ? "dark" : "light"
  } catch {
    return "light"
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const initial = getInitialTheme()
    applyTheme(initial)
    setThemeState(initial)
    setMounted(true)
  }, [])

  const setTheme = useCallback((next: Theme) => {
    applyTheme(next)
    localStorage.setItem("theme", next)
    setThemeState(next)
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark"
      applyTheme(next)
      localStorage.setItem("theme", next)
      return next
    })
  }, [])

  return (
    <ThemeContext.Provider
      value={{
        theme: mounted ? theme : "light",
        toggleTheme,
        setTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider")
  }
  return context
}
