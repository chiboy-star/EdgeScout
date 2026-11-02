import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          950: "#0E0E10",
          900: "#17171A",
          800: "#232327",
        },
        border: {
          subdued: "#4A4A52",
          dark: "#232327",
        },
        text: {
          primary: "#F4F2EA",
          muted: "#9A9AA3",
        },
        lemon: "#E9F56B",
        lavender: "#B49CFF",
        coral: "#FF7A6B",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "serif"],
        sans: ["var(--font-inter)", "sans-serif"],
      },
      borderRadius: {
        squircle: "14px",
      },
    },
  },
  plugins: [],
};
export default config;
