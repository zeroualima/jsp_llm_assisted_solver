#include <bits/stdc++.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

int main() {
    int total=0, gap0=0, gap5=0, gap10=0, gap15=0, gapRest=0;

    std::ifstream file("../dataset.jsonl");
    std::string line;

    while (std::getline(file, line)) {
        total++;

        json j = json::parse(line);

        int gapPercent = j["solution"]["gap_percent"];

        if (gapPercent == 0) gap0++;
        else if (gapPercent <= 5) gap5++;
        else if (gapPercent <= 10) gap10++;
        else if (gapPercent <= 15) gap15++;
        else gapRest++;
    }

    printf("The total number of records is : %d\n", total);
    printf("Those with optimal gap : %d\n", gap0);
    printf("Those with gap_percent <= 5 : %d\n", gap5);
    printf("Those with gap_percent <= 10 : %d\n", gap10);
    printf("Those with gap_percent <= 15 : %d\n", gap15);
    printf("Those with gap_percent > 15 : %d\n", gapRest);
}