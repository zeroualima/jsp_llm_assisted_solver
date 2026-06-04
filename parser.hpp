#ifndef PARSER_H
#define PARSER_H

#include <iostream>
#include <fstream>
#include <string>
#include <map>
#include <sstream>

struct Task {
    int job;
    int task;
    int start;
    int duration;
    int machineID;
};

struct 

void parseInstanceFile(std::ifstream& file, std::map<std::pair<int, int>, Task>& ops);
void parseSolutionFile(std::ifstream& file, std::map<std::pair<int, int>, Task>& ops);
void exportToCSV(const std::map<std::pair<int, int>, Task>& ops, const std::string& filename);

#endif