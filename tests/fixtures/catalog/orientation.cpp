// Original test fixture; no article snippets are executed.
#include <cstdint>
#include <iostream>
#include <limits>

int main() {
    static_assert(std::numeric_limits<int>::max() == 2147483647, "fixture assumes 32-bit int");
    int a, b;
    if (!(std::cin >> a >> b)) return 2;
#ifdef BROKEN
    const __int128 dx = static_cast<__int128>(b - a);
#else
    const __int128 dx = static_cast<__int128>(b) - a;
#endif
    // Right-angle triangle: determinant is dx squared, exceeding int64_t.
    const __int128 det = dx * dx;
    std::cout << (dx == 4000000000LL && det > std::numeric_limits<std::int64_t>::max()) << '\n';
}
