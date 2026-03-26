#!/usr/bin/env python3
"""
Android Developer Agent
Specialized agent for building Android applications.
Uses Kotlin, Jetpack Compose, Gradle, and Android SDK tools.
"""

import subprocess
import os
import json
from pathlib import Path
from typing import Optional, List, Dict

ANDROID_HOME = Path.home() / "Android/Sdk"
GRADLE_WRAPPER = "./gradlew"


class AndroidDevAgent:
    """Agent for Android app development."""
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.api_level = 34  # Android 14
        self.compile_sdk = 34
        self.min_sdk = 28  # Android 9
        self.target_sdk = 34
    
    def create_project(self, package_name: str, app_name: str) -> bool:
        """Create a new Android project with Jetpack Compose."""
        try:
            # Use Android SDK command line tools if available
            # Otherwise, create manually
            
            # Project structure
            dirs = [
                f"app/src/main/java/{package_name.replace('.', '/')}",
                "app/src/main/res/values",
                "app/src/main/res/layout",
                "app/src/main/res/drawable",
                "gradle/wrapper",
            ]
            
            for d in dirs:
                (self.project_dir / d).mkdir(parents=True, exist_ok=True)
            
            # Create build files
            self._write_build_gradle(project_dir)
            self._write_settings_gradle(app_name)
            self._write_gradle_wrapper()
            
            return True
        except Exception as e:
            print(f"Error creating project: {e}")
            return False
    
    def build_apk(self, variant: str = "debug") -> Optional[Path]:
        """Build APK using Gradle wrapper."""
        try:
            result = subprocess.run(
                ["./gradlew", f"assemble{variant.capitalize()}"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode != 0:
                print(f"Build failed: {result.stderr}")
                return None
            
            # Find APK
            apk_dir = self.project_dir / f"app/build/outputs/apk/{variant}"
            apks = list(apk_dir.glob("*.apk"))
            return apks[0] if apks else None
            
        except subprocess.TimeoutExpired:
            print("Build timed out after 5 minutes")
            return None
        except Exception as e:
            print(f"Build error: {e}")
            return None
    
    def lint(self) -> bool:
        """Run Android lint checks."""
        try:
            result = subprocess.run(
                ["./gradlew", "lint"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Lint error: {e}")
            return False
    
    def test(self) -> bool:
        """Run unit tests."""
        try:
            result = subprocess.run(
                ["./gradlew", "test"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Test error: {e}")
            return False
    
    def _write_build_gradle(self, project_dir: Path):
        """Write app-level build.gradle.kts."""
        content = '''plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.voicebridge"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.voicebridge"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.10"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation(platform("androidx.compose:compose-bom:2024.02.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    
    // WebSocket
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    
    // Testing
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
}
'''
        (project_dir / "app" / "build.gradle.kts").write_text(content)
    
    def _write_settings_gradle(self, app_name: str):
        """Write project-level settings.gradle.kts."""
        content = f'''pluginManagement {{
    repositories {{
        google()
        mavenCentral()
        gradlePluginPortal()
    }}
}}
dependencyResolutionManagement {{
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {{
        google()
        mavenCentral()
    }}
}}

rootProject.name = "{app_name}"
include(":app")
'''
        (self.project_dir / "settings.gradle.kts").write_text(content)
    
    def _write_gradle_wrapper(self):
        """Write Gradle wrapper files."""
        # gradle-wrapper.properties
        wrapper_dir = self.project_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        
        wrapper_props = '''distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
'''
        (wrapper_dir / "gradle-wrapper.properties").write_text(wrapper_props)


def main():
    """CLI for Android dev agent."""
    import argparse
    parser = argparse.ArgumentParser(description="Android Developer Agent")
    parser.add_argument("project", help="Project directory")
    parser.add_argument("--create", help="Create new project with package name")
    parser.add_argument("--build", action="store_true", help="Build APK")
    parser.add_argument("--lint", action="store_true", help="Run lint")
    parser.add_argument("--test", action="store_true", help="Run tests")
    args = parser.parse_args()
    
    project_dir = Path(args.project)
    agent = AndroidDevAgent(project_dir)
    
    if args.create:
        success = agent.create_project(args.create, "VoiceBridge")
        print(f"Project creation: {'OK' if success else 'FAILED'}")
    
    if args.build:
        apk = agent.build_apk()
        print(f"APK: {apk}" if apk else "Build FAILED")
    
    if args.lint:
        success = agent.lint()
        print(f"Lint: {'OK' if success else 'FAILED'}")
    
    if args.test:
        success = agent.test()
        print(f"Tests: {'OK' if success else 'FAILED'}")


if __name__ == "__main__":
    main()
