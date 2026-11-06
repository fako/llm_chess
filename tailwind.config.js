/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./*/htmx/**/*.htmx",
    "./*/static/**/*.js",
    "./*/jinja2.py",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#FAF6EE",
        card: "#FFFDF8",
        line: "#E6DCCB",
        ink: "#3A2E25",
        muted: "#7A6A5A",
        walnut: {
          DEFAULT: "#8B5E3C",
          dark: "#6F4A2F",
          light: "#B88A63",
        },
        square: {
          light: "#F1E9DA",
          dark: "#C9AE88",
        },
        sage: "#7D9461",
        brick: "#B8503F",
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", "'Times New Roman'", "serif"],
      },
    },
  },
  plugins: [],
};
