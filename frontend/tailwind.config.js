/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      boxShadow: {
        "editor-soft": "0 24px 70px rgba(15, 23, 42, 0.16)",
        "editor-dark": "0 24px 70px rgba(0, 0, 0, 0.36)",
      },
      fontFamily: {
        legal: ['"IBM Plex Serif"', "Georgia", "serif"],
        sans: ['"IBM Plex Sans"', "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
