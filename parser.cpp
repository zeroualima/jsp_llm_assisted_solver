#include "parser.hpp"

void parseSolutionFile(std::ifstream& file, std::map<std::pair<int, int>, Task>& tasks) {
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty()) continue;

        int j, o, val;
        // Parsing format: x_1_2 = 8;
        if (sscanf(line.c_str(), "%*c_%d_%d = %d;", &j, &o, &val) == 3) {
            tasks[{j, o}].job = j;
            tasks[{j, o}].task = o;
            tasks[{j, o}].start = val;
        }
    }
}

void parseInstanceFile(std::ifstream& file, std::map<std::pair<int, int>, Task>& tasks) {
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
                    if (readingP) tasks[{currentRow, currentCol}].duration = val;
                    if (readingM) tasks[{currentRow, currentCol}].machineID = val;
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

void exportToCSV(const std::map<std::pair<int, int>, Task>& tasks, const std::string& filename) {
    std::ofstream file(filename);
    file << "Job,Task,Start,Duration,Machine\n"; // Header
    
    for (auto const& [key, task] : tasks) {
        file << task.job << "," << task.task << "," << task.start << "," << task.duration << "," << task.machineID << "\n";
    }
    file.close();
}