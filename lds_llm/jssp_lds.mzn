% Index sets
int: J; % number of jobs
int: M; % number of machines 
int: T = M; % number of tasks per machines

set of int: Job = 1..J;
set of int: Task = 1..T;
set of int: Machine = 0..(M-1);

% Parameters
array[Job, Task] of int: durations; % tasks durations
array[Job, Task] of Machine: machines; % tasks machine
array[Job, Job, Machine] of bool: x; % llm proposed precedences
int: k; % the discrepancy limit 

% Variables
int: max_time = sum(durations);
var 0..max_time: C;
array[Job, Task] of var 0..max_time: S; % start times for each task
array[Job, Job, Machine] of var bool: X; % precedence variables

% Sanity check: tasks cannot take a negative amount of time.
constraint forall(j in Job, t in Task)(durations[j, t] >= 0);

% Precedence
constraint forall(j in Job, t in 1..(T-1)) (S[j, t] + durations[j, t] <= S[j, t+1]);

% The first job task can start no earlier than time step 0
constraint forall(j in Job)(0 <= S[j, 1]);

% No overlap
constraint forall(m in Machine, a, b in Job where a < b) (
    let {
        int: t_a = sum(t in Task where machines[a,t] == m)(t), % detects job a's task that is assigned to m
        int: t_b = sum(t in Task where machines[b,t] == m)(t)
    } in
    X[a,b,m] -> (S[a, t_a] + durations[a, t_a] <= S[b, t_b]) % if X[a,b,m] then a before b
    /\
    not(X[a,b,m]) -> (S[b, t_b] + durations[b, t_b] <= S[a, t_a]) % if not(X[a,b,m]) then b before a
);

% LDS
constraint sum(m in Machine, a, b in Job where a < b)(bool2int(X[a,b,m] != x[a,b,m])) <= k;

% Makespan
constraint forall(j in Job) (S[j, M] + durations[j, M] <= C);

solve satisfy;