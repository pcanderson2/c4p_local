#!/bin/bash
# Run this script on Ubuntu to produce c4p-social_1.0_amd64.deb
# Usage: bash build-deb.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/build"
PKG_NAME="c4p-social_1.0_amd64"

echo "[build] Checking for dpkg-deb..."
if ! command -v dpkg-deb &>/dev/null; then
    sudo apt-get install -y dpkg
fi

echo "[build] Preparing package directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$PKG_NAME/DEBIAN"
mkdir -p "$BUILD_DIR/$PKG_NAME/opt/c4p-social"

# Copy DEBIAN control files
cp -r "$SCRIPT_DIR/DEBIAN/"* "$BUILD_DIR/$PKG_NAME/DEBIAN/"
chmod 755 "$BUILD_DIR/$PKG_NAME/DEBIAN/postinst"
chmod 755 "$BUILD_DIR/$PKG_NAME/DEBIAN/prerm"
chmod 755 "$BUILD_DIR/$PKG_NAME/DEBIAN/postrm"

# Copy project files into /opt/c4p-social payload
echo "[build] Copying project files..."
rsync -a --exclude='deb/' --exclude='.git/' --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$PROJECT_DIR/" "$BUILD_DIR/$PKG_NAME/opt/c4p-social/"

# Copy pre-configured .env from deb/opt/c4p-social/ if present
if [ -f "$SCRIPT_DIR/opt/c4p-social/.env" ]; then
    echo "[build] Bundling pre-configured .env..."
    cp "$SCRIPT_DIR/opt/c4p-social/.env" "$BUILD_DIR/$PKG_NAME/opt/c4p-social/.env"
    chmod 600 "$BUILD_DIR/$PKG_NAME/opt/c4p-social/.env"
fi

# Fix line endings on all text files
find "$BUILD_DIR/$PKG_NAME/opt/c4p-social" \
    -name "*.py" -o -name "*.sh" -o -name "*.sql" \
    -o -name "*.yml" -o -name "*.md" -o -name "*.txt" \
    | xargs dos2unix -q 2>/dev/null || true

# Set permissions
find "$BUILD_DIR/$PKG_NAME/opt/c4p-social" -type f -exec chmod 644 {} \;
find "$BUILD_DIR/$PKG_NAME/opt/c4p-social" -type d -exec chmod 755 {} \;

echo "[build] Building .deb package..."
dpkg-deb --build --root-owner-group "$BUILD_DIR/$PKG_NAME"

mv "$BUILD_DIR/${PKG_NAME}.deb" "$SCRIPT_DIR/${PKG_NAME}.deb"

echo ""
echo "=== Build complete ==="
echo ""
echo "  Package: $SCRIPT_DIR/${PKG_NAME}.deb"
echo ""
echo "  Install with:"
echo "    sudo dpkg -i $SCRIPT_DIR/${PKG_NAME}.deb"
echo ""
echo "  After install, edit your config:"
echo "    sudo nano /opt/c4p-social/.env"
echo ""
