#ifndef PARSER_H
#define PARSER_H

#include <iostream>
#include <fstream>
#include <string>
#include <map>
#include <sstream>

struct Operation {
    int job;
    int operation;
    int start;
    int duration;
    int machineID;
};

void parseStartsFile(std::ifstream& file, std::map<std::pair<int, int>, Operation>& ops);
void parseDataFile(std::ifstream& file, std::map<std::pair<int, int>, Operation>& ops);
void exportToCSV(const std::map<std::pair<int, int>, Operation>& ops, const std::string& filename);

#endif