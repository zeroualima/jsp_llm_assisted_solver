% Parameters loaded from .dzn
int: n_jobs;
int: n_machines;

set of int: jobs = 1..n_jobs;
set of int: tasks = 1..n_machines;

array[1..n_jobs, 1..n_machines] of int: job_task_duration; % Durations
array[1..n_jobs, 1..n_machines] of int: job_task_machine; % Machine assignments

% Variables
int: total_max_time = sum(job_task_duration);
array[1..n_jobs, 1..n_machines] of var 0..total_max_time: x;
var 0..total_max_time: C;

% Precedence
constraint forall(j in 1..n_jobs, i in 1..n_machines-1) (
    x[j, i] + job_task_duration[j, i] <= x[j, i+1]
);

% Makespan
constraint forall(j in 1..n_jobs) (
    x[j, n_machines] + job_task_duration[j, n_machines] <= C
);

% No Overlap
constraint forall(j1, j2 in 1..n_jobs, i1, i2 in 1..n_machines 
    where (j1 < j2) /\ job_task_machine[j1, i1] == job_task_machine[j2, i2]
)( 
    x[j1, i1] + job_task_duration[j1, i1] <= x[j2, i2] \/ x[j2, i2] + job_task_duration[j2, i2] <= x[j1, i1]
);

% include "disjunctive.mzn";
% % No Overlap
% constraint forall(machine in 1..n_machines)(
%   disjunctive(
%     [x[j, i] | j in 1..n_jobs, i in 1..n_machines where m[j, i] == machine],
%     [p[j, i] | j in 1..n_jobs, i in 1..n_machines where m[j, i] == machine]
%   )
% );

solve minimize C;

% Output format for C++ parsing
output
[
  "makespan=\(C);\n"
]
++
[
    "x_\(j)_\(i)=\(x[j,i]);\n" 
    | j in 1..n_jobs, i in 1..n_machines
];