// 推荐打分：球面距离（Haversine）+ 距离打分。
// 等价实现见 backend/app/core/compute.py（未编译时的 Python 回退），改一处要同步另一处。

#include "qh_core.hpp"

#include <algorithm>
#include <cmath>

namespace qh {

namespace {

constexpr double kEarthRadiusKm = 6371.0088;
constexpr double kPi = 3.14159265358979323846;

double to_radians(double degrees) { return degrees * kPi / 180.0; }

}  // namespace

double haversine_km(double lat1, double lng1, double lat2, double lng2) {
    const double dlat = to_radians(lat2 - lat1);
    const double dlng = to_radians(lng2 - lng1);
    const double a = std::sin(dlat / 2) * std::sin(dlat / 2) +
                     std::cos(to_radians(lat1)) * std::cos(to_radians(lat2)) *
                         std::sin(dlng / 2) * std::sin(dlng / 2);
    // 对跖点附近 a 可能因浮点舍入略大于 1（std::asin 会静默得 NaN；
    // Python 回退的 math.asin 则抛异常）——clamp 保证两实现行为一致。
    return 2 * kEarthRadiusKm * std::asin(std::sqrt(std::min(1.0, a)));
}

double distance_score(double lat1, double lng1, double lat2, double lng2) {
    const double distance = haversine_km(lat1, lng1, lat2, lng2);
    return 100.0 / (1.0 + distance / 50.0);
}

}  // namespace qh
