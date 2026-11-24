#!/usr/bin/env bash
# Compila Tailwind CSS con el CLI standalone (no hace falta Node).
#   ./scripts/build_css.sh           genera apps/web/static/web/tailwind.css
#   ./scripts/build_css.sh --watch   recompila al guardar las plantillas
# El binario se descarga una vez en .bin/ (ignorado por git).
set -euo pipefail

VERSION="v3.4.17"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/.bin/tailwindcss-$VERSION"

if [ ! -x "$BIN" ]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) ASSET="tailwindcss-linux-x64" ;;
    Linux-aarch64) ASSET="tailwindcss-linux-arm64" ;;
    Darwin-x86_64) ASSET="tailwindcss-macos-x64" ;;
    Darwin-arm64) ASSET="tailwindcss-macos-arm64" ;;
    MINGW*|MSYS*|CYGWIN*) ASSET="tailwindcss-windows-x64.exe" ;;
    *) echo "Sistema no soportado: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
  esac
  mkdir -p "$ROOT/.bin"
  echo "Descargando Tailwind $VERSION ($ASSET)..."
  curl -sSLf -o "$BIN" "https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/$ASSET"
  chmod +x "$BIN"
fi

cd "$ROOT"
"$BIN" -c tailwind/tailwind.config.js -i tailwind/input.css -o apps/web/static/web/tailwind.css --minify "$@"
