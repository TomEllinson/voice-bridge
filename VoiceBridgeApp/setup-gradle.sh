#!/bin/bash
# Setup script to download Gradle wrapper

set -e

GRADLE_VERSION="8.5"
WRAPPER_URL="https://raw.githubusercontent.com/gradle/gradle/v${GRADLE_VERSION}.0/gradle/wrapper/gradle-wrapper.jar"

echo "Setting up Gradle wrapper..."

# Create wrapper directory
mkdir -p gradle/wrapper

# Download wrapper jar
echo "Downloading gradle-wrapper.jar..."
if command -v curl &> /dev/null; then
    curl -L -o gradle/wrapper/gradle-wrapper.jar "$WRAPPER_URL"
elif command -v wget &> /dev/null; then
    wget -O gradle/wrapper/gradle-wrapper.jar "$WRAPPER_URL"
else
    echo "Error: Neither curl nor wget is available. Please install one of them."
    exit 1
fi

# Make gradlew executable
chmod +x gradlew

echo "Gradle wrapper setup complete!"
echo "You can now build the APK with: ./gradlew assembleDebug"
