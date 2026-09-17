"""
ShadowLink Build Script.
Builds the standalone Windows executable using PyInstaller with full icon embedding,
data assets bundling, and OneDrive permissions handling.
"""

import os
from pathlib import Path
import subprocess
import sys

import config


def main() -> None:
    project_root = Path(__file__).resolve().parent
    ico_path = project_root / "icon.ico"
    png_path = project_root / "icon.png"

    print("=" * 60)
    print(f" ShadowLink v{config.APP_VERSION} Windows Build Script")
    print("=" * 60)

    # 1. Verify Icon Assets
    if not ico_path.exists():
        ref_ico = project_root / "reference_kotlin" / "icon.ico"
        if ref_ico.exists():
            import shutil
            shutil.copy2(ref_ico, ico_path)
            print(f"[+] Copied icon.ico from reference_kotlin to root")
        else:
            print(f"[-] ERROR: icon.ico not found at {ico_path}")
            sys.exit(1)

    if not png_path.exists():
        try:
            from PySide6.QtGui import QGuiApplication, QIcon
            app = QGuiApplication.instance() or QGuiApplication(sys.argv)
            icon = QIcon(str(ico_path))
            pix = icon.pixmap(256, 256)
            pix.save(str(png_path), "PNG")
            print(f"[+] Generated 256x256 icon.png from icon.ico")
        except Exception as e:
            print(f"[!] Warning: Could not generate icon.png: {e}")

    def remove_readonly(func, path, exc_info):
        import stat
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    def safe_clean(path_to_clean: Path) -> None:
        if path_to_clean.exists():
            import shutil
            shutil.rmtree(path_to_clean, onexc=remove_readonly)
            print(f"[+] Cleaned directory: {path_to_clean.name}")

    # 2. Safely clean old build and dist directories
    safe_clean(project_root / "dist" / "ShadowLink")
    safe_clean(project_root / "build" / "ShadowLink")

    # 3. Execute PyInstaller
    spec_path = project_root / "ShadowLink.spec"
    print(f"[*] Running PyInstaller with {spec_path.name}...")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(spec_path),
    ]

    result = subprocess.run(cmd, cwd=str(project_root))
    if result.returncode != 0:
        print("[-] Build failed!")
        sys.exit(result.returncode)

    # 4. Verify Built Executable
    dist_exe = project_root / "dist" / "ShadowLink" / "ShadowLink.exe"
    if not dist_exe.exists():
        dist_exe = project_root / "dist" / "ShadowLink.exe"

    if dist_exe.exists():
        print(f"\n[+] SUCCESS: Built executable created for ShadowLink v{config.APP_VERSION} at:")
        print(f"    {dist_exe} ({dist_exe.stat().st_size:,} bytes)")

        # Also update installed C:\ShadowLink\ShadowLink.exe if directory exists
        c_shadowlink = Path("C:/ShadowLink")
        if c_shadowlink.exists():
            dest = c_shadowlink / "ShadowLink.exe"
            try:
                import shutil
                shutil.copy2(dist_exe, dest)
                print(f"[+] Installed updated build to: {dest}")
            except Exception as copy_err:
                print(f"[!] Note: Could not copy to {dest} (process may be running): {copy_err}")

        try:
            import pefile
            pe = pefile.PE(str(dist_exe))
            has_icon = any(
                entry.id == pefile.RESOURCE_TYPE['RT_GROUP_ICON']
                for entry in getattr(pe, 'DIRECTORY_ENTRY_RESOURCE', pefile.Structure()).entries
            )
            print(f"[+] Verified: RT_GROUP_ICON embedded in EXE binary: {has_icon}")
        except Exception:
            pass

        print("\nNote on Windows Explorer Icon Caching:")
        print("  Windows aggressively caches .exe icons in its shell database.")
        print("  If File Explorer displays a generic icon for ShadowLink.exe,")
        print("  simply rename the file or copy it to your Desktop, and Windows")
        print("  will immediately refresh and display the custom ROG wings emblem.")
    else:
        print("[-] ERROR: Output executable not found in dist/")
        sys.exit(1)


if __name__ == "__main__":
    main()
