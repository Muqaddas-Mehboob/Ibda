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
        "ibda-background": "#FAF8F4",
        "ibda-surface": "#F4F0EA",
        "ibda-charcoal": "#25221F",
        "ibda-brown": "#25221F",
        "ibda-coral": "#C24A3C",
        "ibda-lavender": "#F4F0EA",
        "ibda-green": "#25221F",
      },
    },
  },
  plugins: [],
};