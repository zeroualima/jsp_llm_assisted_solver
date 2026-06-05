#pragma once

#include <iostream>
#include <fstream>
#include <string>
#include <map>
#include <sstream>

#include "json_generator.hpp"

struct Task {
    int job;
    int task;
    int start;
    int duration;
    int machineID;
};

struct Record {
    std::string source; //
    std::string id; //
    int numJobs;
    int numMachines;
    std::map<std::pair<int, int>, Task> tasks;

    int makespan;
    int optimalMakespan; //
    double gapPercent; //
    bool isOptimal; //

    int nodes;
    int failures;
    double solveTime;
    int randomSeed;    
};

void parseInstanceFile(std::ifstream& file, Record& record);
void parseSolutionFile(std::ifstream& file, Record& record, std::ofstream& jsonlFile);
void exportToCSV(const std::map<std::pair<int, int>, Task>& ops, const std::string& filename);
