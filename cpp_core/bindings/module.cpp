// pybind11 绑定：把 C++ 计算核心暴露为 Python 模块 qh_core。
// 构建：make build-core（产物输出到 backend/qh_core.<ext>，Python 侧自动优先使用）。

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "qh_core.hpp"

namespace py = pybind11;

PYBIND11_MODULE(qh_core, m) {
    m.doc() = "青海平台 C++ 计算核心（距离 / 推荐打分 / 行程选点打分）";
    m.def("haversine_km", &qh::haversine_km, py::arg("lat1"), py::arg("lng1"), py::arg("lat2"),
          py::arg("lng2"), "两点间大圆距离（公里）");
    m.def("distance_score", &qh::distance_score, py::arg("lat1"), py::arg("lng1"),
          py::arg("lat2"), py::arg("lng2"), "基于距离的推荐打分（0-100，越近越高）");
    m.def("planning_score", &qh::planning_score, py::arg("name"), py::arg("city"),
          py::arg("keyword"), "行程选点的偏好相关性打分（0-100）");
    m.def("planning_scores", &qh::planning_scores, py::arg("names"), py::arg("cities"),
          py::arg("keyword"), "planning_score 的批量版本（返回等长分数列表）");
    m.def("path_length_km", &qh::path_length_km, py::arg("points"),
          "路径总里程（公里）：[(lat, lng), ...] 按顺序相邻累加");
}
