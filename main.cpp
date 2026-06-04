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

    std::ifstream startsFile(argv[1]);
    std::ifstream dataFile(argv[2]);

    if (startsFile.is_open()) {
        parseStartsFile(startsFile, operations);
    }
    
    if (dataFile.is_open()) {
        parseDataFile(dataFile, operations);
    }

    exportToCSV(operations, "jsp/results.csv");

    return 0;
}