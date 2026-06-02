import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b1220",
        panel: "#101827",
        border: "#24324a",
        accent: "#2f80ed",
        signal: "#14b894",
        warning: "#f5a524",
        danger: "#d94848"
      }
    }
  },
  plugins: []
};

export default config;

