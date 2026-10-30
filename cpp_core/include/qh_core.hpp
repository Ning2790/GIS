// 计算核心对外接口。
//
// 当前提供（路线规划 / 风险评估后续在此扩展）：
//   - haversine_km：两点间大圆距离（公里）
//   - distance_score：基于距离的推荐打分（0-100，越近越高）
//   - planning_score / planning_scores：行程选点的偏好相关性打分（0-100）
//   - path_length_km：停靠点路径总里程（相邻点大圆距离累加）

#pragma once

#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace qh {

/// 两点间大圆距离（Haversine 公式），单位：公里。
double haversine_km(double lat1, double lng1, double lat2, double lng2);

/// 基于距离的推荐打分（0-100）：50 公里半程衰减。
double distance_score(double lat1, double lng1, double lat2, double lng2);

/// 行程选点的偏好相关性打分（0-100）：
/// 偏好为空 → 0；与名称完全相同 → 100；名称包含偏好 → 70 + 覆盖度 × 20；
/// 偏好（整句）提到景点名 → 65；城市包含偏好 → 60；否则 0。
double planning_score(const std::string& name, const std::string& city,
                      const std::string& keyword);

/// 路径总里程（公里）：按数组顺序对相邻点做 Haversine 累加；少于两个点返回 0。
double path_length_km(const std::vector<std::pair<double, double>>& points);

/// planning_score 的批量版本（names / cities 一一对应，长度不一致抛 invalid_argument）。
std::vector<double> planning_scores(const std::vector<std::string>& names,
                                    const std::vector<std::string>& cities,
                                    const std::string& keyword);

}  // namespace qh
