#!/usr/bin/env python3
"""Rebrand an upstream v2rayNG tree without breaking package-coupled behavior.

This is intentionally a fail-closed transformer.  If upstream changes one of the
package-coupled source locations that this script understands, it stops the CI
run instead of silently producing an APK with a partially changed package.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


OLD_PACKAGE = "com.v2ray.ang"
NEW_PACKAGE = "com.tools.unitconverter"
OLD_PACKAGE_PATH = OLD_PACKAGE.replace(".", "/")
NEW_PACKAGE_PATH = NEW_PACKAGE.replace(".", "/")
TEXT_SUFFIXES = {".kt", ".java", ".xml", ".kts", ".gradle", ".properties", ".pro"}

# Original Unit Converter visual identity.  These are Android VectorDrawables,
# so they stay crisp at every launcher density and do not need generated PNGs.
ICON_BACKGROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_unit_converter_background">#0F172A</color>
</resources>
"""

ICON_FOREGROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <!-- A compact conversion panel: two opposing arrows inside a measuring frame. -->
    <path
        android:fillColor="#E2E8F0"
        android:pathData="M28,31C24.69,31 22,33.69 22,37L22,71C22,74.31 24.69,77 28,77L80,77C83.31,77 86,74.31 86,71L86,37C86,33.69 83.31,31 80,31L28,31z" />
    <path
        android:fillColor="#16213A"
        android:pathData="M30,39L78,39L78,69L30,69z" />
    <path
        android:fillColor="#38BDF8"
        android:pathData="M36,46L59,46L59,41L70,50L59,59L59,54L36,54z" />
    <path
        android:fillColor="#A78BFA"
        android:pathData="M72,62L49,62L49,67L38,58L49,49L49,54L72,54z" />
    <path
        android:fillColor="#F8FAFC"
        android:pathData="M30,27L36,27L36,31L30,31zM42,27L46,27L46,31L42,31zM52,27L56,27L56,31L52,31zM62,27L66,27L66,31L62,31zM72,27L78,27L78,31L72,31z" />
</vector>
"""

ICON_MONOCHROME_XML = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#FFFFFFFF"
        android:pathData="M28,31C24.69,31 22,33.69 22,37L22,71C22,74.31 24.69,77 28,77L80,77C83.31,77 86,74.31 86,71L86,37C86,33.69 83.31,31 80,31L28,31zM36,46L59,46L59,41L70,50L59,59L59,54L36,54zM72,62L49,62L49,67L38,58L49,49L49,54L72,54z" />
</vector>
"""

ICON_LEGACY_XML = """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@color/ic_unit_converter_background" />
    <item android:drawable="@drawable/ic_unit_converter_foreground" />
</layer-list>
"""

ICON_ADAPTIVE_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_unit_converter_background" />
    <foreground android:drawable="@drawable/ic_unit_converter_foreground" />
    <monochrome android:drawable="@drawable/ic_unit_converter_monochrome" />
</adaptive-icon>
"""

ICON_BANNER_XML = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="320dp"
    android:height="180dp"
    android:viewportWidth="320"
    android:viewportHeight="180">
    <path android:fillColor="#0F172A" android:pathData="M0,0L320,0L320,180L0,180z" />
    <path android:fillColor="#1E293B" android:pathData="M44,42C34.06,42 26,50.06 26,60L26,120C26,129.94 34.06,138 44,138L156,138C165.94,138 174,129.94 174,120L174,60C174,50.06 165.94,42 156,42L44,42z" />
    <path android:fillColor="#E2E8F0" android:pathData="M51,55L149,55L149,125L51,125z" />
    <path android:fillColor="#16213A" android:pathData="M62,67L138,67L138,113L62,113z" />
    <path android:fillColor="#38BDF8" android:pathData="M73,75L111,75L111,67L128,81L111,95L111,87L73,87z" />
    <path android:fillColor="#A78BFA" android:pathData="M127,105L89,105L89,113L72,99L89,85L89,93L127,93z" />
    <path android:fillColor="#38BDF8" android:pathData="M202,55L294,55L294,64L202,64zM202,85L270,85L270,94L202,94z" />
    <path android:fillColor="#A78BFA" android:pathData="M202,115L294,115L294,124L202,124z" />
</vector>
"""

ICON_STATUS_XML = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp"
    android:height="24dp"
    android:viewportWidth="24"
    android:viewportHeight="24">
    <path
        android:fillColor="#FFFFFFFF"
        android:pathData="M4,7L14,7L14,4L20,9L14,14L14,11L4,11zM20,17L10,17L10,20L4,15L10,10L10,13L20,13z" />
