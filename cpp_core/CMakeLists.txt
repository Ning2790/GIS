# C++ 计算核心（路线规划 / 风险评估 / 推荐打分）
#
# 当前实现：距离计算（Haversine）、基于距离的推荐打分、行程选点打分与路径总里程，
# 经 pybind11 暴露为 Python 模块 qh_core。
#
# 构建：make build-core（等价于在 backend 目录执行 uv run python ../cpp_core/build.py）
# 说明：编译需要带开发头文件的 Python（uv 管理的 Python 满足）与 pybind11（uv 依赖）。
#       未编译时 Python 侧自动回退到等价实现（backend/app/core/compute.py），CI 不受影响。

cmake_minimum_required(VERSION 3.20)
project(qh_cpp_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(qh_cpp_core STATIC
    src/recommend.cpp
    src/planning.cpp
    src/route.cpp
)
target_include_directories(qh_cpp_core PUBLIC include)

# ---- pybind11 绑定模块 ----
find_package(pybind11 CONFIG REQUIRED)
pybind11_add_module(qh_core bindings/module.cpp)
target_link_libraries(qh_core PRIVATE qh_cpp_core)

# 产物直接输出到 backend/：uvicorn / pytest 的工作目录可直接 import qh_core
set_target_properties(qh_core PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../backend"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../backend"
)
