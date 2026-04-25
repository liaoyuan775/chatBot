import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Noto Serif SC'", "serif"],
        body: ["'Noto Sans SC'", "sans-serif"]
      },
      colors: {
        ink: "var(--ink)",
        primary: "var(--primary)",
        mint: "var(--mint)",
        shell: "var(--shell)"
      },
      boxShadow: {
        soft: "0 10px 30px rgba(29, 66, 73, 0.08)"
      }
    }
  },
  plugins: []
} satisfies Config;
