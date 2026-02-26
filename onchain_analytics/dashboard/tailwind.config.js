/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // ACU brand colors
        acu: {
          primary: '#3B82F6',
          secondary: '#10B981',
          dark: '#1E293B',
          light: '#F8FAFC',
        },
        // Trading colors
        buy: '#10B981',
        sell: '#EF4444',
      },
    },
  },
  plugins: [],
};
