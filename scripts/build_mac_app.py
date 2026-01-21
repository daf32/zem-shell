import os
import stat
import shutil
from pathlib import Path

def create_mac_app():
    project_root = Path(__file__).parent.parent.resolve()
    dist_dir = project_root / "dist"
    app_name = "Axonix.app"
    app_path = dist_dir / app_name
    
    print(f"🏗  Building {app_name} in {dist_dir}...")

    # 1. Clean previous build
    if app_path.exists():
        shutil.rmtree(app_path)
    
    # 2. Create Directory Structure
    contents_dir = app_path / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # 3. Create Info.plist
    # Define the app as an application that runs in the background (LSUIElement)
    # or a normal app. Since it launches Terminal, it's basically a launcher.
    info_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Axonix</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.axonix.shell</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Axonix</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.10</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""
    with open(contents_dir / "Info.plist", "w") as f:
        f.write(info_plist)

    # 4. Create the Launcher Script (The Executable)
    # Using AppleScript here is the most robust way to interact with Terminal.app
    # We use 'do script' to launch our specific command in a new window.
    
    launcher_script = f"""#!/bin/bash
# Launcher for Axonix Shell
# Determines the project directory and runs 'uv run ax' in a NEW Terminal window.

PROJECT_DIR="{project_root}"

# AppleScript to launch Terminal with the command
osascript <<EOF
tell application "Terminal"
    activate
    do script "cd " & check with command " & quoted form of "{project_root}" & " && uv run ax; exit"
end tell
EOF

# Close this launcher app so it doesn't stay in the dock
killall Axonix
"""
    
    # Corrected AppleScript logic for robust path handling
    launcher_content = f"""#!/bin/bash
PROJECT_DIR="{project_root}"

osascript -e 'tell application "Terminal" to do script "cd \\"'$PROJECT_DIR'\\" && clear && uv run ax"'
osascript -e 'tell application "Terminal" to activate'
"""

    executable_path = macos_dir / "Axonix"
    with open(executable_path, "w") as f:
        f.write(launcher_content)

    # Make executable
    st = os.stat(executable_path)
    os.chmod(executable_path, st.st_mode | stat.S_IEXEC)

    print(f"✅ App created at: {app_path}")
    print("👉 You can drag this to your Applications folder or Dock.")

if __name__ == "__main__":
    create_mac_app()
