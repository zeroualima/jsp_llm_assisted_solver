#include "parser.hpp"

void parseInstanceFile(std::ifstream& file, Record& record) {
    std::string line;
    
    bool readingP = false;
    bool readingM = false;
    int currentRow = 1;

    while (std::getline(file, line)) {
        if (line.find("=") != std::string::npos && line.find(";") != std::string::npos) {
            char key[64];
            int val;

            if (sscanf(line.c_str(), "%63[^ =] = %d;", key, &val) == 2) {
                std::string varName(key);

                if (varName == "n_jobs") {
                    record.numJobs = val;
                    continue;
                } 
                else if (varName == "n_machines") {
                    record.numMachines = val;
                    continue;
                }
            }
        }

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
                    if (readingP) record.tasks[{currentRow, currentCol}].duration = val;
                    if (readingM) record.tasks[{currentRow, currentCol}].machineID = val;
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

void parseSolutionFile(std::ifstream& file, Record& record, std::ofstream& jsonlFile) {
    std::string line;
    while (std::getline(file, line)) {
        // if (line.find("----------")) {
        //     if (jsonlFile.is_open()) {
        //         addJsonRecord(jsonlFile, record);
        //     }
        // }

        if (line.find("makespan =") != std::string::npos && line.find(";") != std::string::npos) {
            char key[64];
            int val;
            if (sscanf(line.c_str(), "%63[^ =] = %d;", key, &val) == 2) {
                std::string varName(key);
                if (varName == "makespan") {
                    record.numJobs = val;
                    continue;
                } 
            }
        }

        int j, o, val;
        // Parsing format: x_1_2 = 8;
        if (sscanf(line.c_str(), "%*c_%d_%d=%d;", &j, &o, &val) == 3) {
            record.tasks[{j, o}].job = j;
            record.tasks[{j, o}].task = o;
            record.tasks[{j, o}].start = val;
            continue;
        }

        if (line.find("%%%mzn-stat:") != std::string::npos) {
            char key[64];
            double val;

            if (sscanf(line.c_str(), "%%%%%%mzn-stat: %63[^=]=%lf", key, &val) == 2) {
                std::string statName(key);

                // if (statName == "objective") {
                //     record.makespan = static_cast<int>(val);
                // } else 
                if (statName == "nodes") {
                    record.nodes = static_cast<int>(val);
                } else if (statName == "failures") {
                    record.failures = static_cast<int>(val);
                } else if (statName == "solveTime") {
                    record.solveTime = val;
                } else if (statName == "randomSeed") {
                    record.randomSeed = static_cast<int>(val);
                }

                // gapPercent ...
            }
        }
    }
}

void exportToCSV(const std::map<std::pair<int, int>, Task>& Record, const std::string& filename) {
    std::ofstream file(filename);
    file << "Job,Task,Start,Duration,Machine\n";
    
    for (auto const& [key, task] : Record) {
        file << task.job << "," << task.task << "," << task.start << "," << task.duration << "," << task.machineID << "\n";
    }
    file.close();
}