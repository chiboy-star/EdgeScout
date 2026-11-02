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
          muted: "#A8A8B3",
        },
        lemon: "#E9F56B",
        lavender: "#B49CFF",
        coral: "#FF7A6B",
      },
      fontFamily: {
        display: ["'Fraunces'", "Georgia", "serif"],
        sans: ["'Inter Variable'", "'Inter'", "sans-serif"],
      },
      borderRadius: {
        squircle: "14px",
      },
    },
  },
  plugins: [],
};
export default config;
