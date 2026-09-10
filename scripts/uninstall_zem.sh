#!/bin/bash
set -e

echo "🗑️ Uninstalling Zem CLI..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: 'uv' is not installed."
    exit 1
fi

# Unisntall the package
uv tool uninstall zem

echo ""
echo "✅ Zem has been successfully uninstalled."
