#pragma once

#include <fstream>
#include <nlohmann/json.hpp>
#include "parser.hpp"

struct Record;

void addJsonRecord(std::ofstream& file, Record& record);