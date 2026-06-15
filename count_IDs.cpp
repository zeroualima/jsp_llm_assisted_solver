#include <fstream>
#include <string>
#include <cstdint>
#include <iostream>

int main() {
    std::ifstream file("../filtered_dataset.jsonl");

    std::string line;
    
    std::string prev_id = "";
    std::string curr_id;

    const std::string id_key = "\"id\": \"";

    uint64_t count_id = 0;

    while (std::getline(file, line)) {
        size_t id_pos = line.find(id_key);

        id_pos += id_key.size();       
        size_t id_end = line.find('"', id_pos);

        curr_id = line.substr(id_pos, id_end - id_pos);

        if (prev_id == "") {
            prev_id = curr_id;
            ++count_id;
        } else if (curr_id == prev_id) {
            continue;
        } else {
            prev_id = curr_id;
            ++count_id;
        }
    }

    if (curr_id != prev_id) {
        ++count_id;
    }

    std::cout << "Number of distinct IDs : " << count_id << '\n';
}