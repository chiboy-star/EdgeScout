/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        charcoal: {
          950: '#0E0E10',
          900: '#17171A',
          800: '#232327',
          700: '#2F2F35',
          600: '#4A4A52',
        },
        lemon: '#E9F56B',
        lavender: '#B49CFF',
        alert: '#FF7A6B',
        textPrimary: '#F4F2EA',
        textMuted: '#9A9AA3',
      },
      fontFamily: {
        serif: ['var(--font-fraunces)', 'Georgia', 'serif'],
        sans: ['var(--font-inter)', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

