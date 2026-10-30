// 路线几何：停靠点路径总里程（相邻点大圆距离累加）。
// 等价实现见 backend/app/core/compute.py（未编译时的 Python 回退），改一处要同步另一处。

#include "qh_core.hpp"

#include <cstddef>

namespace qh {

double path_length_km(const std::vector<std::pair<double, double>>& points) {
    double total = 0.0;
    for (std::size_t index = 1; index < points.size(); ++index) {
        total += haversine_km(points[index - 1].first, points[index - 1].second,
                              points[index].first, points[index].second);
    }
    return total;
}

}  // namespace qh
