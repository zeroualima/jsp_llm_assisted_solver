#include <fstream>
#include <iostream>
#include <string>
#include <cstdlib>
#include <cstdint>


int main() {
    uint64_t total = 0;
    uint64_t optimal = 0;
    uint64_t unknown = 0;
    uint64_t gap1 = 0;
    uint64_t gap2 = 0;
    uint64_t gap3 = 0;
    uint64_t gapRest = 0;

    std::ifstream file("../dataset.jsonl");
    std::string line;

    const std::string key = "\"gap_percent\":";

    while (std::getline(file, line)) {
        ++total;
        std::cout << total << '\n';

        size_t pos = line.find(key);
        if (pos == std::string::npos)
            continue;

        const char* p = line.c_str() + pos + key.size();

        double g = std::strtod(p, nullptr);

        if (g == 0.0)
            ++optimal;
        else if (g == -1.0)
            ++unknown;
        else if (g <= 0.5)
            ++gap1;
        else if (g <= 1.0)
            ++gap2;
        else if (g <= 2.0)
            ++gap3;
        else
            ++gapRest;
    }

    std::cout << "Total records: " << total << '\n';
    std::cout << "optimal: " << optimal << '\n';
    std::cout << "unknown: " << unknown << '\n';
    std::cout << "0 < gap <= 1: " << gap1 << '\n';
    std::cout << "1 < gap <= 2: " << gap2 << '\n';
    std::cout << "2 < gap <= 3: " << gap3 << '\n';
    std::cout << "gap > 3: " << gapRest << '\n';
}

/*
OUTPUT :

Total records: 25208427
optimal: 15997
unknown: 8177561
0 < gap <= 1: 18217
1 < gap <= 2: 24334
2 < gap <= 3: 49862
gap > 3: 16922456
*/