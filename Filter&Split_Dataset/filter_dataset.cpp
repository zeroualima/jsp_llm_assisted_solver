#include <fstream>
#include <string>
#include <cstdint>
#include <iostream>

int main() {
    std::ifstream file("../dataset.jsonl");
    std::ofstream out("../filtered_dataset.jsonl");

    std::string prev_line;
    std::string curr_line;
    
    std::string prev_id;
    std::string curr_id;

    bool got_written = true;

    const std::string gap_key = "\"gap_percent\":";
    const std::string id_key = "\"id\": \"";

    uint64_t count = 0;
    uint64_t written_line_count = 0;

    while (std::getline(file, curr_line)) {
        ++count;
        std::cout << count << '\n';

        size_t gap_pos = curr_line.find(gap_key);
        size_t id_pos = curr_line.find(id_key);

        id_pos += id_key.size();       
        size_t id_end = curr_line.find('"', id_pos);

        curr_id = curr_line.substr(id_pos, id_end - id_pos);

        const char* gap_ptr = curr_line.c_str() + gap_pos + gap_key.size();

        double gap_val = std::strtod(gap_ptr, nullptr);

        if (got_written == false && prev_id != curr_id) {
            out << prev_line << '\n';
            got_written = true;
            ++written_line_count;
        } 
        
        if (gap_val == -1.0) {
            got_written = false;
            prev_line = curr_line;
            prev_id = curr_id;
        }
        
        if (gap_val >= 0.0 && gap_val <= 3.0) {
            out << curr_line << '\n';
            ++written_line_count;
            got_written = true;
        }
    }

    if (got_written == false) {
        out << prev_line << '\n';
        ++written_line_count;
    }

    std::cout << "Total number of selected lines : " << written_line_count << '\n';
}