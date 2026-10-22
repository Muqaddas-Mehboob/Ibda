/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        ibda: {
          background: "#FCF9F4",
          coral: "#F76B5B",
          charcoal: "#1C1C19",
          surface: "#F0EDE9",
          lavender: "#EEDDF3",
          brown: "#58413E",
          muted: "#947D76",
          border: "#E7E2DC",
          white: "#FFFFFF",
          green: "#27845B",
        },
      },
    },
  },
  plugins: [],
};