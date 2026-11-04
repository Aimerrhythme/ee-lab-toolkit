function result = simulink_param_export(varargin)
%SIMULINK_PARAM_EXPORT Read, check, and write a parameter table CSV.
%   RESULT = SIMULINK_PARAM_EXPORT(CSV_PATH)
%   RESULT = SIMULINK_PARAM_EXPORT(CSV_PATH, 'output_csv', OUT, 'strict', true)
%   RESULT = SIMULINK_PARAM_EXPORT(ROWS)
%
%   Classroom convention for Simulink block, mask, model, and workspace
%   parameters. This file does not call Simulink. value_text is the char a
%   later set_param would receive. workspace and base hold typed values.
%
%   Canonical columns:
%     name, value, unit, description, scope, path, dtype, minimum, maximum, group
%   dtype is double, int, logical, or string.
%   scope is model, block, mask, workspace, or base. Empty scope means base.
%   Bounds are inclusive and apply only to double and int.
%   int values are stored as double (exact through 2^53). An empty bound is NaN.
%
%   Name-value keys match Python: rows, csv_path, output_csv, strict.
%   RESULT fields: rows, errors, workspace, base, output_csv, n_rows, n_errors,
%   table_text, assignment_text.
%   rows(i) holds name, value, value_text, unit, description, scope, path,
%   dtype, minimum, maximum, group, row_number.
%   errors(i) holds row_number, field, message.

    [source, rest] = split_source(varargin);
    parser = inputParser;
    parser.FunctionName = 'simulink_param_export';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('rows', []);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('strict', true, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    records = resolve_records(source, opt);
    [rows, issues] = validate_records(records);
    if logical(opt.strict) && ~isempty(issues)
        error('simulink_param_export:BadTable', '%s', issues(1).message);
    end

    outputCsv = char(strtrim(string(opt.output_csv)));
    if ~isempty(outputCsv)
        write_table(outputCsv, rows);
    end
    [workspace, base] = build_assignments(rows);

    result = struct();
    result.rows = rows;
    result.errors = issues;
    result.workspace = workspace;
    result.base = base;
    result.output_csv = outputCsv;
    result.n_rows = numel(rows);
    result.n_errors = numel(issues);
    result.table_text = format_param_table(rows);
    result.assignment_text = format_assignments(rows);
end

function [source, rest] = split_source(args)
    if isempty(args)
        source = [];
        rest = {};
        return
    end
    if is_parameter_name(args{1})
        source = [];
        rest = args;
        return
    end
    source = args{1};
    if numel(args) == 1
        rest = {};
    else
        rest = args(2:end);
    end
end

function tf = is_parameter_name(value)
    if ischar(value)
        text = value;
    elseif isstring(value) && isscalar(value)
        text = char(value);
    else
        tf = false;
        return
    end
    keys = {'rows', 'csv_path', 'output_csv', 'strict'};
    tf = any(strcmpi(strtrim(text), keys));
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = isstring(value) && isscalar(value);
end

function records = resolve_records(source, opt)
    hasSource = ~isempty(source);
    hasRows = ~isempty(opt.rows);
    csvPath = char(strtrim(string(opt.csv_path)));
    hasCsv = ~isempty(csvPath);
    if hasSource && hasRows
        error('simulink_param_export:BadOption', 'rows: not both source and rows');
    end
    if hasSource && hasCsv
        error('simulink_param_export:BadOption', 'csv_path: not both source and csv_path');
    end
    if hasRows && hasCsv
        error('simulink_param_export:BadOption', 'csv_path: not both rows and csv_path');
    end
    if ~hasSource && ~hasRows && ~hasCsv
        error('simulink_param_export:BadOption', 'source: required');
    end
    if hasRows
        records = records_from_value(opt.rows);
        return
    end
    if hasCsv
        records = records_from_csv(csvPath);
        return
    end
    if is_path_source(source)
        records = records_from_csv(char(strtrim(string(source))));
        return
    end
    records = records_from_value(source);
end

function ok = is_path_source(source)
    ok = (ischar(source) && (isempty(source) || isrow(source))) || ...
        (isstring(source) && isscalar(source));
end

function records = records_from_csv(csvPath)
    if exist(csvPath, 'file') ~= 2
        error('simulink_param_export:NotFound', 'csv_path: file not found: %s', csvPath);
    end
    fid = fopen(csvPath, 'r', 'n', 'UTF-8');
    if fid < 0
        error('simulink_param_export:NotFound', 'csv_path: file not found: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    header = {};
    delimiter = ',';
    found = {};
    lineNumber = 0;
    while true
        line = fgetl(fid);
        if ~ischar(line)
            break
        end
        lineNumber = lineNumber + 1;
        if lineNumber == 1 && ~isempty(line) && double(line(1)) == 65279
            line = line(2:end);
        end
        trimmed = strtrim(line);
        if isempty(trimmed) || trimmed(1) == '#'
            continue
        end
        if isempty(header)
            if count_char(line, ';') > count_char(line, ',')
                delimiter = ';';
            end
            header = map_header(split_csv_line(line, delimiter));
            continue
        end
        cells = split_csv_line(line, delimiter);
        found{end + 1} = record_from_cells(header, cells, lineNumber); %#ok<AGROW>
    end
    if isempty(header)
        error('simulink_param_export:BadTable', 'header: missing name column');
    end
    if isempty(found)
        records = repmat(blank_record(), 1, 0);
    else
        records = [found{:}];
    end
end

function records = records_from_value(value)
    if iscell(value)
        items = value;
    elseif isstruct(value)
        items = num2cell(value);
    else
        error('simulink_param_export:BadOption', 'rows: expected a struct, cell, or CSV path');
    end
    n = numel(items);
    if n == 0
        records = repmat(blank_record(), 1, 0);
        return
    end
    found = cell(1, n);
    for index = 1:n
        found{index} = record_from_mapping(items{index}, index);
    end
    records = [found{:}];
end

function rec = record_from_cells(header, cells, lineNumber)
    rec = blank_record();
    rec.line = lineNumber;
    if numel(cells) ~= numel(header)
        rec.error_field = 'header';
        rec.error_detail = 'field count';
        return
    end
    for index = 1:numel(header)
        rec.(header{index}) = strtrim(cells{index});
    end
end

function rec = record_from_mapping(value, rowNumber)
    rec = blank_record();
    rec.line = rowNumber;
    if ~(isstruct(value) && numel(value) == 1)
        rec.error_field = 'header';
        rec.error_detail = 'expected a mapping';
        return
    end
    names = fieldnames(value);
    hint = '';
    for index = 1:numel(names)
        canon = canonical_header(names{index});
        if isempty(canon)
            rec = blank_record();
            rec.line = rowNumber;
            rec.error_field = 'header';
            rec.error_detail = ['unknown field ' names{index}];
            return
        end
        [text, fieldHint, ok, detail] = cell_to_text(canon, value.(names{index}));
        if ~ok
            rec = blank_record();
            rec.line = rowNumber;
            rec.error_field = canon;
            rec.error_detail = detail;
            return
        end
        rec.(canon) = text;
        if strcmp(canon, 'value')
            hint = fieldHint;
        end
    end
    if isempty(strtrim(rec.dtype)) && ~isempty(hint)
        rec.dtype = hint;
    end
end

function [text, hint, ok, detail] = cell_to_text(canon, raw)
    hint = '';
    ok = true;
    detail = '';
    text = '';
    if strcmp(canon, 'value')
        if islogical(raw) && isscalar(raw)
            if raw
                text = 'true';
            else
                text = 'false';
            end
            hint = 'logical';
            return
        end
        if isnumeric(raw) && isscalar(raw)
            if ~isfinite(raw)
                ok = false;
                detail = 'not finite';
                return
            end
            if raw == floor(raw) && abs(raw) <= 2^53
                text = sprintf('%.0f', raw);
                hint = 'int';
            else
                text = format_double(raw);
                hint = 'double';
            end
            return
        end
        if is_text_value(raw)
            text = char(strtrim(string(raw)));
            return
        end
        ok = false;
        detail = 'unsupported value class';
        return
    end
    if (strcmp(canon, 'minimum') || strcmp(canon, 'maximum')) && isnumeric(raw) && isscalar(raw)
        if isnan(raw)
            text = '';
            return
        end
        if ~isfinite(raw)
            ok = false;
            detail = 'not finite';
            return
        end
        text = format_double(raw);
        return
    end
    if (strcmp(canon, 'minimum') || strcmp(canon, 'maximum')) && isempty(raw)
        text = '';
        return
    end
    if is_text_value(raw) || (ischar(raw) && isempty(raw))
        text = char(strtrim(string(raw)));
        return
    end
    ok = false;
    detail = 'unsupported field class';
end

function ok = is_text_value(raw)
    ok = (ischar(raw) && (isempty(raw) || isrow(raw))) || (isstring(raw) && isscalar(raw));
end

function rec = blank_record()
    rec = struct( ...
        'line', 0, ...
        'name', '', ...
        'value', '', ...
        'unit', '', ...
        'description', '', ...
        'scope', '', ...
        'path', '', ...
        'dtype', '', ...
        'minimum', '', ...
        'maximum', '', ...
        'group', '', ...
        'error_field', '', ...
        'error_detail', '');
end

function cells = split_csv_line(line, delimiter)
    cells = {};
    buf = '';
    inQuote = false;
    index = 1;
    n = numel(line);
    while index <= n
        ch = line(index);
        if inQuote
            if ch == '"'
                if index < n && line(index + 1) == '"'
                    buf = [buf '"']; %#ok<AGROW>
                    index = index + 2;
                    continue
                end
                inQuote = false;
                index = index + 1;
                continue
            end
            buf = [buf ch]; %#ok<AGROW>
            index = index + 1;
            continue
        end
        if ch == '"'
            inQuote = true;
            index = index + 1;
            continue
        end
        if ch == delimiter
            cells{end + 1} = buf; %#ok<AGROW>
            buf = '';
            index = index + 1;
            continue
        end
        buf = [buf ch]; %#ok<AGROW>
        index = index + 1;
    end
    if inQuote
        error('simulink_param_export:BadTable', 'header: unclosed quote');
    end
    cells{end + 1} = buf;
end

function names = map_header(cells)
    names = cell(1, numel(cells));
    seen = {};
    hasName = false;
    hasValue = false;
    for index = 1:numel(cells)
        canon = canonical_header(cells{index});
        if isempty(canon)
            error('simulink_param_export:BadTable', 'header: unknown column %s', strtrim(cells{index}));
        end
        if any(strcmp(seen, canon))
            error('simulink_param_export:BadTable', 'header: duplicate column %s', canon);
        end
        seen{end + 1} = canon; %#ok<AGROW>
        names{index} = canon;
        if strcmp(canon, 'name')
            hasName = true;
        elseif strcmp(canon, 'value')
            hasValue = true;
        end
    end
    if ~hasName
        error('simulink_param_export:BadTable', 'header: missing name column');
    end
    if ~hasValue
        error('simulink_param_export:BadTable', 'header: missing value column');
    end
end

function canon = canonical_header(text)
    key = norm_header(text);
    switch key
        case {'name', 'param', 'parameter', 'parametername', char([21442 25968 21517]), char([21442 25968])}
            canon = 'name';
        case {'value', 'val', char(20540), char([25968 20540])}
            canon = 'value';
        case {'unit', 'units', char([21333 20301])}
            canon = 'unit';
        case {'description', 'desc', 'comment', char([35828 26126]), char([25551 36848])}
            canon = 'description';
        case {'scope', 'target', char([20316 29992 22495])}
            canon = 'scope';
        case {'path', 'block', 'blockpath', char([36335 24452])}
            canon = 'path';
        case {'dtype', 'type', 'datatype', char([31867 22411])}
            canon = 'dtype';
        case {'minimum', 'min', 'lower', char([19979 38480])}
            canon = 'minimum';
        case {'maximum', 'max', 'upper', char([19978 38480])}
            canon = 'maximum';
        case {'group', 'category', char([20998 32452]), char([31867 21035])}
            canon = 'group';
        otherwise
            canon = '';
    end
end

function key = norm_header(text)
    key = char(strtrim(string(text)));
    if ~isempty(key) && double(key(1)) == 65279
        key = char(strtrim(string(key(2:end))));
    end
    key = lower(key);
    key = regexprep(key, '[\s_]+', '');
end

function [rows, issues] = validate_records(records)
    good = {};
    bad = {};
    for index = 1:numel(records)
        [row, issue] = interpret_record(records(index));
        if isempty(issue)
            good{end + 1} = row; %#ok<AGROW>
        else
            bad{end + 1} = issue; %#ok<AGROW>
        end
    end
    if isempty(good)
        rows = repmat(empty_row(), 1, 0);
    else
        rows = [good{:}];
    end
    seen = {};
    keep = true(1, numel(rows));
    for index = 1:numel(rows)
        key = sprintf('%s|%s|%s', rows(index).scope, rows(index).path, rows(index).name);
        if any(strcmp(seen, key))
            keep(index) = false;
            bad{end + 1} = make_issue('duplicate', rows(index).row_number, ['key ' key]); %#ok<AGROW>
        else
            seen{end + 1} = key; %#ok<AGROW>
        end
    end
    rows = rows(keep);
    if isempty(bad)
        issues = empty_issues();
    else
        issues = sort_issues([bad{:}]);
    end
end

function [row, issue] = interpret_record(rec)
    row = empty_row();
    issue = [];
    if ~isempty(rec.error_field)
        issue = make_issue(rec.error_field, rec.line, rec.error_detail);
        row = [];
        return
    end
    name = strtrim(rec.name);
    if isempty(name)
        issue = make_issue('name', rec.line, 'empty');
        row = [];
        return
    end
    if ~is_identifier(name)
        issue = make_issue('name', rec.line, 'not an identifier');
        row = [];
        return
    end

    scope = lower(strtrim(rec.scope));
    if isempty(scope)
        scope = 'base';
    end
    if ~any(strcmp({'model', 'block', 'mask', 'workspace', 'base'}, scope))
        issue = make_issue('scope', rec.line, 'unknown');
        row = [];
        return
    end
    pathText = strtrim(rec.path);
    pathDetail = check_path(scope, pathText);
    if ~isempty(pathDetail)
        issue = make_issue('path', rec.line, pathDetail);
        row = [];
        return
    end

    rawDtype = strtrim(rec.dtype);
    explicitDtype = ~isempty(rawDtype);
    valueIn = strtrim(rec.value);
    dtype = lower(rawDtype);
    if isempty(dtype)
        if isempty(valueIn)
            issue = make_issue('value', rec.line, 'empty');
            row = [];
            return
        end
        dtype = infer_dtype(valueIn);
    end
    if ~any(strcmp({'double', 'int', 'logical', 'string'}, dtype))
        issue = make_issue('dtype', rec.line, 'unknown');
        row = [];
        return
    end
    if isempty(valueIn) && ~(explicitDtype && strcmp(dtype, 'string'))
        issue = make_issue('value', rec.line, 'empty');
        row = [];
        return
    end

    [typed, canonical, ok, detail] = parse_value(dtype, valueIn);
    if ~ok
        issue = make_issue('value', rec.line, detail);
        row = [];
        return
    end

    unit = strtrim(rec.unit);
    if ~is_unit_text(unit)
        issue = make_issue('unit', rec.line, 'illegal');
        row = [];
        return
    end
    description = strtrim(rec.description);
    if numel(description) > 240
        issue = make_issue('description', rec.line, 'too long');
        row = [];
        return
    end
    if has_control_char(description)
        issue = make_issue('description', rec.line, 'illegal character');
        row = [];
        return
    end
    group = strtrim(rec.group);
    if ~is_group_text(group)
        issue = make_issue('group', rec.line, 'illegal');
        row = [];
        return
    end

    [minimum, ok, detail] = parse_bound(strtrim(rec.minimum));
    if ~ok
        issue = make_issue('minimum', rec.line, detail);
        row = [];
        return
    end
    [maximum, ok, detail] = parse_bound(strtrim(rec.maximum));
    if ~ok
        issue = make_issue('maximum', rec.line, detail);
        row = [];
        return
    end
    if ~isnan(minimum) && ~isnan(maximum) && minimum > maximum
        issue = make_issue('minimum', rec.line, 'greater than maximum');
        row = [];
        return
    end
    if ~any(strcmp({'double', 'int'}, dtype)) && (~isnan(minimum) || ~isnan(maximum))
        if ~isnan(minimum)
            field = 'minimum';
        else
            field = 'maximum';
        end
        issue = make_issue(field, rec.line, 'not allowed for this dtype');
        row = [];
        return
    end
    if isnumeric(typed) && ~islogical(typed)
        if ~isnan(minimum) && typed < minimum
            issue = make_issue('minimum', rec.line, 'value is below minimum');
            row = [];
            return
        end
        if ~isnan(maximum) && typed > maximum
            issue = make_issue('maximum', rec.line, 'value is above maximum');
            row = [];
            return
        end
    end

    row.name = name;
    row.value = typed;
    row.value_text = canonical;
    row.unit = unit;
    row.description = description;
    row.scope = scope;
    row.path = pathText;
    row.dtype = dtype;
    row.minimum = minimum;
    row.maximum = maximum;
    row.group = group;
    row.row_number = rec.line;
end

function [typed, canonical, ok, detail] = parse_value(dtype, text)
    typed = [];
    canonical = '';
    ok = false;
    detail = '';
    if strcmp(dtype, 'double')
        [typed, canonical, ok, detail] = parse_double_text(text);
        return
    end
    if strcmp(dtype, 'int')
        [typed, canonical, ok, detail] = parse_int_text(text);
        return
    end
    if strcmp(dtype, 'logical')
        [typed, canonical, ok, detail] = parse_logical_text(text);
        return
    end
    if numel(text) > 240
        detail = 'too long';
        return
    end
    if has_control_char(text)
        detail = 'illegal character';
        return
    end
    typed = text;
    canonical = text;
    ok = true;
end

function [number, canon, ok, detail] = parse_double_text(text)
    number = NaN;
    canon = '';
    ok = false;
    detail = 'not a double';
    if isempty(regexp(text, '^[+-]?(\d+\.\d+|\d+|\.\d+)([eE][+-]?\d+)?$', 'once'))
        return
    end
    number = str2double(text);
    if ~isfinite(number)
        detail = 'not finite';
        return
    end
    canon = format_double(number);
    ok = true;
    detail = '';
end

function [number, canon, ok, detail] = parse_int_text(text)
    number = 0;
    canon = '';
    ok = false;
    detail = 'not an int';
    if isempty(regexp(text, '^[+-]?\d+$', 'once'))
        return
    end
    canon = canonical_int_text(text);
    number = str2double(canon);
    roundtrip = sprintf('%.0f', number);
    if ~isfinite(number) || ~strcmp(roundtrip, canon) || abs(number) > 2^53
        detail = 'out of int range';
        canon = '';
        return
    end
    ok = true;
    detail = '';
end

function text = canonical_int_text(text)
    sign = '';
    body = text;
    if body(1) == '+'
        body = body(2:end);
    elseif body(1) == '-'
        sign = '-';
        body = body(2:end);
    end
    while numel(body) > 1 && body(1) == '0'
        body = body(2:end);
    end
    if strcmp(body, '0')
        text = '0';
    else
        text = [sign body];
    end
end

function [value, canon, ok, detail] = parse_logical_text(text)
    value = false;
    canon = '';
    ok = false;
    detail = 'not a logical';
    switch lower(text)
        case {'true', 'yes', 'on', '1'}
            value = true;
            canon = 'true';
            ok = true;
            detail = '';
        case {'false', 'no', 'off', '0'}
            value = false;
            canon = 'false';
            ok = true;
            detail = '';
    end
end

function [value, ok, detail] = parse_bound(text)
    value = NaN;
    ok = true;
    detail = '';
    if isempty(text)
        return
    end
    [value, ~, ok, detail] = parse_double_text(text);
    if ~ok && strcmp(detail, 'not finite')
        return
    end
    if ~ok
        detail = 'not a double';
        value = NaN;
    end
end

function detail = check_path(scope, pathText)
    detail = '';
    if strcmp(scope, 'base')
        if ~isempty(pathText)
            detail = 'must be empty for base';
        end
        return
    end
    if strcmp(scope, 'model') || strcmp(scope, 'workspace')
        if isempty(pathText)
            detail = 'required';
            return
        end
        if ~is_identifier(pathText)
            detail = 'not a model name';
        end
        return
    end
    if ~contains(pathText, '/')
        detail = 'needs a slash';
        return
    end
    parts = strsplit(pathText, '/');
    if numel(parts) < 2
        detail = 'needs a slash';
        return
    end
    for index = 1:numel(parts)
        if ~is_segment(parts{index})
            detail = 'bad segment';
            return
        end
    end
end

function dtype = infer_dtype(text)
    lowered = lower(text);
    if any(strcmp(lowered, {'true', 'false', 'yes', 'no', 'on', 'off'}))
        dtype = 'logical';
    elseif ~isempty(regexp(text, '^[+-]?\d+$', 'once'))
        dtype = 'int';
    elseif ~isempty(regexp(text, '^[+-]?(\d+\.\d+|\d+|\.\d+)([eE][+-]?\d+)?$', 'once'))
        dtype = 'double';
    else
        dtype = 'string';
    end
end

function ok = is_identifier(text)
    ok = ~isempty(regexp(text, '^[A-Za-z_][A-Za-z0-9_]{0,62}$', 'once'));
end

function ok = is_segment(text)
    if isempty(text) || ~strcmp(text, strtrim(text))
        ok = false;
        return
    end
    ok = ~isempty(regexp(text, '^[A-Za-z_][A-Za-z0-9_ -]{0,62}$', 'once'));
end

function ok = is_group_text(text)
    if isempty(text)
        ok = true;
        return
    end
    ok = ~isempty(regexp(text, '^[A-Za-z_][A-Za-z0-9_-]{0,31}$', 'once'));
end

function ok = is_unit_text(text)
    if isempty(text)
        ok = true;
        return
    end
    if numel(text) > 32
        ok = false;
        return
    end
    separators = ['.' '/' '^' '-' char(183)];
    extras = [char(937) char(181) char(956) char(176)];
    tokens = {};
    current = '';
    for index = 1:numel(text)
        ch = text(index);
        if any(ch == separators)
            if isempty(current)
                ok = false;
                return
            end
            tokens{end + 1} = current; %#ok<AGROW>
            current = '';
        else
            current = [current ch]; %#ok<AGROW>
        end
    end
    if isempty(current)
        ok = false;
        return
    end
    tokens{end + 1} = current; %#ok<AGROW>
    for index = 1:numel(tokens)
        if ~unit_token_ok(tokens{index}, index == 1, extras)
            ok = false;
            return
        end
    end
    ok = true;
end

function ok = unit_token_ok(token, isFirst, extras)
    if isFirst && (strcmp(token, '1') || strcmp(token, '%'))
        ok = true;
        return
    end
    if all(isstrprop(token, 'digit'))
        ok = ~isFirst;
        return
    end
    if ~(is_ascii_letter(token(1)) || any(token(1) == extras))
        ok = false;
        return
    end
    ok = true;
    for index = 2:numel(token)
        ch = token(index);
        if is_ascii_alnum(ch) || any(ch == extras)
            continue
        end
        ok = false;
        return
    end
end

function ok = is_ascii_letter(ch)
    ok = (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z');
end

function ok = is_ascii_alnum(ch)
    ok = is_ascii_letter(ch) || (ch >= '0' && ch <= '9');
end

function ok = has_control_char(text)
    if isempty(text)
        ok = false;
        return
    end
    ok = any(double(text) < 32);
end

function text = format_double(value)
    if ~isfinite(value)
        error('simulink_param_export:BadTable', 'value: not finite');
    end
    if value == 0
        text = '0';
        return
    end
    text = sprintf('%.16g', value);
    if str2double(text) ~= value
        text = sprintf('%.17g', value);
    end
    text = strrep(text, 'E', 'e');
end

function write_table(path, rows)
    path = char(strtrim(string(path)));
    folder = fileparts(path);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        [ok, message] = mkdir(folder);
        if ~ok
            error('simulink_param_export:BadTable', 'output_csv: %s', message);
        end
    end
    fid = fopen(path, 'w', 'n', 'UTF-8');
    if fid < 0
        error('simulink_param_export:BadTable', 'output_csv: cannot write %s', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, 'name,value,unit,description,scope,path,dtype,minimum,maximum,group\n');
    for index = 1:numel(rows)
        row = rows(index);
        cells = {row.name, row.value_text, row.unit, row.description, row.scope, ...
            row.path, row.dtype, bound_text(row.minimum), bound_text(row.maximum), row.group};
        escaped = cell(1, numel(cells));
        for column = 1:numel(cells)
            escaped{column} = csv_escape(cells{column}, ',');
        end
        fprintf(fid, '%s\n', strjoin(escaped, ','));
    end
end

function text = bound_text(value)
    if isempty(value) || (isnumeric(value) && isscalar(value) && isnan(value))
        text = '';
    else
        text = format_double(value);
    end
end

function text = csv_escape(value, delimiter)
    needs = contains(value, '"') || contains(value, delimiter) || ...
        contains(value, char(10)) || contains(value, char(13));
    if needs
        text = ['"' strrep(value, '"', '""') '"'];
    else
        text = value;
    end
end

function text = format_param_table(rows)
    lines = cell(1, numel(rows) + 1);
    lines{1} = sprintf('%-12s %-8s %-10s %-12s %-10s %-22s %-12s', ...
        'name', 'dtype', 'value', 'unit', 'scope', 'path', 'group');
    for index = 1:numel(rows)
        row = rows(index);
        lines{index + 1} = sprintf('%-12s %-8s %-10s %-12s %-10s %-22s %-12s', ...
            row.name, row.dtype, row.value_text, row.unit, row.scope, row.path, row.group);
    end
    text = strjoin(lines, newline);
end

function text = format_assignments(rows)
    models = {};
    for index = 1:numel(rows)
        if strcmp(rows(index).scope, 'workspace')
            models{end + 1} = rows(index).path; %#ok<AGROW>
        end
    end
    models = unique(models);
    lines = {};
    for modelIndex = 1:numel(models)
        names = {};
        texts = {};
        for index = 1:numel(rows)
            row = rows(index);
            if strcmp(row.scope, 'workspace') && strcmp(row.path, models{modelIndex})
                names{end + 1} = row.name; %#ok<AGROW>
                texts{end + 1} = row.value_text; %#ok<AGROW>
            end
        end
        [names, order] = sort(names);
        texts = texts(order);
        bits = cell(1, numel(names));
        for nameIndex = 1:numel(names)
            bits{nameIndex} = sprintf('%s=%s', names{nameIndex}, texts{nameIndex});
        end
        lines{end + 1} = sprintf('workspace %s: %s', models{modelIndex}, strjoin(bits, ', ')); %#ok<AGROW>
    end
    baseNames = {};
    baseTexts = {};
    for index = 1:numel(rows)
        if strcmp(rows(index).scope, 'base')
            baseNames{end + 1} = rows(index).name; %#ok<AGROW>
            baseTexts{end + 1} = rows(index).value_text; %#ok<AGROW>
        end
    end
    if ~isempty(baseNames)
        [baseNames, order] = sort(baseNames);
        baseTexts = baseTexts(order);
        bits = cell(1, numel(baseNames));
        for nameIndex = 1:numel(baseNames)
            bits{nameIndex} = sprintf('%s=%s', baseNames{nameIndex}, baseTexts{nameIndex});
        end
        lines{end + 1} = sprintf('base: %s', strjoin(bits, ', ')); %#ok<AGROW>
    end
    text = strjoin(lines, newline);
end

function [workspace, base] = build_assignments(rows)
    workspace = struct();
    base = struct();
    for index = 1:numel(rows)
        row = rows(index);
        if strcmp(row.scope, 'workspace')
            if ~isfield(workspace, row.path)
                workspace.(row.path) = struct();
            end
            workspace.(row.path).(row.name) = row.value;
        elseif strcmp(row.scope, 'base')
            base.(row.name) = row.value;
        end
    end
end

function row = empty_row()
    row = struct( ...
        'name', '', ...
        'value', [], ...
        'value_text', '', ...
        'unit', '', ...
        'description', '', ...
        'scope', '', ...
        'path', '', ...
        'dtype', '', ...
        'minimum', NaN, ...
        'maximum', NaN, ...
        'group', '', ...
        'row_number', 0);
end

function issue = make_issue(field, rowNumber, detail)
    issue = struct('row_number', rowNumber, 'field', field, 'message', '');
    if rowNumber > 0
        issue.message = sprintf('%s: row %d %s', field, rowNumber, detail);
    else
        issue.message = sprintf('%s: %s', field, detail);
    end
end

function issues = empty_issues()
    issues = repmat(struct('row_number', 0, 'field', '', 'message', ''), 1, 0);
end

function issues = sort_issues(issues)
    n = numel(issues);
    if n < 2
        return
    end
    keys = zeros(1, n);
    for index = 1:n
        keys(index) = issues(index).row_number * 100 + field_rank(issues(index).field);
    end
    [~, order] = sort(keys, 'ascend');
    issues = issues(order);
end

function rank = field_rank(field)
    order = {'header', 'name', 'scope', 'path', 'dtype', 'value', 'unit', ...
        'description', 'group', 'minimum', 'maximum', 'duplicate'};
    found = find(strcmp(order, field), 1);
    if isempty(found)
        rank = 99;
    else
        rank = found;
    end
end

function n = count_char(text, ch)
    n = sum(text == ch);
end
