/** @type {import('tailwindcss').Config} */
export default {
    content: ["./index.html", "./src/**/*.{ts,tsx}"],
    darkMode: ["class", '[data-theme="dark"]'],
    theme: {
        extend: {
            fontFamily: {
                sans: ['"IBM Plex Sans"', "Inter", "system-ui", "sans-serif"],
            },
            keyframes: {
                "toast-in": {
                    from: { opacity: "0", transform: "translateY(10px) scale(0.97)" },
                    to: { opacity: "1", transform: "translateY(0) scale(1)" },
                },
            },
            animation: {
                "toast-in": "toast-in 220ms cubic-bezier(0.22, 1, 0.36, 1) both",
            },
            colors: {
                brand: {
                    50: "#eefbf6",
                    100: "#d5f5e7",
                    200: "#aeebd2",
                    300: "#79dab7",
                    400: "#45c298",
                    500: "#27a880",
                    600: "#1c8768",
                    700: "#196c54",
                    800: "#185643",
                    900: "#164738",
                },
            },
        },
    },
    plugins: [],
};
