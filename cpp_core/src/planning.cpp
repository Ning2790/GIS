// 行程选点打分：按自由文本偏好给候选景点打相关性分。
// 等价实现见 backend/app/core/compute.py（未编译时的 Python 回退），改一处要同步另一处。

#include "qh_core.hpp"

#include <cstddef>

namespace qh {

namespace {

/// UTF-8 字符数（码点数）：非连续字节（0b10xxxxxx）的个数。
std::size_t utf8_length(const std::string& text) {
    std::size_t count = 0;
    for (unsigned char byte : text) {
        if ((byte & 0xC0) != 0x80) {
            ++count;
        }
    }
    return count;
}

/// needle 是否是 haystack 的子串（UTF-8 字节子串与码点子串等价，可直接用 find）。
bool contains(const std::string& haystack, const std::string& needle) {
    return haystack.find(needle) != std::string::npos;
}

}  // namespace

double planning_score(const std::string& name, const std::string& city,
                      const std::string& keyword) {
    if (keyword.empty()) {
        return 0.0;
    }
    if (!name.empty()) {
        if (name == keyword) {
            return 100.0;
        }
        if (contains(name, keyword)) {
            // 偏好是名称的一部分：越接近全名分越高（70 起，随覆盖度上浮，封顶 90）
            const std::size_t name_length = utf8_length(name);
            const double coverage =
                name_length == 0
                    ? 1.0
                    : static_cast<double>(utf8_length(keyword)) / static_cast<double>(name_length);
            return 70.0 + 20.0 * coverage;
        }
        if (contains(keyword, name)) {
            // 偏好是一整句话、其中提到景点全名
            return 65.0;
        }
    }
    if (!city.empty() && contains(city, keyword)) {
        return 60.0;
    }
    return 0.0;
}

std::vector<double> planning_scores(const std::vector<std::string>& names,
                                    const std::vector<std::string>& cities,
                                    const std::string& keyword) {
    if (names.size() != cities.size()) {
        throw std::invalid_argument("planning_scores: names 与 cities 长度必须一致");
    }
    std::vector<double> scores;
    scores.reserve(names.size());
    for (std::size_t index = 0; index < names.size(); ++index) {
        scores.push_back(planning_score(names[index], cities[index], keyword));
    }
    return scores;
}

}  // namespace qh
