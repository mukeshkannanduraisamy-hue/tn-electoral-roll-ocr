import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: "#030712",
          900: "#080C16",
          850: "#0E1526",
          800: "#151F36",
          700: "#1E293B",
        },
        quantum: {
          cyan: "#00F2FE",
          indigo: "#6366F1",
          violet: "#8B5CF6",
          emerald: "#10B981",
          amber: "#F59E0B",
          rose: "#F43F5E",
          electric: "#4FACFE",
        },
        serena: {
          violet: "#8B5CF6",
          indigo: "#6366F1",
          cyan: "#06B6D4",
          emerald: "#10B981",
          amber: "#F59E0B",
          rose: "#F43F5E",
        },
      },
      backgroundImage: {
        "quantum-radial": "radial-gradient(ellipse at top, rgba(99, 102, 241, 0.15), transparent 70%)",
        "quantum-grid": "linear-gradient(to right, rgba(255, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(to bottom, rgba(255, 255, 255, 0.03) 1px, transparent 1px)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "glow-slow": "glow 4s ease-in-out infinite alternate",
        "shimmer": "shimmer 2s linear infinite",
        "laser-scan": "laserScan 2.5s ease-in-out infinite alternate",
        "quantum-spin": "spin 8s linear infinite",
      },
      keyframes: {
        glow: {
          "0%": { opacity: "0.4", filter: "blur(20px)" },
          "100%": { opacity: "0.8", filter: "blur(32px)" },
        },
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        laserScan: {
          "0%": { top: "4%" },
          "100%": { top: "96%" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
