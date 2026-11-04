function demo_simulink_param_export()
%DEMO_SIMULINK_PARAM_EXPORT Round-trip examples/data/dc_speed_params.csv.
%   From the repository root:
%     addpath('tools/simulink-param-export/matlab'); demo_simulink_param_export
%   The canonical CSV is written to examples/output (gitignored).
%
%   Simulink is not called. After the table checks out, a machine that has
%   Simulink can push the checked values. Dialog and model parameters take
%   value_text; workspace and base take the typed value.
%     load_system('dc_speed');
%     hws = get_param('dc_speed', 'ModelWorkspace');
%     names = fieldnames(result.workspace.dc_speed);
%     for k = 1:numel(names)
%         hws.assignin(names{k}, result.workspace.dc_speed.(names{k}));
%     end
%     for k = 1:numel(result.rows)
%         row = result.rows(k);
%         if any(strcmp(row.scope, {'block', 'mask', 'model'}))
%             set_param(row.path, row.name, row.value_text);
%         elseif strcmp(row.scope, 'base')
%             assignin('base', row.name, row.value);
%         end
%     end

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'dc_speed_params.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outCsv = fullfile(outDir, 'simulink_param_export_demo.csv');
    result = simulink_param_export(csvPath, 'output_csv', outCsv, 'strict', true);
    again = simulink_param_export(outCsv, 'strict', true);
    if ~rows_match(result.rows, again.rows)
        error('simulink_param_export:BadTable', 'round-trip mismatch');
    end
    fprintf('simulink-param-export: rows=%d errors=%d\n', result.n_rows, result.n_errors);
    fprintf('%s\n', result.table_text);
    fprintf('%s\n', result.assignment_text);
    fprintf('round-trip ok: %d rows\n', result.n_rows);
    fprintf('saved %s\n', result.output_csv);
end

function ok = rows_match(left, right)
    if numel(left) ~= numel(right)
        ok = false;
        return
    end
    for index = 1:numel(left)
        a = left(index);
        b = right(index);
        if ~strcmp(a.name, b.name) || ~strcmp(a.value_text, b.value_text) ...
                || ~strcmp(a.unit, b.unit) || ~strcmp(a.description, b.description) ...
                || ~strcmp(a.scope, b.scope) || ~strcmp(a.path, b.path) ...
                || ~strcmp(a.dtype, b.dtype) || ~strcmp(a.group, b.group) ...
                || ~values_match(a.value, b.value) ...
                || ~bounds_match(a.minimum, b.minimum) ...
                || ~bounds_match(a.maximum, b.maximum)
            ok = false;
            return
        end
    end
    ok = true;
end

function ok = values_match(left, right)
    if ischar(left) || isstring(left) || ischar(right) || isstring(right)
        ok = strcmp(char(string(left)), char(string(right)));
        return
    end
    if islogical(left) || islogical(right)
        ok = islogical(left) && islogical(right) && left == right;
        return
    end
    ok = isnumeric(left) && isnumeric(right) && left == right;
end

function ok = bounds_match(left, right)
    leftEmpty = isnan(left);
    rightEmpty = isnan(right);
    if leftEmpty || rightEmpty
        ok = leftEmpty && rightEmpty;
        return
    end
    ok = left == right;
end
