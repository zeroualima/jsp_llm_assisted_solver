#include "json_generator.hpp"
#include "parser.hpp"

using json = nlohmann::json;

void addJsonRecord(std::ofstream& file, Record& record) {
    json newRecord;

    newRecord["instance"]["source"] = record.source;
    newRecord["instance"]["id"] = record.id;
    newRecord["instance"]["num_jobs"] = record.numJobs;
    newRecord["instance"]["num_machines"] = record.numMachines; 

    std::vector<std::vector<int>> durations(record.numJobs);
    std::vector<std::vector<int>> machines(record.numJobs);
    std::vector<std::vector<int>> starts(record.numJobs);
    for (int j = 0; j < record.numJobs; ++j) {
        durations[j].reserve(record.numMachines);
        machines[j].reserve(record.numMachines);
        starts[j].reserve(record.numMachines);
        for (int t = 0; t < record.numMachines; ++t) {
            durations[j].push_back(record.tasks[{j+1, t+1}].duration);
            machines[j].push_back(record.tasks[{j+1, t+1}].machineID);
            starts[j].push_back(record.tasks[{j+1, t+1}].start);
        }
    }

    newRecord["instance"]["durations"] = durations;
    newRecord["instance"]["machines"] = machines;
    newRecord["solution"]["starts"] = starts;

    newRecord["solution"]["makespan"] = record.makespan;
    newRecord["solution"]["optimal_makespan"] = record.optimalMakespan;
    newRecord["solution"]["gap_percent"] = record.gapPercent;
    newRecord["solution"]["is_optimal"] = record.isOptimal;

    newRecord["solver_stats"]["nodes"] = record.nodes;
    newRecord["solver_stats"]["failures"] = record.failures;
    newRecord["solver_stats"]["solve_time"] = record.solveTime;
    newRecord["solver_stats"]["random_seed"] = record.randomSeed;

    file << newRecord.dump() << '\n';
}