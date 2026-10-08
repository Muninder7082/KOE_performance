/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
      },
      colors: {
        brand: { 50: "#eef4ff", 100: "#dbe7ff", 500: "#2563eb", 600: "#1d4ed8", 700: "#1e40af", 900: "#0f2b46" },
      },
    },
  },
  plugins: [],
};
