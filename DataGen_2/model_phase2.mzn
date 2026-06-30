% Phase 2: enumerate solutions whose makespan falls within [C_lb, C_ub],
% the band around i_o (the phase-1 best found). Satisfaction problem --
% run this with --all-solutions. The caller (Python) is responsible for
% capping how many solutions it reads before killing the process; this
% model does not bound the enumeration itself.

int: n_jobs;
int: n_machines;

set of int: jobs = 1..n_jobs;
set of int: tasks = 1..n_machines;

array[1..n_jobs, 1..n_machines] of int: job_task_duration;
array[1..n_jobs, 1..n_machines] of int: job_task_machine;

int: C_lb; % = i_o (phase-1 best found makespan)
int: C_ub; % = i_o scaled up by the accepted gap tolerance

int: total_max_time = sum(job_task_duration);
array[1..n_jobs, 1..n_machines] of var 0..total_max_time: x;
var C_lb..C_ub: C;

constraint forall(j in 1..n_jobs, i in 1..n_machines-1) (
    x[j, i] + job_task_duration[j, i] <= x[j, i+1]
);

constraint forall(j in 1..n_jobs) (
    x[j, n_machines] + job_task_duration[j, n_machines] <= C
);

constraint forall(j1, j2 in 1..n_jobs, i1, i2 in 1..n_machines
    where (j1 < j2) /\ job_task_machine[j1, i1] == job_task_machine[j2, i2]
)(
    x[j1, i1] + job_task_duration[j1, i1] <= x[j2, i2] \/ x[j2, i2] + job_task_duration[j2, i2] <= x[j1, i1]
);

solve satisfy;
