#!/usr/bin/env python3
"""
Mobile Developer Agent
Specialized agent for building Android and iOS applications.
Android: Kotlin, Jetpack Compose, Gradle
iOS: Swift, SwiftUI, Xcode (where applicable)

Note: Voice Bridge is Android-only (Tailscale + WebSocket limitations)
Other projects may support both platforms.
"""

import subprocess
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Tuple

ANDROID_HOME = Path.home() / "Android/Sdk"
GRADLE_WRAPPER = "./gradlew"
XCODE_BUILD = "/usr/bin/xcodebuild"


class MobileDevAgent:
    """Agent for mobile app development (Android + iOS where supported)."""
    
    def __init__(self, project_dir: Path, platforms: List[str] = None):
        """
        Args:
            project_dir: Project root directory
            platforms: List of platforms to support ["android", "ios"] or ["android"] only
        """
        self.project_dir = project_dir
        self.platforms = platforms or ["android"]
        
        # Android settings
        self.android_api = 34
        self.compile_sdk = 34
        self.min_sdk = 28
        self.target_sdk = 34
        
        # iOS settings (if applicable)
        self.ios_deployment_target = "15.0"
    
    # =========================================================================
    # ANDROID DEVELOPMENT
    # =========================================================================
    
    def create_android_project(self, package_name: str, app_name: str) -> bool:
        """Create a new Android project with Jetpack Compose."""
        try:
            dirs = [
                f"android/app/src/main/java/{package_name.replace('.', '/')}",
                "android/app/src/main/res/values",
                "android/app/src/main/res/layout",
                "android/app/src/main/res/drawable",
                "android/gradle/wrapper",
            ]
            
            for d in dirs:
                (self.project_dir / d).mkdir(parents=True, exist_ok=True)
            
            self._write_android_build_gradle(app_name)
            self._write_android_settings_gradle(app_name)
            self._write_android_gradle_wrapper()
            
            return True
        except Exception as e:
            print(f"Error creating Android project: {e}")
            return False
    
    def build_android_apk(self, variant: str = "debug") -> Optional[Path]:
        """Build Android APK using Gradle wrapper."""
        android_dir = self.project_dir / "android"
        if not android_dir.exists():
            print("Android directory not found")
            return None
        
        try:
            result = subprocess.run(
                ["./gradlew", f"assemble{variant.capitalize()}"],
                cwd=android_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
            )
            
            if result.returncode != 0:
                print(f"Android build failed: {result.stderr}")
                return None
            
            apk_dir = android_dir / f"app/build/outputs/apk/{variant}"
            apks = list(apk_dir.glob("*.apk"))
            return apks[0] if apks else None
            
        except subprocess.TimeoutExpired:
            print("Android build timed out")
            return None
        except Exception as e:
            print(f"Android build error: {e}")
            return None
    
    def android_lint(self) -> bool:
        """Run Android lint checks."""
        android_dir = self.project_dir / "android"
        try:
            result = subprocess.run(
                ["./gradlew", "lint"],
                cwd=android_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Android lint error: {e}")
            return False
    
    def android_test(self) -> bool:
        """Run Android unit tests."""
        android_dir = self.project_dir / "android"
        try:
            result = subprocess.run(
                ["./gradlew", "test"],
                cwd=android_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Android test error: {e}")
            return False
    
    def install_android_tools(self) -> bool:
        """Check/install required Android SDK tools."""
        tools_needed = [
            "sdkmanager",
            "adb",
            "emulator",
        ]
        
        missing = []
        for tool in tools_needed:
            result = subprocess.run(["which", tool], capture_output=True)
            if result.returncode != 0:
                missing.append(tool)
        
        if missing:
            print(f"Missing Android tools: {missing}")
            print("Install via: sdkmanager 'platform-tools' 'build-tools;34.0.0'")
            return False
        
        return True
    
    # =========================================================================
    # iOS DEVELOPMENT (if platform includes iOS)
    # =========================================================================
    
    def create_ios_project(self, bundle_id: str, app_name: str) -> bool:
        """Create a new iOS project with SwiftUI."""
        if "ios" not in self.platforms:
            print("iOS platform not enabled for this project")
            return False
        
        try:
            ios_dir = self.project_dir / "ios"
            ios_dir.mkdir(parents=True, exist_ok=True)
            
            # Create Xcode project structure
            project_name = app_name.replace(" ", "")
            (ios_dir / f"{project_name}.xcodeproj").mkdir(exist_ok=True)
            (ios_dir / f"{project_name}").mkdir(exist_ok=True)
            
            self._write_ios_project_file(project_name, bundle_id)
            self._write_ios_app_delegate(project_name)
            self._write_ios_swiftui_app(project_name)
            self._write_ios_info_plist(project_name, bundle_id)
            
            return True
        except Exception as e:
            print(f"Error creating iOS project: {e}")
            return False
    
    def build_ios_app(self, scheme: str = "Debug") -> bool:
        """Build iOS app using xcodebuild."""
        if "ios" not in self.platforms:
            print("iOS platform not enabled")
            return False
        
        ios_dir = self.project_dir / "ios"
        if not ios_dir.exists():
            print("iOS directory not found")
            return False
        
        try:
            result = subprocess.run(
                [
                    XCODE_BUILD,
                    "-project", str(ios_dir),
                    "-scheme", scheme,
                    "-configuration", scheme,
                    "build",
                ],
                cwd=ios_dir,
                capture_output=True,
                text=True,
                timeout=600,
            )
            
            return result.returncode == 0
        except Exception as e:
            print(f"iOS build error: {e}")
            return False
    
    def ios_simulator_test(self) -> bool:
        """Run iOS tests on simulator."""
        if "ios" not in self.platforms:
            return False
        
        ios_dir = self.project_dir / "ios"
        try:
            result = subprocess.run(
                [XCODE_BUILD, "test", "-project", str(ios_dir), "-destination", "platform=iOS Simulator,name=iPhone 15"],
                cwd=ios_dir,
                capture_output=True,
                text=True,
                timeout=600,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"iOS test error: {e}")
            return False
    
    # =========================================================================
    # CROSS-PLATFORM HELPERS
    # =========================================================================
    
    def validate_project(self) -> Dict[str, bool]:
        """Validate project structure for all enabled platforms."""
        results = {}
        
        if "android" in self.platforms:
            results["android_structure"] = (self.project_dir / "android" / "app" / "build.gradle.kts").exists()
            results["android_tools"] = self.install_android_tools()
        
        if "ios" in self.platforms:
            results["ios_structure"] = len(list((self.project_dir / "ios").glob("*.xcodeproj"))) > 0
            results["xcode_available"] = Path(XCODE_BUILD).exists()
        
        return results
    
    def get_status(self) -> str:
        """Get agent status summary."""
        lines = [
            f"Project: {self.project_dir}",
            f"Platforms: {', '.join(self.platforms)}",
        ]
        
        if "android" in self.platforms:
            android_dir = self.project_dir / "android"
            lines.append(f"Android dir exists: {android_dir.exists()}")
            if android_dir.exists():
                lines.append(f"Gradle wrapper: {(android_dir / 'gradlew').exists()}")
        
        if "ios" in self.platforms:
            ios_dir = self.project_dir / "ios"
            lines.append(f"iOS dir exists: {ios_dir.exists()}")
        
        return "\n".join(lines)
    
    # =========================================================================
    # PRIVATE: Android file generators
    # =========================================================================
    
    def _write_android_build_gradle(self, app_name: str):
        """Write Android app-level build.gradle.kts."""
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
        build_file = self.project_dir / "android" / "app" / "build.gradle.kts"
        build_file.parent.mkdir(parents=True, exist_ok=True)
        build_file.write_text(content)
    
    def _write_android_settings_gradle(self, app_name: str):
        """Write Android project-level settings.gradle.kts."""
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
        (self.project_dir / "android" / "settings.gradle.kts").write_text(content)
    
    def _write_android_gradle_wrapper(self):
        """Write Android Gradle wrapper files."""
        wrapper_dir = self.project_dir / "android" / "gradle" / "wrapper"
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
    
    # =========================================================================
    # PRIVATE: iOS file generators
    # =========================================================================
    
    def _write_ios_project_file(self, project_name: str, bundle_id: str):
        """Write iOS project.pbxproj (simplified)."""
        # Xcode project files are complex; in practice use `xcodebuild` or Swift Package Manager
        pass
    
    def _write_ios_app_delegate(self, project_name: str):
        """Write iOS AppDelegate.swift."""
        content = f'''import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {{
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {{
        return true
    }}
}}
'''
        app_dir = self.project_dir / "ios" / project_name
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "AppDelegate.swift").write_text(content)
    
    def _write_ios_swiftui_app(self, project_name: str):
        """Write iOS SwiftUI ContentView."""
        content = '''import SwiftUI

@main
struct VoiceBridgeApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        Text("Voice Bridge")
            .font(.largeTitle)
    }
}
'''
        app_dir = self.project_dir / "ios" / project_name
        (app_dir / "ContentView.swift").write_text(content)
    
    def _write_ios_info_plist(self, project_name: str, bundle_id: str):
        """Write iOS Info.plist."""
        content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>{bundle_id}</string>
    <key>CFBundleName</key>
    <string>{project_name}</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
</dict>
</plist>
'''
        app_dir = self.project_dir / "ios" / project_name
        (app_dir / "Info.plist").write_text(content)


def main():
    """CLI for mobile dev agent."""
    import argparse
    parser = argparse.ArgumentParser(description="Mobile Developer Agent")
    parser.add_argument("project", help="Project directory")
    parser.add_argument("--platforms", nargs="+", default=["android"], 
                        choices=["android", "ios"],
                        help="Platforms to support")
    parser.add_argument("--create-android", metavar="PACKAGE", 
                        help="Create Android project with package name")
    parser.add_argument("--create-ios", metavar="BUNDLE_ID",
                        help="Create iOS project with bundle ID")
    parser.add_argument("--build-android", action="store_true")
    parser.add_argument("--build-ios", action="store_true")
    parser.add_argument("--lint", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    
    project_dir = Path(args.project)
    agent = MobileDevAgent(project_dir, platforms=args.platforms)
    
    if args.status:
        print(agent.get_status())
    
    if args.validate:
        results = agent.validate_project()
        for check, passed in results.items():
            status = "✓" if passed else "✗"
            print(f"{status} {check}")
    
    if args.create_android:
        success = agent.create_android_project(args.create_android, "App")
        print(f"Android project: {'OK' if success else 'FAILED'}")
    
    if args.create_ios:
        success = agent.create_ios_project(args.create_ios, "App")
        print(f"iOS project: {'OK' if success else 'FAILED'}")
    
    if args.build_android:
        apk = agent.build_android_apk()
        print(f"APK: {apk}" if apk else "Android build FAILED")
    
    if args.build_ios:
        success = agent.build_ios_app()
        print(f"iOS build: {'OK' if success else 'FAILED'}")
    
    if args.lint:
        success = agent.android_lint()
        print(f"Android lint: {'OK' if success else 'FAILED'}")
    
    if args.test:
        success = agent.android_test()
        print(f"Android tests: {'OK' if success else 'FAILED'}")


if __name__ == "__main__":
    main()
