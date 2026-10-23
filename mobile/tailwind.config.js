/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./app/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        "ibda-background": "#FCF9F4",
        "ibda-surface": "#F0EDE8",
        "ibda-charcoal": "#201F1C",
        "ibda-brown": "#705B52",
        "ibda-coral": "#FF6B5F",
        "ibda-lavender": "#EEDCF5",
        "ibda-green": "#287D54",
      },
    },
  },
  plugins: [],
};