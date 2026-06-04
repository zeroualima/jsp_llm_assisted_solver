int: p_1_1;
int: p_1_2;

int: p_2_1;
int: p_2_2;
int: p_2_3;

int: p_3_1;
int: p_3_2;

% JOB 1
var 0..100: x_1_1;
var 0..100: x_1_2;

% JOB 2
var 0..100: x_2_1;
var 0..100: x_2_2;
var 0..100: x_2_3;

% JOB 3
var 0..100: x_3_1;
var 0..100: x_3_2;

% Makespan
var 0..1000: C;
constraint x_1_2 + p_1_2 <= C;
constraint x_2_3 + p_2_3 <= C;
constraint x_3_2 + p_3_2 <= C;

% Precedence
constraint x_1_1 + p_1_1 <= x_1_2;

constraint x_2_1 + p_2_1 <= x_2_2;
constraint x_2_2 + p_2_2 <= x_2_3;

constraint x_3_1 + p_3_1 <= x_3_2;

% On considere deux machines
% M1 : O11, O22, O31
% M2 : O12, O21, O23, O32

% No overlap
% M1
constraint (x_1_1 + p_1_1 <= x_2_2) \/ (x_2_2 + p_2_2 <= x_1_1); % O_1_1 with O_2_2
constraint (x_1_1 + p_1_1 <= x_3_1) \/ (x_3_1 + p_3_1 <= x_1_1); % O_1_1 with O_3_1
constraint (x_2_2 + p_2_2 <= x_3_1) \/ (x_3_1 + p_3_1 <= x_2_2); % O_2_2 with O_3_1

% M2
constraint (x_1_2 + p_1_2 <= x_2_1) \/ (x_2_1 + p_2_1 <= x_1_2); % O_1_2 with O_2_1
constraint (x_1_2 + p_1_2 <= x_2_3) \/ (x_2_3 + p_2_3 <= x_1_2); % O_1_2 with O_2_3
constraint (x_1_2 + p_1_2 <= x_3_2) \/ (x_3_2 + p_3_2 <= x_1_2); % O_1_2 with O_3_2
constraint (x_2_1 + p_2_1 <= x_2_3) \/ (x_2_3 + p_2_3 <= x_2_1); % O_2_1 with O_2_3
constraint (x_2_1 + p_2_1 <= x_3_2) \/ (x_3_2 + p_3_2 <= x_2_1); % O_2_1 with O_3_2
constraint (x_2_3 + p_2_3 <= x_3_2) \/ (x_3_2 + p_3_2 <= x_2_3); % O_2_3 with O_3_2

solve minimize C;