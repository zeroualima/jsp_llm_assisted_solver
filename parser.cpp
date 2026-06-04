#include "parser.hpp"

void parseStartsFile(std::ifstream& file, std::map<std::pair<int, int>, Operation>& ops) {
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty()) continue;

        int j, o, val;
        // Parsing format: x_1_2 = 8;
        if (sscanf(line.c_str(), "%*c_%d_%d = %d;", &j, &o, &val) == 3) {
            ops[{j, o}].job = j;
            ops[{j, o}].operation = o;
            ops[{j, o}].start = val;
        }
    }
}

void parseDataFile(std::ifstream& file, std::map<std::pair<int, int>, Operation>& ops) {
    std::string line;
    
    bool readingP = false;
    bool readingM = false;
    int currentRow = 1;

    while (std::getline(file, line)) {
        if (line.find("job_task_machine = ") != std::string::npos) {
            readingM = true;
            currentRow = 1;
            continue;
        }
        if (line.find("job_task_duration = ") != std::string::npos) {
            readingP = true; 
            currentRow = 1;
            continue;
        }
        if (readingP || readingM) {
            std::stringstream ss(line);
            int val;
            int currentCol = 1;
            char comma;

            while (ss >> val) {
                if (val != 0) {
                    if (readingP) ops[{currentRow, currentCol}].duration = val;
                    if (readingM) ops[{currentRow, currentCol}].machineID = val;
                }
                ss >> comma; // consume the comma
                currentCol++;
            }

            currentRow++;
        }
        if (line.find(";") != std::string::npos) {
            readingP = false; 
            readingM = false; 
            continue; 
        }
    }
}

void exportToCSV(const std::map<std::pair<int, int>, Operation>& ops, const std::string& filename) {
    std::ofstream file(filename);
    file << "Job,Operation,Start,Duration,Machine\n"; // Header
    
    for (auto const& [key, op] : ops) {
        file << op.job << "," << op.operation << "," << op.start << "," << op.duration << "," << op.machineID << "\n";
    }
    file.close();
}