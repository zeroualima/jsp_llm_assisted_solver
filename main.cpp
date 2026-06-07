#include "parser.hpp"

#include <iostream>
#include <fstream>
#include <map>

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <starts.dzn> <durations.dzn>\n";
        return 1;
    }

    Record record;

    std::ifstream instanceFile(argv[2]);
    std::ifstream solutionFile(argv[1]);
    std::ofstream jsonlFile("dataset.jsonl");
    
    if (instanceFile.is_open()) {
        parseInstanceFile(instanceFile, record);
    }

    if (solutionFile.is_open()) {
        parseSolutionFile(solutionFile, record, jsonlFile);
    }

    if (jsonlFile.is_open()) {
        addJsonRecord(jsonlFile, record);
    }

    // exportToCSV(record.tasks, "jsp/results.csv");

    return 0;
}