</vector>
"""


def fail(message: str) -> None:
    raise RuntimeError(message)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, help="root of a checked-out 2dust/v2rayNG source tree")
    parser.add_argument(
        "--release-repository",
        required=True,
        metavar="OWNER/REPOSITORY",
        help="GitHub repository whose Releases the rebranded app must check",
    )
    return parser.parse_args()


def validate_release_repository(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        fail("--release-repository must have the form OWNER/REPOSITORY")
    return value


def replace_text(path: Path, old: str, new: str) -> bool:
    content = path.read_text(encoding="utf-8")
    if old not in content:
        return False
    path.write_text(content.replace(old, new), encoding="utf-8", newline="\n")
    return True


def replace_once(path: Path, old: str, new: str, description: str) -> None:
    content = path.read_text(encoding="utf-8")
    occurrences = content.count(old)
    if occurrences != 1:
        fail(f"{description}: expected exactly one match in {path}, found {occurrences}")
    path.write_text(content.replace(old, new), encoding="utf-8", newline="\n")


def write_resource(path: Path, content: str) -> None:
    if path.exists():
        fail(f"refusing to overwrite existing brand resource: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def text_files(app_dir: Path) -> list[Path]:
    return sorted(path for path in app_dir.rglob("*") if path.is_file() and path.suffix in TEXT_SUFFIXES)


def move_package_directories(app_dir: Path) -> None:
    for source_set in ("main", "test", "androidTest"):
        old_dir = app_dir / "src" / source_set / "java" / Path(*OLD_PACKAGE.split("."))
        if not old_dir.exists():
            continue
        new_dir = app_dir / "src" / source_set / "java" / Path(*NEW_PACKAGE.split("."))
        if new_dir.exists():
            fail(f"target package directory already exists: {new_dir}")
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_dir), str(new_dir))


def assert_no_old_package(app_dir: Path, native_build_script: Path) -> None:
    offenders: list[Path] = []
    for path in [*text_files(app_dir), native_build_script]:
        content = path.read_text(encoding="utf-8")
        if OLD_PACKAGE in content or OLD_PACKAGE_PATH in content:
            offenders.append(path)
    if offenders:
        paths = "\n".join(f"  - {path}" for path in offenders)
        fail(f"old package reference remains in functional source:\n{paths}")


def rebrand_visible_strings(app_dir: Path) -> None:
    app_name_pattern = re.compile(
        r'(<(?:string|item)\b[^>]*\bname="app_name"[^>]*>).*?(</(?:string|item)>)',
        re.DOTALL,
    )
    changed_app_names = 0
    for path in sorted((app_dir / "src").glob("**/res/values*/strings.xml")):
        content = path.read_text(encoding="utf-8")
        updated, replacements = app_name_pattern.subn(r"\1Unit Converter\2", content)
        if replacements:
            changed_app_names += replacements
            # Replace the remaining user-visible product references such as the
            # service notification channel and Quick Settings tile, but retain
            # protocol URIs and developer-facing HTTP user-agent text elsewhere.
            updated = updated.replace("v2rayNG", "Unit Converter")
            path.write_text(updated, encoding="utf-8", newline="\n")
    if changed_app_names == 0:
        fail("no app_name resource was found for the Unit Converter rebrand")


def add_original_icon_resources(app_dir: Path) -> None:
    main_res = app_dir / "src" / "main" / "res"
    write_resource(main_res / "values" / "ic_unit_converter_background.xml", ICON_BACKGROUND_XML)
    write_resource(main_res / "drawable" / "ic_unit_converter_foreground.xml", ICON_FOREGROUND_XML)
    write_resource(main_res / "drawable" / "ic_unit_converter_monochrome.xml", ICON_MONOCHROME_XML)
    write_resource(main_res / "drawable" / "ic_unit_converter_banner.xml", ICON_BANNER_XML)
    write_resource(main_res / "drawable" / "ic_unit_converter_status.xml", ICON_STATUS_XML)
    write_resource(main_res / "mipmap-anydpi" / "ic_unit_converter.xml", ICON_LEGACY_XML)
    write_resource(main_res / "mipmap-anydpi-v26" / "ic_unit_converter.xml", ICON_ADAPTIVE_XML)


def rebrand_icon_references(app_dir: Path) -> None:
    manifest = app_dir / "src" / "main" / "AndroidManifest.xml"
    replace_once(
        manifest,
        'android:banner="@mipmap/ic_banner"',
        'android:banner="@drawable/ic_unit_converter_banner"',
        "application banner reference",
    )
    if not replace_text(manifest, 'android:icon="@mipmap/ic_launcher"', 'android:icon="@mipmap/ic_unit_converter"'):
        fail("no launcher icon reference was found in AndroidManifest.xml")
    replace_once(
        manifest,
        'android:icon="@drawable/ic_stat_name"',
        'android:icon="@drawable/ic_unit_converter_status"',
        "Quick Settings tile icon reference",
    )

    status_references = 0
    for path in text_files(app_dir):
        status_references += int(
            replace_text(path, "R.drawable.ic_stat_name", "R.drawable.ic_unit_converter_status")
        )
    if status_references == 0:
        fail("no notification status icon reference was found")


def main() -> int:
    args = parse_arguments()
    source_root = args.source_root.resolve()
    release_repository = validate_release_repository(args.release_repository)
    app_dir = source_root / "V2rayNG" / "app"
    native_build_script = source_root / "compile-hevtun.sh"

    if not (app_dir / "build.gradle.kts").is_file() or not native_build_script.is_file():
        fail("source_root does not look like the expected v2rayNG checkout")

    # Change source packages, imports, Gradle namespace/applicationId, shortcut target
    # classes, and package-scoped intent extras together.  Altering only applicationId
    # leaves those parts pointing at com.v2ray.ang.
    replacements = 0
    for path in text_files(app_dir):
        replacements += int(replace_text(path, OLD_PACKAGE, NEW_PACKAGE))
    replace_text(native_build_script, OLD_PACKAGE, NEW_PACKAGE)
    replace_once(
        native_build_script,
        OLD_PACKAGE_PATH,
        NEW_PACKAGE_PATH,
        "HEV JNI class package",
    )

    # Upstream uses the old application ID as an Xray-vs-v2fly feature switch.  This
    # build still downloads AndroidLibXrayLite, so package identity must not control
    # this behavior.  Without this patch, changing the ID enables a second HTTP
    # inbound and changes its port, which is the common 'changed package breaks
    # features' failure mode.
    old_is_xray = f'fun isXray(): Boolean = BuildConfig.APPLICATION_ID.startsWith("{NEW_PACKAGE}")'
    utils_file = app_dir / "src" / "main" / "java" / Path(*OLD_PACKAGE.split(".")) / "util" / "Utils.kt"
    replace_once(
        utils_file,
        old_is_xray,
        "fun isXray(): Boolean = true",
        "Xray core feature switch",
    )

    # The app's built-in updater must not offer the official com.v2ray.ang APK.
    # Repoint its GitHub release API and About links to the repository that runs this
    # workflow.  The official privacy-policy source remains attributed upstream.
    app_config = app_dir / "src" / "main" / "java" / Path(*OLD_PACKAGE.split(".")) / "AppConfig.kt"
    replace_once(
        app_config,
        'const val APP_URL = "$GITHUB_URL/2dust/v2rayNG"',
        f'const val APP_URL = "$GITHUB_URL/{release_repository}"',
        "application GitHub URL",
    )
    replace_once(
        app_config,
        'const val APP_API_URL = "https://api.github.com/repos/2dust/v2rayNG/releases"',
        f'const val APP_API_URL = "https://api.github.com/repos/{release_repository}/releases"',
        "application update API URL",
    )

    rebrand_visible_strings(app_dir)
    add_original_icon_resources(app_dir)
    rebrand_icon_references(app_dir)

    move_package_directories(app_dir)

    new_utils_file = app_dir / "src" / "main" / "java" / Path(*NEW_PACKAGE.split(".")) / "util" / "Utils.kt"
    new_app_config = app_dir / "src" / "main" / "java" / Path(*NEW_PACKAGE.split(".")) / "AppConfig.kt"
    main_res = app_dir / "src" / "main" / "res"
    manifest = app_dir / "src" / "main" / "AndroidManifest.xml"
    if "fun isXray(): Boolean = true" not in new_utils_file.read_text(encoding="utf-8"):
        fail("Xray core feature switch was not preserved")
    if release_repository not in new_app_config.read_text(encoding="utf-8"):
        fail("application update repository was not rewritten")
    if 'android:icon="@mipmap/ic_unit_converter"' not in manifest.read_text(encoding="utf-8"):
        fail("Unit Converter launcher icon was not wired into the manifest")
    if "Unit Converter" not in (main_res / "values" / "strings.xml").read_text(encoding="utf-8"):
        fail("Unit Converter display name was not written")
    for resource in (
        main_res / "mipmap-anydpi" / "ic_unit_converter.xml",
        main_res / "mipmap-anydpi-v26" / "ic_unit_converter.xml",
        main_res / "drawable" / "ic_unit_converter_foreground.xml",
        main_res / "drawable" / "ic_unit_converter_status.xml",
    ):
        if not resource.is_file():
            fail(f"missing Unit Converter icon resource: {resource}")

    assert_no_old_package(app_dir, native_build_script)
    print(f"Rebranded {source_root} to {NEW_PACKAGE}; changed {replacements} app files.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
