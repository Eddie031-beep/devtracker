/**
 * Tailwind CSS para DevTracker (módulos del examen semestral).
 *
 * - Prefijo `tw-`: las utilidades no chocan con las clases de app.css (.grid, .container, .card...).
 * - Sin preflight: el reset de Tailwind no toca las pantallas que ya existían.
 * - Los colores apuntan a las variables de app.css, así el modo oscuro funciona solo.
 *
 * Se compila con `scripts/build_css.sh` (CLI standalone, sin Node) y el resultado
 * (`apps/web/static/web/tailwind.css`) se sube al repo para que Railway no tenga que compilar.
 */
module.exports = {
  prefix: "tw-",
  content: ["./apps/**/templates/**/*.html", "./apps/**/*.py"],
  darkMode: ["selector", '[data-theme="dark"]'],
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        "ink-2": "var(--ink-2)",
        muted: "var(--muted)",
        page: "var(--bg)",
        card: "var(--card)",
        line: "var(--line)",
        "line-2": "var(--line-2)",
        field: "var(--field)",
        accent: "var(--accent)",
        "accent-dark": "var(--accent-dark)",
        "accent-soft": "var(--accent-soft)",
      },
      fontFamily: {
        sans: "var(--sans)",
        mono: "var(--mono)",
      },
      borderRadius: {
        card: "var(--radius)",
      },
    },
  },
};
