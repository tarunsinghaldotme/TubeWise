#!/bin/bash

# ══════════════════════════════════════════════════════════════
# build.sh — Build TubeWise into a standalone binary
# ══════════════════════════════════════════════════════════════
#
# Uses PyInstaller's --onedir mode, which creates a folder with
# the binary + shared libraries pre-extracted on disk.
#
# WHY --onedir INSTEAD OF --onefile?
#   --onefile compresses everything into one 50+ MB executable.
#   Every time you run it, it must DECOMPRESS to a temp dir first.
#   With heavy deps like NumPy (44 MB), botocore (18 MB), yt-dlp
#   (10 MB), this adds 3-8 seconds of startup delay.
#
#   --onedir extracts once at build time. The binary starts up
#   instantly because the libraries are already on disk.
#
# PREREQUISITES:
#   pip install pyinstaller
#
# USAGE:
#   chmod +x build.sh
#   ./build.sh
#
# OUTPUT:
#   dist/tubewise/tubewise  — The launcher binary
#
# INSTALL:
#   # Symlink to your PATH (don't copy — keeps the folder intact)
#   sudo ln -sfn "$(pwd)/dist/tubewise/tubewise" /usr/local/bin/tubewise
#
#   # Or install to /opt for a cleaner setup:
#   sudo cp -r dist/tubewise /opt/tubewise
#   sudo ln -sfn /opt/tubewise/tubewise /usr/local/bin/tubewise
#
#   NOTE: Use -sfn (not -sf) on macOS. The -n flag prevents ln from
#   following an existing symlink and creating the link inside it.
#
# ══════════════════════════════════════════════════════════════

set -e  # Exit on any error

INSTALL_DIR="/opt/tubewise"

echo ""
echo "🧠 TubeWise — Building standalone binary..."
echo "============================================="
echo ""

# ── Step 1: Check if PyInstaller is installed ──
if ! command -v pyinstaller &> /dev/null; then
    echo "📦 Installing PyInstaller..."
    pip install pyinstaller
fi

# ── Step 2: Clean previous builds ──
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/ *.spec

# ── Step 3: Build the binary ──
# Flags explained:
#   --onedir         : Extract libraries at BUILD time, not every launch.
#                      This eliminates the 3-8 second decompression delay
#                      that --onefile causes with heavy deps (NumPy, boto3).
#   --name tubewise  : Name the output binary 'tubewise'
#   --clean          : Clean PyInstaller cache before building
#   --noconfirm      : Don't ask for confirmation to overwrite
#
#   --hidden-import  : Some packages aren't auto-detected by PyInstaller
#                      because they're imported dynamically. We explicitly
#                      tell PyInstaller to include them.
#
#   --collect-all    : Some packages have data files (not just code) that
#                      need to be bundled. This ensures everything is included.
#
#   --exclude-module : Skip modules that add bloat but aren't needed:
#                      - pytest/unittest: test frameworks (not needed at runtime)
#                      - tkinter: GUI toolkit (TubeWise is CLI-only)
#                      - PIL/matplotlib: image/plotting libs (not used)
#                      - scipy: scientific computing (not used)

echo "🔨 Building binary (this takes 1-2 minutes)..."
echo ""

pyinstaller \
    --onedir \
    --name tubewise \
    --clean \
    --noconfirm \
    --hidden-import=langchain_aws \
    --hidden-import=langchain_community \
    --hidden-import=langchain_text_splitters \
    --hidden-import=youtube_transcript_api \
    --hidden-import=yt_dlp \
    --hidden-import=notion_client \
    --hidden-import=dotenv \
    --hidden-import=botocore \
    --hidden-import=boto3 \
    --hidden-import=pydantic \
    --hidden-import=models \
    --hidden-import=playlist \
    --hidden-import=queue_manager \
    --hidden-import=worker \
    --hidden-import=logging_config \
    --hidden-import=sqlite3 \
    --hidden-import=concurrent.futures \
    --collect-all langchain_aws \
    --collect-all youtube_transcript_api \
    --collect-all yt_dlp \
    --collect-all certifi \
    --exclude-module pytest \
    --exclude-module unittest \
    --exclude-module tkinter \
    --exclude-module PIL \
    --exclude-module matplotlib \
    --exclude-module scipy \
    agent.py

# ── Step 4: Check if build succeeded ──
echo ""
if [ -f "dist/tubewise/tubewise" ]; then
    BINARY_SIZE=$(du -sh dist/tubewise | cut -f1)
    echo "✅ Build successful!"
    echo ""
    echo "📍 Binary location: $(pwd)/dist/tubewise/tubewise"
    echo "📏 Bundle size: ${BINARY_SIZE}"
    echo ""
    echo "🚀 Install system-wide:"
    echo ""
    echo "   # Option 1: Install to /opt (recommended)"
    echo "   sudo rm -rf ${INSTALL_DIR}"
    echo "   sudo cp -r dist/tubewise ${INSTALL_DIR}"
    echo "   sudo ln -sfn ${INSTALL_DIR}/tubewise /usr/local/bin/tubewise"
    echo ""
    echo "   # Option 2: Symlink from build dir (for development)"
    echo "   sudo ln -sfn \"$(pwd)/dist/tubewise/tubewise\" /usr/local/bin/tubewise"
    echo ""
    echo "📝 Usage:"
    echo "   tubewise \"https://www.youtube.com/watch?v=VIDEO_ID\""
    echo "   tubewise \"https://www.youtube.com/playlist?list=PLAYLIST_ID\""
    echo "   tubewise \"URL\" --async"
    echo "   tubewise --status"
    echo "   tubewise --worker start"
    echo ""
    echo "⚙️  Make sure your config is at ~/.tubewise/.env"
    echo "   mkdir -p ~/.tubewise"
    echo "   cp .env ~/.tubewise/.env"
else
    echo "❌ Build failed. Check the errors above."
    exit 1
fi
