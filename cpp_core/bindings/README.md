# pybind11 绑定层

`module.cpp` 把 C++ 计算核心暴露为 Python 模块 **`qh_core`**（当前提供
`haversine_km` 与 `distance_score`）。

## 构建方式

```bash
make build-core          # 仓库根目录；等价于 cd backend && uv run python ../cpp_core/build.py
```

- 需要：带开发头文件的 Python（uv 管理的 Python 满足；**Microsoft Store 版缺头文件，编不过**）、
  pybind11（`uv` 依赖，已加入）与 CMake + MinGW make（w64devkit 提供）。
- 产物输出到 `backend/qh_core.<平台扩展名>`，`uvicorn` / `pytest` 在其工作目录可直接 import。
- **未编译时**：`backend/app/core/compute.py` 自动回退到等价的 Python 实现，
  业务代码只调封装层，CI 不需要编译器。

## 业务代码约定

业务模块**只调用 `app/core/compute.py`**，不要直接 `import qh_core`——
这样未编译的机器（含 CI）也能得到正确结果，两种实现由封装层自动切换。
