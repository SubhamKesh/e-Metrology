/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14181C",
        paper: "#F6F4EE",
        paper2: "#EDE9DE",
        slate: {
          DEFAULT: "#3D4A52",
          50: "#F3F5F5",
          100: "#E4E9EA",
          400: "#7A8A91",
          600: "#4E5D64",
        },
        line: "#DDD6C7",
        teal: {
          DEFAULT: "#1F5F5B",
          50: "#EAF2F1",
          100: "#D2E4E2",
          600: "#1A514D",
          700: "#154340",
        },
        brass: {
          DEFAULT: "#B08D3E",
          50: "#F7F1E1",
          100: "#EDE0BC",
          600: "#8F7130",
        },
        success: { DEFAULT: "#2E7D46", 50: "#E9F5EC" },
        warning: { DEFAULT: "#B07A22", 50: "#FBF1E1" },
        danger: { DEFAULT: "#B23A2E", 50: "#FBEAE8" },
        info: { DEFAULT: "#2A5F8F", 50: "#E9F1F8" },
        neutralx: { DEFAULT: "#6B7280", 50: "#F1F2F3" },
      },
      fontFamily: {
        display: ["'Source Serif 4'", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
        xl: "14px",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(20, 24, 28, 0.06), 0 1px 0 rgba(20, 24, 28, 0.04)",
        raised: "0 4px 16px rgba(20, 24, 28, 0.10)",
      },
      maxWidth: {
        prose: "72ch",
      },
    },
  },
  plugins: [],
};
