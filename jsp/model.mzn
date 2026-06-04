% Parameters loaded from .dzn
int: num_jobs;
int: num_machines;

array[1..num_jobs, 1..num_machines] of int: p; % Durations
array[1..num_jobs, 1..num_machines] of int: m; % Machine assignments

% Variables
int: total_max_time = sum(p);
array[1..num_jobs, 1..num_machines] of var 0..total_max_time: x;
var 0..total_max_time: C;

% Precedence
constraint forall(j in 1..num_jobs, i in 1..num_machines-1) (
    x[j, i] + p[j, i] <= x[j, i+1]
);

% Makespan
constraint forall(j in 1..num_jobs) (
    x[j, num_machines] + p[j, num_machines] <= C
);

% include "disjunctive.mzn";
% % No Overlap
% constraint forall(machine in 1..num_machines)(
%   disjunctive(
%     [x[j, i] | j in 1..num_jobs, i in 1..num_machines where m[j, i] == machine],
%     [p[j, i] | j in 1..num_jobs, i in 1..num_machines where m[j, i] == machine]
%   )
% );

% No Overlap
constraint forall(j1, j2 in 1..num_jobs, i1, i2 in 1..num_machines 
    where (j1 < j2) /\ m[j1, i1] == m[j2, i2]
)( 
    x[j1, i1] + p[j1, i1] <= x[j2, i2] \/ x[j2, i2] + p[j2, i2] <= x[j1, i1]
);

solve minimize C;

% Output format for C++ parsing
output ["x_\(j)_\(i) = \(x[j,i]);\n" | j in 1..num_jobs, i in 1..num_machines];