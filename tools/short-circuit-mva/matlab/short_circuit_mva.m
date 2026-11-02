function result = short_circuit_mva(varargin)
%SHORT_CIRCUIT_MVA Short-circuit MVA, current, and impedance.
%   RESULT = SHORT_CIRCUIT_MVA('s_mva', 250, 'v_kv', 10)
%   RESULT = SHORT_CIRCUIT_MVA('i_ka', 10, 'v_kv', 10)
%   RESULT = SHORT_CIRCUIT_MVA('kind', 'transformer', 's_rated_mva', 20, ...
%       'z_percent', 8, 'x_over_r', 10)
%   RESULT = SHORT_CIRCUIT_MVA('stages.csv', 'output_csv', 'out.csv', ...
%       'output_png', 'mva.png', 'show', false)
%
%   Three-phase (default). V is the line-to-line study voltage. S is the
%   three-phase short-circuit capacity. I is the bolted fault current.
%   Z is the per-phase equivalent impedance at that voltage.
%       S = sqrt(3) * V * I = V^2 / |Z|
%       I = S / (sqrt(3) * V)
%       |Z| = V^2 / S
%       Z_pu = S_base / S
%       Z_base = V^2 / S_base
%   Single-phase drops sqrt(3) in the current. |Z| = V^2 / S is unchanged.
%
%   A transformer impedance on its own rating becomes
%   S = S_rated / z_pu. z_percent is 100 * z_pu, so 8 means 8 percent.
%
%   Stages fold left to right by the magnitude MVA method. The first row
%   is the seed. series uses 1/S_eq = 1/S_run + 1/S_next. parallel uses
%   S_eq = S_run + S_next. Ohmic R and X are at v_kv; they are not referred
%   across a winding. Omitted x_over_r means pure +jX.
%
%   R and X are also folded as phasors. S_complex = V^2 / |Z_phasor|.
%   It matches the MVA method when every stage has the same X/R.
%
%   Name-value keys match Python: name, kind, combine, s_mva, s_va, i_ka,
%   i_a, z_ohm, r_ohm, x_ohm, z_pu, z_percent, s_rated_mva, x_over_r, v_kv,
%   v_v, s_base_mva, system, csv_path, output_csv, output_png, show.
%
%   RESULT.summary is the same text Python prints.

    [source, rest] = split_source(varargin);
    assert_pairs(rest);
    parser = inputParser;
    parser.FunctionName = 'short_circuit_mva';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('name', '', @is_text_scalar);
    parser.addParameter('kind', '', @is_text_scalar);
    parser.addParameter('combine', '', @is_text_scalar);
    parser.addParameter('s_mva', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('s_va', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('i_ka', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('i_a', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('z_ohm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('r_ohm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('x_ohm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('z_pu', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('z_percent', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('s_rated_mva', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('x_over_r', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('v_kv', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('v_v', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('s_base_mva', 100, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('system', 'three_phase', @is_text_scalar);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    systemName = normalize_system(opt.system);
    [volts, voltsKv] = study_voltage(opt.v_kv, opt.v_v);
    baseMva = positive_number('s_base_mva', opt.s_base_mva);
    if strcmp(systemName, 'three_phase')
        phase = sqrt(3);
    else
        phase = 1;
    end
    baseVa = baseMva * 1e6;
    zBase = (volts * volts) / baseVa;
    iBase = baseVa / (phase * volts);

    rawRows = resolve_rows(source, rest, opt);
    nRows = numel(rawRows);
    drafts = repmat(draft_template(), 1, nRows);
    for index = 1:nRows
        drafts(index) = parse_element(rawRows{index}, index, volts, phase, baseMva);
    end
    [elements, rEq, xEq] = fold_elements(drafts, volts, phase, baseMva);
    final = elements(end);
    zComplex = hypot(rEq, xEq);
    if ~(zComplex > 1e-15)
        error('short_circuit_mva:Impedance', ...
            ['equivalent phasor impedance is zero (the reactances cancel). ', ...
            'The magnitude MVA method ignores this; keep X signs consistent or drop x_over_r']);
    end
    sComplex = (volts * volts) / zComplex;
    iComplex = sComplex / (phase * volts);

    outputCsv = strtrim(to_char(opt.output_csv));
    outputPng = strtrim(to_char(opt.output_png));
    showFig = logical(opt.show);
    if ~isempty(outputCsv)
        write_elements_csv(outputCsv, elements);
    end

    result = struct();
    result.method = 'mva';
    result.system = systemName;
    result.v_v = volts;
    result.v_kv = voltsKv;
    result.s_base_va = baseVa;
    result.s_base_mva = baseMva;
    result.z_base_ohm = zBase;
    result.i_base_a = iBase;
    result.i_base_ka = iBase / 1000;
    result.elements = elements;
    result.s_va = final.s_running_mva * 1e6;
    result.s_mva = final.s_running_mva;
    result.i_a = final.i_running_a;
    result.i_ka = final.i_running_ka;
    result.z_ohm = final.z_running_ohm;
    result.z_pu = baseMva / final.s_running_mva;
    result.r_ohm = rEq;
    result.x_ohm = xEq;
    result.x_over_r = xr_of(rEq, xEq);
    result.angle_deg = atan2(xEq, rEq) * 180 / pi;
    result.z_complex_ohm = zComplex;
    result.s_va_complex = sComplex;
    result.s_mva_complex = sComplex / 1e6;
    result.i_a_complex = iComplex;
    result.i_ka_complex = iComplex / 1000;
    result.summary = '';
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = [];
    result.summary = format_summary(result);
    if ~isempty(outputPng) || showFig
        result.fig = render_figure(result, outputPng, showFig);
    end
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

function assert_pairs(rest)
    % Octave's inputParser drops a leading struct instead of rejecting it.
    for index = 1:2:numel(rest)
        if ~is_parameter_name(rest{index})
            error('short_circuit_mva:BadOption', ...
                ['pass stages as one struct array or one cell of structs; ', ...
                'options are name-value pairs']);
        end
    end
    if mod(numel(rest), 2) ~= 0
        error('short_circuit_mva:BadOption', 'name-value arguments must come in pairs');
    end
end

function tf = is_parameter_name(value)
    if ischar(value) || (is_matlab_string(value) && isscalar(value))
        text = to_char(value);
    else
        tf = false;
        return
    end
    keys = {'name', 'kind', 'combine', 's_mva', 's_va', 'i_ka', 'i_a', ...
        'z_ohm', 'r_ohm', 'x_ohm', 'z_pu', 'z_percent', 's_rated_mva', ...
        'x_over_r', 'v_kv', 'v_v', 's_base_mva', 'system', 'csv_path', ...
        'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(text), keys));
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = is_matlab_string(value) && isscalar(value);
end

function tf = was_passed(rest, key)
    tf = false;
    for index = 1:2:numel(rest)
        if is_parameter_name(rest{index}) && strcmpi(strtrim(to_char(rest{index})), key)
            tf = true;
            return
        end
    end
end

function data = direct_struct(opt, rest)
    keys = {'name', 'kind', 'combine', 's_mva', 's_va', 'i_ka', 'i_a', ...
        'z_ohm', 'r_ohm', 'x_ohm', 'z_pu', 'z_percent', 's_rated_mva', 'x_over_r'};
    data = struct();
    for index = 1:numel(keys)
        key = keys{index};
        if was_passed(rest, key)
            data.(key) = opt.(key);
        end
    end
end

function rawRows = resolve_rows(source, rest, opt)
    direct = direct_struct(opt, rest);
    hasDirect = ~isempty(fieldnames(direct));
    csvText = strtrim(to_char(opt.csv_path));
    mapMode = false;
    mapRows = {};
    if ischar(source) || (is_matlab_string(source) && isscalar(source))
        text = strtrim(to_char(source));
        if ~isempty(text)
            if is_parameter_name(text)
                error('short_circuit_mva:BadOption', ...
                    ['%s is a parameter name. Pass the CSV path as csv_path ', ...
                    'or as the first argument'], text);
            end
            if ~isempty(csvText)
                error('short_circuit_mva:BadOption', ...
                    'pass a CSV path once, either positionally or as csv_path');
            end
            if hasDirect
                error('short_circuit_mva:BadOption', ...
                    'pass a CSV path or one element''s arguments, not both');
            end
            csvText = text;
        end
    elseif isstruct(source) || iscell(source)
        if ~isempty(csvText) || hasDirect
            error('short_circuit_mva:BadOption', ...
                'pass a CSV path, row mappings, or one element''s arguments, not more than one');
        end
        mapMode = true;
        if isstruct(source)
            mapRows = cell(1, numel(source));
            for index = 1:numel(source)
                mapRows{index} = source(index);
            end
        else
            if isempty(source)
                error('short_circuit_mva:BadOption', 'element list is empty');
            end
            mapRows = source(:).';
        end
    elseif ~isempty(source)
        error('short_circuit_mva:BadOption', ...
            'source must be a CSV path, a struct, or a cell of structs');
    end

    if ~isempty(csvText) && hasDirect
        error('short_circuit_mva:BadOption', ...
            'pass a CSV path or one element''s arguments, not both');
    end
    if ~isempty(csvText)
        rawRows = read_stage_csv(csvText);
        return
    end
    if mapMode
        if isempty(mapRows)
            error('short_circuit_mva:BadOption', 'element list is empty');
        end
        rawRows = mapRows;
        return
    end
    if hasDirect
        rawRows = {direct};
        return
    end
    error('short_circuit_mva:BadOption', ...
        'pass a stage CSV or one element (S, I, Z, or a transformer/pu impedance)');
end

function systemName = normalize_system(value)
    switch normalize_key(value)
        case {'threephase', '3phase', '3ph'}
            systemName = 'three_phase';
        case {'singlephase', '1phase', '1ph'}
            systemName = 'single_phase';
        otherwise
            error('short_circuit_mva:BadOption', ...
                'system must be ''three_phase'' or ''single_phase''');
    end
end

function [volts, voltsKv] = study_voltage(vKv, vV)
    hasKv = ~isempty(vKv);
    hasV = ~isempty(vV);
    if hasKv && hasV
        error('short_circuit_mva:BadOption', 'pass v_kv or v_v, not both');
    end
    if hasV
        volts = positive_number('v_v', vV);
        voltsKv = volts / 1000;
        return
    end
    if ~hasKv
        vKv = 10;
    end
    voltsKv = positive_number('v_kv', vKv);
    volts = voltsKv * 1000;
end

function number = positive_number(name, value)
    number = finite_number(name, value, false);
    if ~(number > 0)
        error('short_circuit_mva:BadOption', '%s must be a positive finite number', name);
    end
end

function number = finite_number(name, value, allowInf)
    if iscell(value)
        if numel(value) ~= 1
            error('short_circuit_mva:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if ischar(value) || is_matlab_string(value)
        text = strtrim(to_char(value));
        lowerText = lower(text);
        if allowInf && any(strcmp(lowerText, {'inf', '+inf', 'infinity', '+infinity'}))
            number = Inf;
            return
        end
        if allowInf && any(strcmp(lowerText, {'-inf', '-infinity'}))
            number = -Inf;
            return
        end
        number = str2double(text);
    elseif isnumeric(value)
        number = double(value);
    else
        error('short_circuit_mva:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number)
        error('short_circuit_mva:BadOption', '%s must be a finite number', name);
    end
    if allowInf && isinf(number)
        return
    end
    if ~isfinite(number)
        error('short_circuit_mva:BadOption', '%s must be a finite number', name);
    end
end

function number = optional_number(label, data, field, allowInf)
    if nargin < 4
        allowInf = false;
    end
    if ~isfield(data, field) || is_blank(data.(field))
        number = [];
        return
    end
    number = finite_number(label, data.(field), allowInf);
end

function rows = read_stage_csv(csvPath)
    if exist(csvPath, 'file') ~= 2
        error('short_circuit_mva:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if numel(raw) >= 3 && raw(1) == char(239) && raw(2) == char(187) && raw(3) == char(191)
        raw = raw(4:end);
    end
    raw = strrep(raw, char(13), '');
    if isempty(strtrim(raw))
        error('short_circuit_mva:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    lines = split_lines(raw);
    headerLine = '';
    dataLines = {};
    started = false;
    for index = 1:numel(lines)
        if isempty(strtrim(lines{index}))
            continue
        end
        if ~started
            headerLine = lines{index};
            started = true;
        else
            dataLines{end + 1} = lines{index}; %#ok<AGROW>
        end
    end
    if isempty(headerLine)
        error('short_circuit_mva:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    if any(headerLine == ',')
        delimiter = ',';
    elseif any(headerLine == ';')
        delimiter = ';';
    else
        delimiter = ',';
    end
    headers = split_line(headerLine, delimiter);
    canons = cell(1, numel(headers));
    for col = 1:numel(headers)
        norm = normalize_key(headers{col});
        if isempty(norm)
            canons{col} = '';
            continue
        end
        canon = column_alias(norm);
        if isempty(canon)
            error('short_circuit_mva:BadOption', 'unknown column ''%s''', strtrim(headers{col}));
        end
        canons{col} = canon;
    end
    rows = cell(1, numel(dataLines));
    kept = 0;
    for rowIndex = 1:numel(dataLines)
        cells = split_line(dataLines{rowIndex}, delimiter);
        if numel(cells) ~= numel(headers)
            error('short_circuit_mva:BadOption', ...
                'CSV row %d has %d columns, header has %d', ...
                rowIndex, numel(cells), numel(headers));
        end
        if all(cellfun(@(value) isempty(strtrim(value)), cells))
            continue
        end
        item = struct();
        for col = 1:numel(canons)
            if isempty(canons{col})
                continue
            end
            value = strtrim(cells{col});
            canon = canons{col};
            if isfield(item, canon) && ~isempty(strtrim(item.(canon))) && ~isempty(value)
                error('short_circuit_mva:BadOption', 'duplicate column %s', canon);
            end
            if ~isfield(item, canon) || ~isempty(value)
                item.(canon) = value;
            end
        end
        kept = kept + 1;
        rows{kept} = item;
    end
    rows = rows(1:kept);
    if kept == 0
        error('short_circuit_mva:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function lines = split_lines(raw)
    lines = {};
    rest = char(raw);
    while true
        pos = find(rest == char(10), 1, 'first');
        if isempty(pos)
            lines{end + 1} = rest; %#ok<AGROW>
            break
        end
        lines{end + 1} = rest(1:pos - 1); %#ok<AGROW>
        rest = rest(pos + 1:end);
    end
end

function cells = split_line(line, delimiter)
    cells = {};
    rest = char(line);
    while true
        pos = find(rest == delimiter, 1, 'first');
        if isempty(pos)
            cells{end + 1} = strtrim(rest); %#ok<AGROW>
            break
        end
        cells{end + 1} = strtrim(rest(1:pos - 1)); %#ok<AGROW>
        rest = rest(pos + 1:end);
    end
end

function canon = column_alias(key)
    switch key
        case {'name', 'element', 'id'}
            canon = 'name';
        case {'kind', 'type'}
            canon = 'kind';
        case {'combine', 'connection'}
            canon = 'combine';
        case {'smva', 's', 'ssc', 'sscmva', 'mva'}
            canon = 's_mva';
        case 'sva'
            canon = 's_va';
        case {'ika', 'ka', 'currentka'}
            canon = 'i_ka';
        case {'ia', 'i', 'current', 'amp', 'amps'}
            canon = 'i_a';
        case {'zohm', 'z', 'impedance'}
            canon = 'z_ohm';
        case {'rohm', 'r', 'resistance'}
            canon = 'r_ohm';
        case {'xohm', 'x', 'reactance'}
            canon = 'x_ohm';
        case {'zpu', 'pu', 'perunit'}
            canon = 'z_pu';
        case {'zpercent', 'zpct', 'uk', 'ukpercent'}
            canon = 'z_percent';
        case {'sratedmva', 'srated', 'sn', 'snmva', 'ratingmva'}
            canon = 's_rated_mva';
        case {'xoverr', 'xr'}
            canon = 'x_over_r';
        otherwise
            canon = '';
    end
end

function raw = canonicalize(data)
    if ~isstruct(data) || numel(data) ~= 1
        error('short_circuit_mva:BadOption', 'each element must be a scalar struct');
    end
    names = fieldnames(data);
    raw = struct();
    for index = 1:numel(names)
        key = names{index};
        norm = normalize_key(key);
        if isempty(norm)
            continue
        end
        canon = column_alias(norm);
        if isempty(canon)
            error('short_circuit_mva:BadOption', 'unknown column ''%s''', key);
        end
        value = data.(key);
        if isfield(raw, canon) && ~is_blank(raw.(canon)) && ~is_blank(value)
            error('short_circuit_mva:BadOption', 'duplicate column %s', canon);
        end
        if ~isfield(raw, canon) || ~is_blank(value)
            raw.(canon) = value;
        end
    end
end

function draft = parse_element(data, index, volts, phase, sBaseMva)
    raw = canonicalize(data);
    name = as_char(struct_get(raw, 'name'));
    if isempty(name)
        name = sprintf('element%d', index);
    end
    sMva = optional_number('s_mva', raw, 's_mva');
    sVa = optional_number('s_va', raw, 's_va');
    iKa = optional_number('i_ka', raw, 'i_ka');
    iA = optional_number('i_a', raw, 'i_a');
    zOhm = optional_number('z_ohm', raw, 'z_ohm');
    rOhm = optional_number('r_ohm', raw, 'r_ohm');
    xOhm = optional_number('x_ohm', raw, 'x_ohm');
    zPu = optional_number('z_pu', raw, 'z_pu');
    zPercent = optional_number('z_percent', raw, 'z_percent');
    sRated = optional_number('s_rated_mva', raw, 's_rated_mva');
    xOverR = optional_number('x_over_r', raw, 'x_over_r', true);
    combine = as_char(struct_get(raw, 'combine'));

    hasSource = ~isempty(sMva) || ~isempty(sVa);
    hasCurrent = ~isempty(iKa) || ~isempty(iA);
    hasZ = ~isempty(zOhm) || ~isempty(rOhm) || ~isempty(xOhm);
    hasRated = ~isempty(sRated);
    hasPu = ~hasRated && (~isempty(zPu) || ~isempty(zPercent));
    if hasRated && isempty(zPu) && isempty(zPercent)
        error('short_circuit_mva:BadOption', ...
            '%s: transformer requires z_percent or z_pu', name);
    end
    if ~isempty(zPu) && ~isempty(zPercent)
        error('short_circuit_mva:BadOption', '%s: pass z_percent or z_pu, not both', name);
    end
    groups = {};
    if hasSource
        groups{end + 1} = 'source'; %#ok<AGROW>
    end
    if hasCurrent
        groups{end + 1} = 'current'; %#ok<AGROW>
    end
    if hasZ
        groups{end + 1} = 'impedance'; %#ok<AGROW>
    end
    if hasRated
        groups{end + 1} = 'transformer'; %#ok<AGROW>
    end
    if hasPu
        groups{end + 1} = 'pu'; %#ok<AGROW>
    end
    if isempty(groups)
        error('short_circuit_mva:BadOption', ...
            ['%s: a short-circuit specification is required ', ...
            '(S, I, Z, or a transformer/pu impedance)'], name);
    end
    if numel(groups) > 1
        error('short_circuit_mva:BadOption', ...
            '%s: pass one short-circuit specification, not %s', name, strjoin(groups, ' and '));
    end
    group = groups{1};
    kind = resolve_kind(as_char(struct_get(raw, 'kind')), group, name);
    zSpec = NaN;
    rated = NaN;
    if strcmp(group, 'source')
        [power, resistance, reactance] = from_power(sMva, sVa, volts, xOverR, name);
    elseif strcmp(group, 'current')
        [power, resistance, reactance] = from_current(iKa, iA, volts, phase, xOverR, name);
    elseif strcmp(group, 'impedance')
        [power, resistance, reactance] = from_impedance(zOhm, rOhm, xOhm, xOverR, volts, name);
    elseif strcmp(group, 'transformer')
        zSpec = spec_pu(zPercent, zPu, name);
        rated = positive_number(sprintf('%s: s_rated_mva', name), sRated);
        power = (rated * 1e6) / zSpec;
        [resistance, reactance] = rx_from_magnitude((volts * volts) / power, xOverR);
    else
        zSpec = spec_pu(zPercent, zPu, name);
        power = (sBaseMva * 1e6) / zSpec;
        [resistance, reactance] = rx_from_magnitude((volts * volts) / power, xOverR);
    end
    if ~(power > 0) || ~isfinite(power)
        error('short_circuit_mva:BadOption', '%s: short-circuit capacity must be positive', name);
    end
    draft = draft_template();
    draft.name = name;
    draft.kind = kind;
    draft.combine = combine;
    draft.s_mva = power / 1e6;
    draft.s_va = power;
    draft.r_ohm = resistance;
    draft.x_ohm = reactance;
    draft.z_spec_pu = zSpec;
    draft.s_rated_mva = rated;
end

function kind = resolve_kind(token, group, label)
    if isempty(token)
        kind = group;
        return
    end
    switch normalize_key(token)
        case {'source', 'mva', 'grid', 'utility'}
            expect = 'source';
            public = 'source';
        case 'current'
            expect = 'current';
            public = 'current';
        case 'impedance'
            expect = 'impedance';
            public = 'impedance';
        case {'line', 'cable', 'feeder'}
            expect = 'impedance';
            public = 'line';
        case {'transformer', 'tx', 'trafo'}
            expect = 'transformer';
            public = 'transformer';
        case {'pu', 'perunit'}
            expect = 'pu';
            public = 'pu';
        otherwise
            error('short_circuit_mva:BadOption', ...
                '%s: kind must be source, current, impedance, line, transformer, or pu', label);
    end
    if ~strcmp(expect, group)
        error('short_circuit_mva:BadOption', ...
            '%s: kind ''%s'' does not match the fields for a %s element', label, public, group);
    end
    kind = public;
end

function zSpec = spec_pu(zPercent, zPu, label)
    if ~isempty(zPercent)
        if ~(zPercent > 0)
            error('short_circuit_mva:BadOption', ...
                '%s: z_percent must be a positive finite number (8 means 8%%)', label);
        end
        zSpec = zPercent / 100;
        return
    end
    if isempty(zPu) || ~(zPu > 0)
        error('short_circuit_mva:BadOption', '%s: z_pu must be a positive finite number', label);
    end
    zSpec = zPu;
end

function [power, resistance, reactance] = from_power(sMva, sVa, volts, xOverR, label)
    if ~isempty(sMva) && ~isempty(sVa)
        error('short_circuit_mva:BadOption', '%s: pass s_mva or s_va, not both', label);
    end
    if ~isempty(sVa)
        power = positive_number(sprintf('%s: s_va', label), sVa);
    else
        power = positive_number(sprintf('%s: s_mva', label), sMva) * 1e6;
    end
    [resistance, reactance] = rx_from_magnitude((volts * volts) / power, xOverR);
end

function [power, resistance, reactance] = from_current(iKa, iA, volts, phase, xOverR, label)
    if ~isempty(iKa) && ~isempty(iA)
        error('short_circuit_mva:BadOption', '%s: pass i_ka or i_a, not both', label);
    end
    if ~isempty(iKa)
        current = positive_number(sprintf('%s: i_ka', label), iKa) * 1000;
    else
        current = positive_number(sprintf('%s: i_a', label), iA);
    end
    power = phase * volts * current;
    [resistance, reactance] = rx_from_magnitude((volts * volts) / power, xOverR);
end

function [power, resistance, reactance] = from_impedance(zOhm, rOhm, xOhm, xOverR, volts, label)
    if ~isempty(zOhm) && (~isempty(rOhm) || ~isempty(xOhm))
        error('short_circuit_mva:BadOption', '%s: pass z_ohm or r_ohm/x_ohm, not both', label);
    end
    if ~isempty(zOhm)
        magnitude = positive_number(sprintf('%s: z_ohm', label), zOhm);
        [resistance, reactance] = rx_from_magnitude(magnitude, xOverR);
    else
        [resistance, reactance] = complete_rx(rOhm, xOhm, xOverR, label);
    end
    magnitude = hypot(resistance, reactance);
    if ~(magnitude > 0)
        error('short_circuit_mva:BadOption', '%s: impedance magnitude must be positive', label);
    end
    power = (volts * volts) / magnitude;
end

function [resistance, reactance] = rx_from_magnitude(magnitude, xOverR)
    if isempty(xOverR) || (isinf(xOverR) && xOverR > 0)
        resistance = 0;
        reactance = magnitude;
        return
    end
    if isinf(xOverR)
        resistance = 0;
        reactance = -magnitude;
        return
    end
    scale = sqrt(1 + xOverR * xOverR);
    resistance = magnitude / scale;
    reactance = resistance * xOverR;
end

function [resistance, reactance] = complete_rx(rOhm, xOhm, xOverR, label)
    if ~isempty(rOhm) && ~(rOhm >= 0)
        error('short_circuit_mva:BadOption', '%s: resistance must be >= 0', label);
    end
    if ~isempty(rOhm) && ~isempty(xOhm)
        if ~isempty(xOverR)
            check_xr(rOhm, xOhm, xOverR, label);
        end
        resistance = rOhm;
        reactance = xOhm;
        return
    end
    if ~isempty(rOhm) && isempty(xOhm) && isempty(xOverR)
        resistance = rOhm;
        reactance = 0;
        return
    end
    if ~isempty(xOhm) && isempty(rOhm) && isempty(xOverR)
        resistance = 0;
        reactance = xOhm;
        return
    end
    if ~isempty(rOhm) && ~isempty(xOverR)
        if isinf(xOverR)
            error('short_circuit_mva:BadOption', ...
                '%s: x_over_r is infinite; pass x_ohm instead of r_ohm', label);
        end
        resistance = rOhm;
        reactance = xOverR * rOhm;
        return
    end
    if ~isempty(xOhm) && ~isempty(xOverR)
        if xOverR == 0
            if xOhm ~= 0
                error('short_circuit_mva:BadOption', '%s: x_over_r is 0; x_ohm must be 0', label);
            end
            resistance = 0;
            reactance = 0;
            return
        end
        if isinf(xOverR)
            if (xOverR > 0 && xOhm < 0) || (xOverR < 0 && xOhm > 0)
                error('short_circuit_mva:BadOption', '%s: x_over_r does not match x_ohm', label);
            end
            resistance = 0;
            reactance = xOhm;
            return
        end
        resistance = xOhm / xOverR;
        if resistance < 0
            error('short_circuit_mva:BadOption', '%s: resistance must be >= 0', label);
        end
        reactance = xOhm;
        return
    end
    error('short_circuit_mva:BadOption', '%s: resistance or reactance is required', label);
end

function check_xr(rOhm, xOhm, xOverR, label)
    if rOhm == 0
        positive = xOhm > 0 && isinf(xOverR) && xOverR > 0;
        negative = xOhm < 0 && isinf(xOverR) && xOverR < 0;
        if ~(positive || negative)
            error('short_circuit_mva:BadOption', ...
                '%s: x_over_r does not match r_ohm and x_ohm', label);
        end
        return
    end
    if isinf(xOverR)
        error('short_circuit_mva:BadOption', ...
            '%s: x_over_r does not match r_ohm and x_ohm', label);
    end
    ratio = xOhm / rOhm;
    tol = max([1e-6 * max(abs(ratio), abs(xOverR)), 1e-6]);
    if abs(ratio - xOverR) > tol
        error('short_circuit_mva:BadOption', ...
            '%s: x_over_r does not match r_ohm and x_ohm', label);
    end
end

function value = xr_of(rOhm, xOhm)
    if rOhm == 0
        if xOhm > 0
            value = Inf;
        elseif xOhm < 0
            value = -Inf;
        else
            value = NaN;
        end
    else
        value = xOhm / rOhm;
    end
end

function [resistance, reactance] = parallel_z(r1, x1, r2, x2)
    realNum = r1 * r2 - x1 * x2;
    imagNum = r1 * x2 + x1 * r2;
    realDen = r1 + r2;
    imagDen = x1 + x2;
    denom = realDen * realDen + imagDen * imagDen;
    if denom == 0
        error('short_circuit_mva:Impedance', ...
            'parallel combination is undefined (the two impedances are opposite)');
    end
    resistance = (realNum * realDen + imagNum * imagDen) / denom;
    reactance = (imagNum * realDen - realNum * imagDen) / denom;
end

function [rOhm, xOhm] = clean_rx(rOhm, xOhm)
    magnitude = hypot(rOhm, xOhm);
    if magnitude == 0
        rOhm = 0;
        xOhm = 0;
        return
    end
    tol = magnitude * 1e-12;
    if abs(rOhm) <= tol
        rOhm = 0;
    end
    if abs(xOhm) <= tol
        xOhm = 0;
    end
    if rOhm < 0 && abs(rOhm) <= magnitude * 1e-9
        rOhm = 0;
    end
end

function combine = normalize_combine(value, label)
    if isempty(value)
        combine = 'series';
        return
    end
    switch normalize_key(value)
        case {'series', 'serial', 'cascade'}
            combine = 'series';
        case {'parallel', 'shunt'}
            combine = 'parallel';
        otherwise
            error('short_circuit_mva:BadOption', ...
                '%s: combine must be ''series'' or ''parallel''', label);
    end
end

function [elements, rEq, xEq] = fold_elements(drafts, volts, phase, sBaseMva)
    nRows = numel(drafts);
    elements = repmat(element_template(), 1, nRows);
    sRun = drafts(1).s_mva;
    rComplex = drafts(1).r_ohm;
    xComplex = drafts(1).x_ohm;
    for index = 1:nRows
        draft = drafts(index);
        if index == 1
            if ~isempty(draft.combine)
                normalize_combine(draft.combine, draft.name);
            end
            combine = 'seed';
        else
            combine = normalize_combine(draft.combine, draft.name);
            if strcmp(combine, 'series')
                sRun = (sRun * draft.s_mva) / (sRun + draft.s_mva);
                rComplex = rComplex + draft.r_ohm;
                xComplex = xComplex + draft.x_ohm;
            else
                sRun = sRun + draft.s_mva;
                [rComplex, xComplex] = parallel_z(rComplex, xComplex, draft.r_ohm, draft.x_ohm);
            end
        end
        zOwn = (volts * volts) / draft.s_va;
        iOwn = draft.s_va / (phase * volts);
        zRun = (volts * volts) / (sRun * 1e6);
        iRun = (sRun * 1e6) / (phase * volts);
        row = element_template();
        row.name = draft.name;
        row.kind = draft.kind;
        row.combine = combine;
        row.s_mva = draft.s_mva;
        row.s_va = draft.s_va;
        row.z_ohm = zOwn;
        row.r_ohm = draft.r_ohm;
        row.x_ohm = draft.x_ohm;
        row.x_over_r = xr_of(draft.r_ohm, draft.x_ohm);
        row.z_pu = sBaseMva / draft.s_mva;
        row.z_spec_pu = draft.z_spec_pu;
        row.s_rated_mva = draft.s_rated_mva;
        row.i_a = iOwn;
        row.i_ka = iOwn / 1000;
        row.s_running_mva = sRun;
        row.z_running_ohm = zRun;
        row.i_running_a = iRun;
        row.i_running_ka = iRun / 1000;
        elements(index) = row;
    end
    [rEq, xEq] = clean_rx(rComplex, xComplex);
end

function text = format_summary(result)
    nRows = numel(result.elements);
    lines = cell(1, nRows + 3);
    lines{1} = sprintf(['method=%s  system=%s  V=%.4f kV  ', ...
        'S_base=%.4f MVA  Z_base=%.4f ohm  I_base=%.4f kA'], ...
        result.method, result.system, result.v_kv, ...
        result.s_base_mva, result.z_base_ohm, result.i_base_ka);
    lines{2} = sprintf('%-10s %-12s %-8s %10s %9s %8s %10s %9s', ...
        'element', 'kind', 'combine', 'S_MVA', 'Z_ohm', 'X/R', 'Srun_MVA', 'Irun_kA');
    for index = 1:nRows
        row = result.elements(index);
        lines{index + 2} = sprintf('%-10s %-12s %-8s %10.4f %9.4f %8s %10.4f %9.4f', ...
            row.name, row.kind, row.combine, row.s_mva, row.z_ohm, ...
            xr_text(row.x_over_r), row.s_running_mva, row.i_running_ka);
    end
    lines{nRows + 3} = sprintf(['S_sc=%.4f MVA  I_sc=%.4f kA  ', ...
        'Z=%.4f ohm  z_pu=%.4f pu  X/R=%s  angle=%.4f deg  ', ...
        'S_complex=%.4f MVA  Z_complex=%.4f ohm'], ...
        result.s_mva, result.i_ka, result.z_ohm, result.z_pu, ...
        xr_text(result.x_over_r), result.angle_deg, ...
        result.s_mva_complex, result.z_complex_ohm);
    text = strjoin(lines, char(10));
end

function text = xr_text(value)
    if isnan(value)
        text = 'nan';
    elseif isinf(value)
        if value < 0
            text = '-inf';
        else
            text = 'inf';
        end
    else
        text = sprintf('%.4f', value);
    end
end

function write_elements_csv(csvPath, elements)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fields = {'name', 'kind', 'combine', 's_mva', 's_va', 'z_ohm', 'r_ohm', 'x_ohm', ...
        'x_over_r', 'z_pu', 'z_spec_pu', 's_rated_mva', 'i_a', 'i_ka', ...
        's_running_mva', 'z_running_ohm', 'i_running_a', 'i_running_ka'};
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('short_circuit_mva:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s\n', strjoin(fields, ','));
    for index = 1:numel(elements)
        row = elements(index);
        fprintf(fid, '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n', ...
            csv_cell(row.name), csv_cell(row.kind), csv_cell(row.combine), ...
            csv_num(row.s_mva), csv_num(row.s_va), csv_num(row.z_ohm), ...
            csv_num(row.r_ohm), csv_num(row.x_ohm), csv_num(row.x_over_r), ...
            csv_num(row.z_pu), csv_num(row.z_spec_pu), csv_num(row.s_rated_mva), ...
            csv_num(row.i_a), csv_num(row.i_ka), csv_num(row.s_running_mva), ...
            csv_num(row.z_running_ohm), csv_num(row.i_running_a), csv_num(row.i_running_ka));
    end
end

function text = csv_num(value)
    if isnan(value)
        text = '';
    elseif isinf(value)
        if value < 0
            text = '-inf';
        else
            text = 'inf';
        end
    else
        text = sprintf('%.12g', value);
    end
end

function text = csv_cell(value)
    text = to_char(value);
    if any(text == ',') || any(text == '"') || any(text == char(10)) || any(text == char(13))
        text = ['"', strrep(text, '"', '""'), '"'];
    end
end

function fig = render_figure(result, outputPng, showFig)
    if exist('OCTAVE_VERSION', 'builtin')
        graphics_toolkit('gnuplot');
    end
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    elements = result.elements;
    nRows = numel(elements);
    names = cell(nRows, 1);
    own = zeros(nRows, 1);
    running = zeros(nRows, 1);
    for index = 1:nRows
        names{index} = elements(index).name;
        own(index) = elements(index).s_mva;
        running(index) = elements(index).s_running_mva;
    end
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 80 980 740], ...
        'Name', 'short-circuit-mva', 'NumberTitle', 'off');
    ax = subplot(2, 1, 1);
    hold(ax, 'on');
    for index = 1:nRows
        bar(ax, index, own(index), 0.72, 'FaceColor', kind_color(elements(index).kind), ...
            'EdgeColor', 'none');
    end
    set(ax, 'XTick', 1:nRows, 'XTickLabel', names);
    xlim(ax, [0.4, nRows + 0.6]);
    ylim(ax, [0, max(own) * 1.18]);
    xlabel(ax, 'Element');
    ylabel(ax, 'Short-circuit MVA');
    title(ax, 'Element short-circuit capacity');
    grid(ax, 'on');
    set(ax, 'XGrid', 'off', 'YGrid', 'on', ...
        'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.6);
    set(ax, 'FontSize', 11);
    box(ax, 'on');

    ax2 = subplot(2, 1, 2);
    hold(ax2, 'on');
    steps = (1:nRows).';
    profile = plot(ax2, steps, running, '-o', 'Color', [31, 78, 121] / 255, ...
        'LineWidth', 2, 'MarkerFaceColor', [31, 78, 121] / 255);
    set(profile, 'DisplayName', 'running equivalent');
    finalLine = plot(ax2, [0.5, nRows + 0.5], [result.s_mva, result.s_mva], '--', ...
        'Color', [192, 57, 43] / 255, 'LineWidth', 1);
    set(finalLine, 'DisplayName', 'final S_sc');
    highRun = max([running; result.s_mva; 1]);
    pad = highRun * 0.04;
    for index = 1:nRows
        text(ax2, steps(index), running(index) + pad, sprintf('%.1f', running(index)), ...
            'VerticalAlignment', 'bottom', 'HorizontalAlignment', 'center', ...
            'FontSize', 9, 'Color', [0.2 0.2 0.2]);
    end
    set(ax2, 'XTick', 1:nRows, 'XTickLabel', names);
    xlim(ax2, [0.4, nRows + 0.6]);
    ylim(ax2, [0, highRun * 1.22]);
    xlabel(ax2, 'Step');
    ylabel(ax2, 'Running S_sc (MVA)');
    title(ax2, sprintf('MVA method at %.4g kV    I_sc = %.4f kA    Z = %.4f ohm', ...
        result.v_kv, result.i_ka, result.z_ohm));
    grid(ax2, 'on');
    set(ax2, 'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.6);
    legend(ax2, 'Location', 'best');
    set(ax2, 'FontSize', 11);
    box(ax2, 'on');

    if ~isempty(outputPng)
        folder = fileparts(outputPng);
        if ~isempty(folder) && exist(folder, 'dir') ~= 7
            mkdir(folder);
        end
        if exist('exportgraphics', 'file') == 2
            exportgraphics(fig, outputPng, 'Resolution', 150);
        else
            print(fig, outputPng, '-dpng', '-r150');
        end
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function color = kind_color(kind)
    switch kind
        case 'source'
            color = [31, 78, 121] / 255;
        case 'current'
            color = [230, 126, 34] / 255;
        case 'impedance'
            color = [26, 82, 118] / 255;
        case 'line'
            color = [17, 122, 101] / 255;
        case 'transformer'
            color = [192, 57, 43] / 255;
        case 'pu'
            color = [108, 52, 131] / 255;
        otherwise
            color = [0.2, 0.2, 0.2];
    end
end

function row = draft_template()
    row = struct( ...
        'name', '', ...
        'kind', '', ...
        'combine', '', ...
        's_mva', NaN, ...
        's_va', NaN, ...
        'r_ohm', NaN, ...
        'x_ohm', NaN, ...
        'z_spec_pu', NaN, ...
        's_rated_mva', NaN);
end

function row = element_template()
    row = struct( ...
        'name', '', ...
        'kind', '', ...
        'combine', '', ...
        's_mva', NaN, ...
        's_va', NaN, ...
        'z_ohm', NaN, ...
        'r_ohm', NaN, ...
        'x_ohm', NaN, ...
        'x_over_r', NaN, ...
        'z_pu', NaN, ...
        'z_spec_pu', NaN, ...
        's_rated_mva', NaN, ...
        'i_a', NaN, ...
        'i_ka', NaN, ...
        's_running_mva', NaN, ...
        'z_running_ohm', NaN, ...
        'i_running_a', NaN, ...
        'i_running_ka', NaN);
end

function value = struct_get(data, field)
    if isfield(data, field)
        value = data.(field);
    else
        value = [];
    end
end

function key = normalize_key(value)
    text = lower(strtrim(as_char(value)));
    key = regexprep(text, '[\s_-]', '');
end

function text = as_char(value)
    if is_blank(value)
        text = '';
        return
    end
    text = strtrim(to_char(value));
end

function text = to_char(value)
    if iscell(value)
        if numel(value) == 1
            text = to_char(value{1});
        else
            text = '';
        end
        return
    end
    if ischar(value)
        text = value;
        return
    end
    if isnumeric(value)
        if isempty(value) || ~isscalar(value)
            text = '';
        else
            text = num2str(value);
        end
        return
    end
    if is_matlab_string(value)
        text = char(value);
        return
    end
    text = '';
end

function tf = is_matlab_string(value)
    % Octave ships a stub isstring that errors. Only the MATLAB builtin is usable.
    tf = false;
    if exist('isstring', 'builtin')
        tf = isstring(value);
    end
end

function tf = is_blank(value)
    if isempty(value)
        tf = true;
        return
    end
    if iscell(value)
        if numel(value) ~= 1
            tf = false;
            return
        end
        tf = is_blank(value{1});
        return
    end
    if ischar(value)
        tf = isempty(strtrim(value));
        return
    end
    if is_matlab_string(value)
        tf = isempty(strtrim(char(value)));
        return
    end
    if isnumeric(value) && isscalar(value) && isnan(value)
        tf = true;
        return
    end
    tf = false;
end
