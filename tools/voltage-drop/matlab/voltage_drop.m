function result = voltage_drop(varargin)
%VOLTAGE_DROP Approximate line and feeder voltage drop.
%   RESULT = VOLTAGE_DROP('length_km', 2, 'r_ohm_per_km', 0.4, ...
%       'x_ohm_per_km', 0.35, 'i_a', 80, 'pf', 0.8)
%   RESULT = VOLTAGE_DROP('feeder.csv', 'output_csv', 'out.csv', ...
%       'output_png', 'profile.png', 'show', false)
%
%   Three-phase (default). R and X are one phase, ohms. V is the
%   line-to-line voltage in the denominator, volts. I is line current.
%   P and Q are three-phase watts and vars. Lagging Q is positive.
%       dV = sqrt(3) * I * (R cosφ + X sinφ) = (P R + Q X) / V
%       dV_percent = 100 * dV / V_nominal
%   Single-phase two-wire. R and X are one conductor; the loop is both ways.
%       dV = 2 * I * (R cosφ + X sinφ) = (P * 2R + Q * 2X) / V
%
%   voltage_basis 'nominal' (default) uses V_nominal in every section.
%   'sending' uses that section's sending-end voltage. Percent is always
%   relative to V_nominal.
%
%   load_mode 'tap' (default) treats each row as the load at the receiving
%   bus and adds downstream taps. 'through' uses the row as the flow already
%   in that section. Rows run from the source outward. A current input is
%   converted to P and Q at V_nominal, so on the nominal basis the current
%   formula and the power formula match.
%
%   Name-value keys match Python: length_km, r_ohm_per_km, x_ohm_per_km,
%   r_ohm, x_ohm, i_a, pf, p_kw, q_kvar, p_w, q_var, name, from_bus, to_bus,
%   v_nominal, v_source, system, load_mode, voltage_basis, csv_path,
%   output_csv, output_png, show.
%
%   RESULT fields: system, load_mode, voltage_basis, v_nominal, v_source,
%   sections, v_end, delta_v_total, delta_v_percent_total, summary,
%   output_csv, output_png, fig. summary is the same text Python prints.

    [source, rest] = split_source(varargin);
    parser = inputParser;
    parser.FunctionName = 'voltage_drop';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('length_km', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('r_ohm_per_km', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('x_ohm_per_km', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('r_ohm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('x_ohm', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('i_a', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('pf', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('p_kw', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('q_kvar', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('p_w', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('q_var', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('name', '', @is_text_scalar);
    parser.addParameter('from_bus', '', @is_text_scalar);
    parser.addParameter('to_bus', '', @is_text_scalar);
    parser.addParameter('v_nominal', 10000, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_source', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('system', 'three_phase', @is_text_scalar);
    parser.addParameter('load_mode', 'tap', @is_text_scalar);
    parser.addParameter('voltage_basis', 'nominal', @is_text_scalar);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    systemName = normalize_system(opt.system);
    modeName = normalize_load_mode(opt.load_mode);
    basisName = normalize_basis(opt.voltage_basis);
    vNominal = positive_number('v_nominal', opt.v_nominal);
    if isempty(opt.v_source)
        vSource = vNominal;
    else
        vSource = positive_number('v_source', opt.v_source);
    end
    threePhase = strcmp(systemName, 'three_phase');

    rawRows = resolve_rows(source, rest, opt);
    nRows = numel(rawRows);
    sections = repmat(section_template(), 1, nRows);
    for index = 1:nRows
        sections(index) = parse_section(rawRows{index}, index, vNominal, threePhase);
    end
    sections = assign_buses(sections);
    sections = accumulate(sections, modeName);
    sections = solve_sections(sections, vNominal, vSource, basisName, threePhase);

    outputCsv = strtrim(to_char(opt.output_csv));
    outputPng = strtrim(to_char(opt.output_png));
    showFig = logical(opt.show);
    if ~isempty(outputCsv)
        write_sections_csv(outputCsv, sections);
    end

    result = struct();
    result.system = systemName;
    result.load_mode = modeName;
    result.voltage_basis = basisName;
    result.v_nominal = vNominal;
    result.v_source = vSource;
    result.sections = sections;
    result.v_end = sections(end).v_recv;
    result.delta_v_total = vSource - result.v_end;
    result.delta_v_percent_total = 100 * result.delta_v_total / vNominal;
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

function tf = is_parameter_name(value)
    if ischar(value) || (is_matlab_string(value) && isscalar(value))
        text = to_char(value);
    else
        tf = false;
        return
    end
    keys = {'length_km', 'r_ohm_per_km', 'x_ohm_per_km', 'r_ohm', 'x_ohm', ...
        'i_a', 'pf', 'p_kw', 'q_kvar', 'p_w', 'q_var', 'name', 'from_bus', ...
        'to_bus', 'v_nominal', 'v_source', 'system', 'load_mode', ...
        'voltage_basis', 'csv_path', 'output_csv', 'output_png', 'show'};
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
    keys = {'length_km', 'r_ohm_per_km', 'x_ohm_per_km', 'r_ohm', 'x_ohm', ...
        'i_a', 'pf', 'p_kw', 'q_kvar', 'p_w', 'q_var', 'name', 'from_bus', 'to_bus'};
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
                error('voltage_drop:BadOption', ...
                    ['%s is a parameter name. Pass the CSV path as csv_path ', ...
                    'or as the first argument'], text);
            end
            if ~isempty(csvText)
                error('voltage_drop:BadOption', ...
                    'pass a CSV path once, either positionally or as csv_path');
            end
            if hasDirect
                error('voltage_drop:BadOption', ...
                    'pass a CSV path or one section''s arguments, not both');
            end
            csvText = text;
        end
    elseif isstruct(source) || iscell(source)
        if ~isempty(csvText) || hasDirect
            error('voltage_drop:BadOption', ...
                'pass a CSV path, row mappings, or one section''s arguments, not more than one');
        end
        mapMode = true;
        if isstruct(source)
            mapRows = cell(1, numel(source));
            for index = 1:numel(source)
                mapRows{index} = source(index);
            end
        else
            if isempty(source)
                error('voltage_drop:BadOption', 'section list is empty');
            end
            mapRows = source(:).';
        end
    elseif ~isempty(source)
        error('voltage_drop:BadOption', ...
            'source must be a CSV path, a struct, or a cell of structs');
    end

    if ~isempty(csvText) && hasDirect
        error('voltage_drop:BadOption', ...
            'pass a CSV path or one section''s arguments, not both');
    end
    if ~isempty(csvText)
        rawRows = read_section_csv(csvText);
        return
    end
    if mapMode
        if isempty(mapRows)
            error('voltage_drop:BadOption', 'section list is empty');
        end
        rawRows = mapRows;
        return
    end
    if hasDirect
        rawRows = {direct};
        return
    end
    error('voltage_drop:BadOption', 'pass a feeder CSV or one section (R/X and a load)');
end

function systemName = normalize_system(value)
    switch normalize_key(value)
        case {'threephase', '3phase', '3ph'}
            systemName = 'three_phase';
        case {'singlephase', '1phase', '1ph'}
            systemName = 'single_phase';
        otherwise
            error('voltage_drop:BadOption', 'system must be ''three_phase'' or ''single_phase''');
    end
end

function modeName = normalize_load_mode(value)
    switch normalize_key(value)
        case {'tap', 'bus', 'load', 'tapped'}
            modeName = 'tap';
        case {'through', 'flow', 'section', 'series'}
            modeName = 'through';
        otherwise
            error('voltage_drop:BadOption', 'load_mode must be ''tap'' or ''through''');
    end
end

function basisName = normalize_basis(value)
    switch normalize_key(value)
        case {'nominal', 'vn', 'rated', 'un'}
            basisName = 'nominal';
        case {'sending', 'send', 'actual', 'upstream'}
            basisName = 'sending';
        otherwise
            error('voltage_drop:BadOption', 'voltage_basis must be ''nominal'' or ''sending''');
    end
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('voltage_drop:BadOption', '%s must be a positive finite number', name);
    end
end

function number = finite_number(name, value)
    if iscell(value)
        if numel(value) ~= 1
            error('voltage_drop:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if ischar(value) || is_matlab_string(value)
        number = str2double(strtrim(to_char(value)));
    elseif isnumeric(value)
        number = double(value);
    else
        error('voltage_drop:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('voltage_drop:BadOption', '%s must be a finite number', name);
    end
end

function number = optional_number(label, data, field)
    if ~isfield(data, field) || is_blank(data.(field))
        number = [];
        return
    end
    number = finite_number(label, data.(field));
end

function rows = read_section_csv(csvPath)
    if exist(csvPath, 'file') ~= 2
        error('voltage_drop:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if numel(raw) >= 3 && raw(1) == char(239) && raw(2) == char(187) && raw(3) == char(191)
        raw = raw(4:end);
    end
    raw = strrep(raw, char(13), '');
    if isempty(strtrim(raw))
        error('voltage_drop:EmptyCsv', 'CSV is empty: %s', csvPath);
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
        error('voltage_drop:EmptyCsv', 'CSV is empty: %s', csvPath);
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
            error('voltage_drop:BadOption', 'unknown column ''%s''', strtrim(headers{col}));
        end
        canons{col} = canon;
    end
    rows = cell(1, numel(dataLines));
    kept = 0;
    for rowIndex = 1:numel(dataLines)
        cells = split_line(dataLines{rowIndex}, delimiter);
        if numel(cells) ~= numel(headers)
            error('voltage_drop:BadOption', ...
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
                error('voltage_drop:BadOption', 'duplicate column %s', canon);
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
        error('voltage_drop:EmptyCsv', 'CSV has no data rows: %s', csvPath);
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
        case {'name', 'section', 'id'}
            canon = 'name';
        case {'frombus', 'from', 'busfrom'}
            canon = 'from_bus';
        case {'tobus', 'to', 'busto'}
            canon = 'to_bus';
        case {'lengthkm', 'length', 'km', 'lkm'}
            canon = 'length_km';
        case {'rohmperkm', 'rperkm', 'rkm'}
            canon = 'r_ohm_per_km';
        case {'xohmperkm', 'xperkm', 'xkm'}
            canon = 'x_ohm_per_km';
        case {'rohm', 'r', 'resistance'}
            canon = 'r_ohm';
        case {'xohm', 'x', 'reactance'}
            canon = 'x_ohm';
        case {'pkw', 'p'}
            canon = 'p_kw';
        case {'qkvar', 'q'}
            canon = 'q_kvar';
        case 'pw'
            canon = 'p_w';
        case 'qvar'
            canon = 'q_var';
        case {'ia', 'i', 'current', 'amp', 'amps'}
            canon = 'i_a';
        case {'pf', 'cosphi', 'powerfactor'}
            canon = 'pf';
        otherwise
            canon = '';
    end
end

function raw = canonicalize(data)
    if ~isstruct(data) || numel(data) ~= 1
        error('voltage_drop:BadOption', 'each section must be a scalar struct');
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
            error('voltage_drop:BadOption', 'unknown column ''%s''', key);
        end
        value = data.(key);
        if isfield(raw, canon) && ~is_blank(raw.(canon)) && ~is_blank(value)
            error('voltage_drop:BadOption', 'duplicate column %s', canon);
        end
        if ~isfield(raw, canon) || ~is_blank(value)
            raw.(canon) = value;
        end
    end
end

function row = parse_section(data, index, vNominal, threePhase)
    raw = canonicalize(data);
    name = as_char(struct_get(raw, 'name'));
    if isempty(name)
        name = sprintf('section%d', index);
    end
    [lengthKm, rOhm, xOhm] = section_rx(raw, name);
    [active, reactive] = load_pq(raw, vNominal, threePhase, name);
    row = section_template();
    row.name = name;
    row.from_bus = as_char(struct_get(raw, 'from_bus'));
    row.to_bus = as_char(struct_get(raw, 'to_bus'));
    row.length_km = lengthKm;
    row.r_ohm = rOhm;
    row.x_ohm = xOhm;
    row.p_w = active;
    row.q_var = reactive;
end

function [lengthOut, rOhm, xOhm] = section_rx(raw, label)
    lengthKm = optional_number('length_km', raw, 'length_km');
    if ~isempty(lengthKm) && lengthKm < 0
        error('voltage_drop:BadOption', '%s: length_km must be >= 0', label);
    end
    rTotal = optional_number('r_ohm', raw, 'r_ohm');
    xTotal = optional_number('x_ohm', raw, 'x_ohm');
    rKm = optional_number('r_ohm_per_km', raw, 'r_ohm_per_km');
    xKm = optional_number('x_ohm_per_km', raw, 'x_ohm_per_km');
    hasTotal = ~isempty(rTotal) || ~isempty(xTotal);
    hasKm = ~isempty(rKm) || ~isempty(xKm);
    if hasTotal && hasKm
        error('voltage_drop:BadOption', ...
            '%s: pass total r_ohm/x_ohm or per-km values, not both', label);
    end
    if hasTotal
        if isempty(rTotal)
            rOhm = 0;
        else
            rOhm = rTotal;
        end
        if isempty(xTotal)
            xOhm = 0;
        else
            xOhm = xTotal;
        end
    elseif hasKm
        if isempty(lengthKm)
            error('voltage_drop:BadOption', ...
                '%s: length_km is required when r/x are given per km', label);
        end
        if isempty(rKm)
            rOhm = 0;
        else
            rOhm = rKm * lengthKm;
        end
        if isempty(xKm)
            xOhm = 0;
        else
            xOhm = xKm * lengthKm;
        end
    else
        error('voltage_drop:BadOption', '%s: resistance or reactance is required', label);
    end
    if rOhm < 0
        error('voltage_drop:BadOption', '%s: resistance must be >= 0', label);
    end
    if isempty(lengthKm)
        lengthOut = NaN;
    else
        lengthOut = lengthKm;
    end
end

function [active, reactive] = load_pq(raw, vNominal, threePhase, label)
    pKw = optional_number('p_kw', raw, 'p_kw');
    qKvar = optional_number('q_kvar', raw, 'q_kvar');
    pWatts = optional_number('p_w', raw, 'p_w');
    qVars = optional_number('q_var', raw, 'q_var');
    iA = optional_number('i_a', raw, 'i_a');
    pf = optional_number('pf', raw, 'pf');
    hasP = ~isempty(pKw) || ~isempty(pWatts);
    hasQ = ~isempty(qKvar) || ~isempty(qVars);
    if hasP && ~isempty(iA)
        error('voltage_drop:BadOption', '%s: pass P/Q or I/pf, not both', label);
    end
    if ~isempty(pKw) && ~isempty(pWatts)
        error('voltage_drop:BadOption', '%s: pass p_kw or p_w, not both', label);
    end
    if ~isempty(qKvar) && ~isempty(qVars)
        error('voltage_drop:BadOption', '%s: pass q_kvar or q_var, not both', label);
    end
    if ~isempty(iA)
        if ~(iA >= 0)
            error('voltage_drop:BadOption', '%s: i_a must be >= 0', label);
        end
        if isempty(pf)
            pf = 1;
        end
        [cosPhi, sinPhi] = pf_parts(pf, label);
        if threePhase
            scale = sqrt(3);
        else
            scale = 1;
        end
        active = scale * vNominal * iA * cosPhi;
        reactive = scale * vNominal * iA * sinPhi;
        return
    end
    if ~hasP && ~hasQ
        error('voltage_drop:BadOption', ...
            '%s: a load is required (p_kw/q_kvar or i_a/pf)', label);
    end
    if ~isempty(pKw)
        active = pKw * 1000;
    elseif ~isempty(pWatts)
        active = pWatts;
    else
        active = 0;
    end
    if hasQ
        if ~isempty(pf)
            error('voltage_drop:BadOption', '%s: pass q or pf, not both', label);
        end
        if ~isempty(qKvar)
            reactive = qKvar * 1000;
        else
            reactive = qVars;
        end
        return
    end
    if isempty(pf)
        pf = 1;
    end
    [cosPhi, sinPhi] = pf_parts(pf, label);
    if cosPhi == 0
        error('voltage_drop:BadOption', ...
            '%s: pf is 0; pass q_kvar for a pure reactive load', label);
    end
    reactive = active * sinPhi / cosPhi;
end

function [cosPhi, sinPhi] = pf_parts(pf, label)
    if pf < -1 || pf > 1
        error('voltage_drop:BadOption', ...
            '%s: pf must be between -1 and 1 (a fraction, not a percent)', label);
    end
    cosPhi = abs(pf);
    sinMag = sqrt(max(0, 1 - cosPhi * cosPhi));
    if pf < 0
        sinPhi = -sinMag;
    else
        sinPhi = sinMag;
    end
end

function rows = assign_buses(rows)
    nRows = numel(rows);
    for index = 1:nRows
        if isempty(rows(index).to_bus)
            rows(index).to_bus = sprintf('B%d', index);
        end
    end
    for index = 1:nRows
        if isempty(rows(index).from_bus)
            if index == 1
                rows(index).from_bus = 'source';
            else
                rows(index).from_bus = rows(index - 1).to_bus;
            end
        end
    end
end

function rows = accumulate(rows, loadMode)
    nRows = numel(rows);
    if strcmp(loadMode, 'through')
        for index = 1:nRows
            rows(index).p_through_w = rows(index).p_w;
            rows(index).q_through_var = rows(index).q_var;
        end
        return
    end
    active = 0;
    reactive = 0;
    for index = nRows:-1:1
        active = active + rows(index).p_w;
        reactive = reactive + rows(index).q_var;
        rows(index).p_through_w = active;
        rows(index).q_through_var = reactive;
    end
end

function [pf, cosPhi, sinPhi] = signed_pf(active, reactive, apparent)
    if apparent == 0
        pf = 1;
        cosPhi = 1;
        sinPhi = 0;
        return
    end
    cosPhi = active / apparent;
    sinPhi = reactive / apparent;
    if reactive < 0
        pf = -abs(cosPhi);
    elseif reactive > 0
        pf = abs(cosPhi);
    else
        pf = cosPhi;
    end
end

function rows = solve_sections(rows, vNominal, vSource, voltageBasis, threePhase)
    if threePhase
        phase = sqrt(3);
        loop = 1;
    else
        phase = 1;
        loop = 2;
    end
    vSend = vSource;
    for index = 1:numel(rows)
        if strcmp(voltageBasis, 'nominal')
            vFormula = vNominal;
        else
            vFormula = vSend;
        end
        if ~(vFormula > 0)
            error('voltage_drop:Voltage', ...
                ['%s: sending voltage is not positive; ', ...
                'the approximate drop exceeds the upstream voltage'], rows(index).name);
        end
        rUsed = rows(index).r_ohm * loop;
        xUsed = rows(index).x_ohm * loop;
        active = rows(index).p_through_w;
        reactive = rows(index).q_through_var;
        delta = (active * rUsed + reactive * xUsed) / vFormula;
        apparent = hypot(active, reactive);
        if apparent == 0
            current = 0;
            pf = 1;
            cosPhi = 1;
            sinPhi = 0;
        else
            current = apparent / (phase * vFormula);
            [pf, cosPhi, sinPhi] = signed_pf(active, reactive, apparent);
        end
        vRecv = vSend - delta;
        rows(index).r_used_ohm = rUsed;
        rows(index).x_used_ohm = xUsed;
        rows(index).i_a = current;
        rows(index).pf = pf;
        rows(index).cos_phi = cosPhi;
        rows(index).sin_phi = sinPhi;
        rows(index).delta_v = delta;
        rows(index).delta_v_percent = 100 * delta / vNominal;
        rows(index).v_send = vSend;
        rows(index).v_recv = vRecv;
        vSend = vRecv;
    end
end

function text = format_summary(result)
    nRows = numel(result.sections);
    lines = cell(1, nRows + 3);
    lines{1} = sprintf(['system=%s  load_mode=%s  basis=%s  ', ...
        'V_nominal=%.4f V  V_source=%.4f V'], ...
        result.system, result.load_mode, result.voltage_basis, ...
        result.v_nominal, result.v_source);
    lines{2} = sprintf(['%-8s %-6s %-6s %7s %8s %8s %8s %9s %9s %11s ', ...
        '%8s %7s %9s %8s %10s %10s'], ...
        'section', 'from', 'to', 'km', 'R_ohm', 'X_ohm', ...
        'Ptap_kW', 'Qtap_kvar', 'Pthru_kW', 'Qthru_kvar', ...
        'I_A', 'pf', 'dV_V', 'dV_pct', 'V_send', 'V_recv');
    for index = 1:nRows
        row = result.sections(index);
        lines{index + 2} = sprintf(['%-8s %-6s %-6s %7s %8.4f %8.4f %8.3f %9.3f ', ...
            '%9.3f %11.3f %8.3f %7.4f %9.4f %8.4f %10.4f %10.4f'], ...
            row.name, row.from_bus, row.to_bus, km_text(row.length_km), ...
            row.r_ohm, row.x_ohm, row.p_w / 1000, row.q_var / 1000, ...
            row.p_through_w / 1000, row.q_through_var / 1000, ...
            row.i_a, row.pf, row.delta_v, row.delta_v_percent, ...
            row.v_send, row.v_recv);
    end
    lines{nRows + 3} = sprintf('total drop=%.4f V (%.4f %%)  V_end=%.4f V', ...
        result.delta_v_total, result.delta_v_percent_total, result.v_end);
    text = strjoin(lines, char(10));
end

function text = km_text(value)
    if ~isfinite(value)
        text = '      -';
    else
        text = sprintf('%7.3f', value);
    end
end

function write_sections_csv(csvPath, sections)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fields = {'name', 'from_bus', 'to_bus', 'length_km', 'r_ohm', 'x_ohm', ...
        'r_used_ohm', 'x_used_ohm', 'p_w', 'q_var', 'p_through_w', 'q_through_var', ...
        'i_a', 'pf', 'cos_phi', 'sin_phi', 'delta_v', 'delta_v_percent', ...
        'v_send', 'v_recv'};
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('voltage_drop:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s\n', strjoin(fields, ','));
    for index = 1:numel(sections)
        row = sections(index);
        fprintf(fid, '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n', ...
            csv_cell(row.name), csv_cell(row.from_bus), csv_cell(row.to_bus), ...
            csv_num(row.length_km), csv_num(row.r_ohm), csv_num(row.x_ohm), ...
            csv_num(row.r_used_ohm), csv_num(row.x_used_ohm), ...
            csv_num(row.p_w), csv_num(row.q_var), ...
            csv_num(row.p_through_w), csv_num(row.q_through_var), ...
            csv_num(row.i_a), csv_num(row.pf), csv_num(row.cos_phi), csv_num(row.sin_phi), ...
            csv_num(row.delta_v), csv_num(row.delta_v_percent), ...
            csv_num(row.v_send), csv_num(row.v_recv));
    end
end

function text = csv_num(value)
    if ~isfinite(value)
        text = '';
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
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    sections = result.sections;
    nRows = numel(sections);
    lengths = [sections.length_km];
    if all(isfinite(lengths))
        xs = zeros(nRows + 1, 1);
        for index = 1:nRows
            xs(index + 1) = xs(index) + lengths(index);
        end
        xLabel = 'Distance from source (km)';
    else
        xs = (0:nRows).';
        xLabel = 'Bus index from source';
    end
    volts = zeros(nRows + 1, 1);
    volts(1) = result.v_source;
    labels = cell(nRows + 1, 1);
    labels{1} = sections(1).from_bus;
    names = cell(nRows, 1);
    drops = zeros(nRows, 1);
    for index = 1:nRows
        volts(index + 1) = sections(index).v_recv;
        labels{index + 1} = sections(index).to_bus;
        names{index} = sections(index).name;
        drops(index) = sections(index).delta_v_percent;
    end
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 80 980 740], ...
        'Name', 'voltage-drop', 'NumberTitle', 'off');
    ax = subplot(2, 1, 1);
    hold(ax, 'on');
    profile = plot(ax, xs, volts, '-o', 'Color', [31, 78, 121] / 255, ...
        'LineWidth', 2, 'MarkerFaceColor', [31, 78, 121] / 255);
    set(profile, 'DisplayName', 'bus voltage');
    nominal = plot(ax, [xs(1), xs(end)], [result.v_nominal, result.v_nominal], '--', ...
        'Color', [192, 57, 43] / 255, 'LineWidth', 1);
    set(nominal, 'DisplayName', 'nominal');
    low = min([volts; result.v_nominal]);
    high = max([volts; result.v_nominal]);
    span = high - low;
    pad = max([span * 0.22, abs(result.v_nominal) * 0.004, 1]);
    for index = 1:numel(xs)
        text(ax, xs(index), volts(index) + 0.08 * pad, labels{index}, ...
            'VerticalAlignment', 'bottom', 'HorizontalAlignment', 'center', ...
            'FontSize', 9, 'Color', [0.2 0.2 0.2]);
    end
    ylim(ax, [low - 0.35 * pad, high + pad]);
    xlabel(ax, xLabel);
    ylabel(ax, 'Voltage (V)');
    title(ax, 'Feeder voltage profile');
    grid(ax, 'on');
    set(ax, 'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.6);
    legend(ax, 'Location', 'best');
    set(ax, 'FontSize', 11);
    box(ax, 'on');

    ax2 = subplot(2, 1, 2);
    hold(ax2, 'on');
    for index = 1:nRows
        if drops(index) >= 0
            barColor = [31, 78, 121] / 255;
        else
            barColor = [17, 122, 101] / 255;
        end
        bar(ax2, index, drops(index), 0.72, 'FaceColor', barColor, 'EdgeColor', 'none');
    end
    set(ax2, 'XTick', 1:nRows, 'XTickLabel', names);
    xlim(ax2, [0.4, nRows + 0.6]);
    zeroLine = plot(ax2, [0.5, nRows + 0.5], [0, 0], ...
        'Color', [0.4 0.4 0.4], 'LineWidth', 0.8);
    set(zeroLine, 'HandleVisibility', 'off');
    xlabel(ax2, 'Section');
    ylabel(ax2, 'Voltage drop (%)');
    title(ax2, 'Section voltage drop vs nominal');
    grid(ax2, 'on');
    set(ax2, 'XGrid', 'off', 'YGrid', 'on', ...
        'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.6);
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

function row = section_template()
    row = struct( ...
        'name', '', ...
        'from_bus', '', ...
        'to_bus', '', ...
        'length_km', NaN, ...
        'r_ohm', NaN, ...
        'x_ohm', NaN, ...
        'r_used_ohm', NaN, ...
        'x_used_ohm', NaN, ...
        'p_w', NaN, ...
        'q_var', NaN, ...
        'p_through_w', NaN, ...
        'q_through_var', NaN, ...
        'i_a', NaN, ...
        'pf', NaN, ...
        'cos_phi', NaN, ...
        'sin_phi', NaN, ...
        'delta_v', NaN, ...
        'delta_v_percent', NaN, ...
        'v_send', NaN, ...
        'v_recv', NaN);
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
    if isnumeric(value) && isscalar(value) && ~isfinite(value)
        tf = true;
        return
    end
    tf = false;
end
