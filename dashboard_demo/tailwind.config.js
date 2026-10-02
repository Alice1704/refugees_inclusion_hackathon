/** @type {import('tailwindcss').Config} */
// Colours are declared once as CSS custom properties in static/css/input.css.
// The helpers below expose them to Tailwind (with opacity support) so there is a
// single source of truth for the brand palette.
const token = (name) => `rgb(var(${name}) / <alpha-value>)`;

module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        // UNHCR blue and approved supporting tints
        brand: {
          DEFAULT: token("--brand"),
          80: token("--brand-80"),
          60: token("--brand-60"),
          40: token("--brand-40"),
          20: token("--brand-20"),
          dark: token("--brand-dark"), // derived hover/active shade of brand blue
        },
        // Secondary accent - use sparingly (status indicators only)
        accent: token("--accent"),
        // Grayscale
        ink: {
          DEFAULT: token("--ink"),
          medium: token("--ink-medium"),
          light: token("--ink-light"),
        },
        line: {
          DEFAULT: token("--line"),
          soft: token("--line-soft"),
        },
      },
      fontFamily: {
        // Proxima Nova is the licensed brand typeface and wins wherever it is
        // installed locally. Figtree (self-hosted, OFL) is the FOSS stand-in and
        // the practical default; Lato is the brand's secondary face, then Arial.
        sans: ["Proxima Nova", "Figtree", "Lato", "Arial", "Helvetica Neue", "sans-serif"],
        heading: ["Proxima Nova", "Figtree", "Lato", "Arial", "Helvetica Neue", "sans-serif"],
        body: ["Proxima Nova", "Figtree", "Lato", "Arial", "Helvetica Neue", "sans-serif"],
      },
      lineHeight: {
        heading: "1.1",
        subheading: "1.2",
        body: "1.4",
      },
      borderRadius: {
        // Minimal radius: 0-6px
        sm: "2px",
        DEFAULT: "3px",
        md: "4px",
        lg: "6px",
      },
    },
  },
  plugins: [],
};
