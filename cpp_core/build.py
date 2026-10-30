"""构建 C++ 计算核心（pybind11 扩展 qh_core）。

用法（仓库根目录）：
    make build-core

产物：backend/qh_core.<平台扩展名>；Python 侧 import 成功即自动优先使用
（封装见 backend/app/core/compute.py），未编译时自动回退到等价 Python 实现，
CI 与未装编译器的机器不受影响。
"""

import subprocess
import sys
from pathlib import Path

import pybind11

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"


def main() -> None:
    subprocess.run(
        [
            "cmake",
            "-S",
            str(ROOT),
            "-B",
            str(ROOT / "build"),
            # Ninja 而不是 MinGW Makefiles：mingw32-make 处理不了中文路径（仓库目录含中文）
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-Dpybind11_DIR={pybind11.get_cmake_dir()}",
            f"-DPython_EXECUTABLE={sys.executable}",
        ],
        check=True,
    )
    subprocess.run(["cmake", "--build", str(ROOT / "build")], check=True)
    built = sorted(BACKEND.glob("qh_core*"))
    print("构建完成：" + (", ".join(path.name for path in built) or "（未找到产物，请检查输出目录）"))


if __name__ == "__main__":
    main()
