#include "parser.hpp"

#include <iostream>
#include <fstream>
#include <map>

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <starts.dzn> <durations.dzn>\n";
        return 1;
    }

    std::map<std::pair<int, int>, Operation> operations;

    std::ifstream solutionFile(argv[1]);
    std::ifstream instanceFile(argv[2]);
    
    if (instanceFile.is_open()) {
        parseInstanceFile(instanceFile, operations);
    }

    if (solutionFile.is_open()) {
        parseSolutionFile(solutionFile, operations);
    }

    // exportToCSV(operations, "jsp/results.csv");

    return 0;
}