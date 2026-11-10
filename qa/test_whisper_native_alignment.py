#!/usr/bin/env python3
"""Exercise 16 KiB linker settings inherited by fetched Whisper/GGML targets.

This uses tiny host-compiled ELF shared libraries in place of whisper.cpp. It
checks CMake option propagation, not an NDK build or Android runtime behavior.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from audit_native_alignment import PAGE_SIZE, inspect_elf


ROOT = Path(__file__).resolve().parents[1]
CMAKE_SOURCE = ROOT / "app/src/main/cpp"


class WhisperNativeAlignmentTests(unittest.TestCase):
    def test_android_link_options_reach_fetched_shared_targets(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("Host ELF surrogate requires Linux")
        cmake = os.environ.get("WAEX_CMAKE") or shutil.which("cmake")
        self.assertIsNotNone(cmake, "CMake is required for native linker QA")
        self.assertIsNotNone(shutil.which("cc"), "A C compiler is required for native linker QA")

        with tempfile.TemporaryDirectory(prefix="waex_whisper_link_") as tmp:
            tmp_path = Path(tmp)
            fake_whisper = tmp_path / "whisper"
            fake_whisper.mkdir()
            (fake_whisper / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.22)\n"
                "project(whisper_test C)\n"
                "add_library(ggml SHARED probe.c)\n"
                "add_library(whisper SHARED probe.c)\n"
                "add_subdirectory(backends)\n",
                encoding="utf-8",
            )
            (fake_whisper / "backends").mkdir()
            (fake_whisper / "backends/CMakeLists.txt").write_text(
                "add_library(ggml-cpu-android_armv8_0_1 SHARED ../probe.c)\n",
                encoding="utf-8",
            )
            (fake_whisper / "probe.c").write_text(
                "int waex_page_alignment_probe(void) { return 7; }\n", encoding="utf-8"
            )

            def build(fake_android):
                name = "android" if fake_android else "control"
                output = tmp_path / name
                commands = [
                    [cmake, "-S", str(CMAKE_SOURCE), "-B", str(output),
                     "-G", "Unix Makefiles",
                     "-DFETCHCONTENT_SOURCE_DIR_WHISPER=" + str(fake_whisper),
                     "-DANDROID=" + ("ON" if fake_android else "OFF")],
                    [cmake, "--build", str(output), "--target", "ggml", "whisper",
                     "ggml-cpu-android_armv8_0_1", "-j", "2"],
                ]
                for command in commands:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                    self.assertEqual(0, result.returncode,
                                     f"{' '.join(command)}\n{result.stdout}\n{result.stderr}")
                libraries = [output / "_deps/whisper-build/libggml.so",
                             output / "_deps/whisper-build/libwhisper.so",
                             output / "_deps/whisper-build/backends/libggml-cpu-android_armv8_0_1.so"]
                for library in libraries:
                    self.assertTrue(library.is_file(), f"Missing linked library: {library}")
                if fake_android:
                    # The app-owned JNI target must receive the same flags as
                    # fetched targets, although this host fixture does not compile JNI.
                    link = (output / "CMakeFiles/waexwhisper.dir/link.txt").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("-Wl,-z,max-page-size=16384", link)
                    self.assertIn("-Wl,-z,common-page-size=16384", link)
                return [inspect_elf(library.read_bytes()) for library in libraries]

            control = build(fake_android=False)
            self.assertTrue(all("ELF_LOAD_ALIGNMENT_BELOW_16K" in item["issues"]
                                for item in control),
                            "Control must reproduce 4 KiB host linker alignment")

            candidate = build(fake_android=True)
            for library in candidate:
                self.assertEqual([], library["issues"])
                self.assertTrue(all(segment["alignment"] >= PAGE_SIZE
                                    for segment in library["load_segments"]))


if __name__ == "__main__":
    unittest.main()
