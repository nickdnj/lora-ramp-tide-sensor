"""Build and run the C++ host tests (firmware/test/host) against the shared vectors,
so one `pytest` run covers both codecs. Skipped if no C++ compiler is present."""

import shutil
import subprocess

import pytest

from conftest import ROOT

CXX = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")


@pytest.mark.skipif(CXX is None, reason="no C++ compiler on PATH")
def test_cpp_core_passes_shared_vectors(tmp_path):
    core = ROOT / "firmware" / "lib" / "tidecore" / "src"
    host = ROOT / "firmware" / "test" / "host"
    exe = tmp_path / "test_tidecore"
    srcs = [str(core / f) for f in ("payload.cpp", "stats.cpp", "power_logic.cpp", "cycle.cpp")]
    subprocess.run([CXX, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-pedantic", f"-I{core}", f"-I{host}",
                    *srcs, str(host / "test_tidecore.cpp"), "-o", str(exe)], check=True, capture_output=True)
    r = subprocess.run([str(exe), str(ROOT / "tests" / "vectors")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert ", 0 failed" in r.stdout
