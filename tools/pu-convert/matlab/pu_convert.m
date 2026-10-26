function result = pu_convert(varargin)
%PU_CONVERT Convert between SI (named) values and per-unit values.
%   RESULT = PU_CONVERT() returns the classroom bases only.
%   RESULT = PU_CONVERT(220e3, 'quantity', 'V', 'side', 'hv')
%   RESULT = PU_CONVERT('quantities.csv', 'output_csv', 'out.csv', ...
%       'output_png', 'pu.png', 'show', false)
%
%   Three-phase (default): V_base is line-to-line, S_base is three-phase.
%       I_base = S_base / (sqrt(3) * V_base)
%       Z_base = V_base^2 / S_base
%   Single-phase (system = 'single_phase'):
%       I_base = S_base / V_base
%       Z_base = V_base^2 / S_base
%
%   V, I, and Z/R/X use the winding selected by side ('same', 'hv', 'lv').
%   S, P, and Q always use S_base. refer_to ('hv' or 'lv') moves an ohmic
%   Z/R/X to the other winding before the per-unit step:
%       Z_dest = Z_src * (V_dest / V_src)^2
%   Both windings share one S_base, so a correct referral does not change pu.
%
%   Defaults: s_base = 100e6 VA, v_base_hv = 220e3 V, v_base_lv = 110e3 V.
%   side 'same' uses v_base when that argument is set, otherwise v_base_hv.
%
%   Name-value keys match the Python arguments: value, quantity, direction,
%   name, unit_hint, unit_out, side, refer_to, s_base, v_base, v_base_hv,
%   v_base_lv, system, csv_path, output_csv, output_png, show.
%
%   RESULT fields: s_base, system, v_base, v_base_hv, v_base_lv, i_base,
%   i_base_hv, i_base_lv, z_base, z_base_hv, z_base_lv, rows, output_csv,
%   output_png, fig.
%   rows(i) holds name, quantity, direction, side, refer_to, winding,
%   value_in, unit_in, value_pu, value_si, si_unit, value_out, unit_out,
%   base_used. value_pu = value_si / base_used.

    [source, rest] = split_source(varargin);
    parser = inputParser;
    parser.FunctionName = 'pu_convert';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('value', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('quantity', 'V', @is_text_scalar);
    parser.addParameter('direction', 'to_pu', @is_text_scalar);
    parser.addParameter('name', '', @is_text_scalar);
    parser.addParameter('unit_hint', '', @is_text_scalar);
    parser.addParameter('unit_out', '', @is_text_scalar);
    parser.addParameter('side', 'same', @is_text_scalar);
    parser.addParameter('refer_to', '', @is_text_scalar);
    parser.addParameter('s_base', 100e6, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_base', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('v_base_hv', 220e3, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_base_lv', 110e3, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('system', 'three_phase', @is_text_scalar);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    [opt, fromScalar, rawRows] = resolve_rows(source, rest, opt);

    systemName = normalize_system(opt.system);
    sBase = positive_number('s_base', opt.s_base);
    vHv = positive_number('v_base_hv', opt.v_base_hv);
    vLv = positive_number('v_base_lv', opt.v_base_lv);
    if isempty(opt.v_base)
        vSame = vHv;
    else
        vSame = positive_number('v_base', opt.v_base);
    end
    threePhase = strcmp(systemName, 'three_phase');
    [iSame, zSame] = side_bases(sBase, vSame, threePhase);
    [iHv, zHv] = side_bases(sBase, vHv, threePhase);
    [iLv, zLv] = side_bases(sBase, vLv, threePhase);

    ctx = struct();
    ctx.s_base = sBase;
    ctx.v_same = vSame;
    ctx.v_hv = vHv;
    ctx.v_lv = vLv;
    ctx.three_phase = threePhase;
    ctx.direction = char(strtrim(string(opt.direction)));
    ctx.side = char(strtrim(string(opt.side)));
    ctx.quantity = char(strtrim(string(opt.quantity)));
    ctx.unit_hint = char(strtrim(string(opt.unit_hint)));
    ctx.unit_out = char(strtrim(string(opt.unit_out)));
    ctx.refer_to = char(strtrim(string(opt.refer_to)));
    ctx.name = char(strtrim(string(opt.name)));
    ctx.from_scalar = fromScalar;

    nRows = numel(rawRows);
    if nRows == 0
        rows = empty_rows();
    else
        rows = repmat(empty_row_template(), 1, nRows);
        for index = 1:nRows
            rows(index) = convert_row(rawRows{index}, ctx, index);
        end
    end

    outputCsv = char(strtrim(string(opt.output_csv)));
    outputPng = char(strtrim(string(opt.output_png)));
    showFig = logical(opt.show);
    if ~isempty(outputCsv)
        write_rows_csv(outputCsv, rows);
    end
    if ~isempty(outputPng) || showFig
        if nRows == 0
            error('pu_convert:BadOption', 'output_png/show needs at least one converted row');
        end
        fig = render_figure(rows, outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.s_base = sBase;
    result.system = systemName;
    result.v_base = vSame;
    result.v_base_hv = vHv;
    result.v_base_lv = vLv;
    result.i_base = iSame;
    result.i_base_hv = iHv;
    result.i_base_lv = iLv;
    result.z_base = zSame;
    result.z_base_hv = zHv;
    result.z_base_lv = zLv;
    result.rows = rows;
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = fig;
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
    keys = {'value', 'quantity', 'direction', 'name', 'unit_hint', 'unit_out', ...
        'side', 'refer_to', 's_base', 'v_base', 'v_base_hv', 'v_base_lv', ...
        'system', 'csv_path', 'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(text), keys));
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = isstring(value) && isscalar(value);
end

function tf = is_number_scalar(value)
    tf = isnumeric(value) && isscalar(value) && isfinite(value);
end

function tf = was_passed(rest, key)
    tf = false;
    for index = 1:2:numel(rest)
        if is_parameter_name(rest{index}) && strcmpi(strtrim(char(string(rest{index}))), key)
            tf = true;
            return
        end
    end
end

function [opt, fromScalar, rawRows] = resolve_rows(source, rest, opt)
    fromScalar = false;
    csvMode = false;
    mapMode = false;
    mapRows = {};
    if is_number_scalar(source)
        if was_passed(rest, 'value')
            error('pu_convert:BadOption', ...
                'pass the value once, either positionally or as value');
        end
        if was_passed(rest, 'csv_path')
            error('pu_convert:BadOption', 'pass a CSV path or a single value, not both');
        end
        opt.value = double(source);
        fromScalar = true;
    elseif ischar(source) || (isstring(source) && isscalar(source))
        text = char(strtrim(string(source)));
        if ~isempty(text)
            if was_passed(rest, 'csv_path')
                error('pu_convert:BadOption', ...
                    'pass a CSV path once, either positionally or as csv_path');
            end
            if was_passed(rest, 'value')
                error('pu_convert:BadOption', 'pass a CSV path or a single value, not both');
            end
            opt.csv_path = text;
            csvMode = true;
        end
    elseif isstruct(source) || iscell(source)
        if was_passed(rest, 'csv_path') || was_passed(rest, 'value')
            error('pu_convert:BadOption', ...
                'pass a CSV path, a single value, or row mappings, not more than one');
        end
        mapMode = true;
        if isstruct(source)
            mapRows = cell(1, numel(source));
            for index = 1:numel(source)
                mapRows{index} = source(index);
            end
        else
            mapRows = source(:).';
        end
    elseif ~isempty(source)
        error('pu_convert:BadOption', ...
            'source must be a number, a CSV path, a struct, or a cell of structs');
    end

    if ~fromScalar && ~csvMode && ~mapMode
        hasValue = ~isempty(opt.value);
        hasCsv = strlength(strtrim(string(opt.csv_path))) > 0;
        if hasValue && hasCsv
            error('pu_convert:BadOption', 'pass a CSV path or a single value, not both');
        end
        fromScalar = hasValue;
        csvMode = hasCsv;
    end

    if csvMode
        rawRows = read_quantity_csv(char(strtrim(string(opt.csv_path))));
    elseif mapMode
        rawRows = mapRows;
    elseif fromScalar
        rawRows = {struct( ...
            'name', char(strtrim(string(opt.name))), ...
            'quantity', char(strtrim(string(opt.quantity))), ...
            'value', double(opt.value), ...
            'unit_hint', char(strtrim(string(opt.unit_hint))), ...
            'unit_out', char(strtrim(string(opt.unit_out))), ...
            'direction', char(strtrim(string(opt.direction))), ...
            'side', char(strtrim(string(opt.side))), ...
            'refer_to', char(strtrim(string(opt.refer_to))))};
    else
        rawRows = {};
    end
end

function systemName = normalize_system(value)
    key = normalize_key(value);
    if any(strcmp(key, {'threephase', '3phase', '3ph'}))
        systemName = 'three_phase';
        return
    end
    if any(strcmp(key, {'singlephase', '1phase', '1ph'}))
        systemName = 'single_phase';
        return
    end
    error('pu_convert:BadOption', 'system must be ''three_phase'' or ''single_phase''');
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('pu_convert:BadOption', '%s must be a positive finite number', name);
    end
end

function number = finite_number(name, value)
    if iscell(value)
        if numel(value) ~= 1
            error('pu_convert:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if isstring(value) || ischar(value)
        number = str2double(strtrim(string(value)));
    elseif isnumeric(value)
        number = double(value);
    else
        error('pu_convert:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('pu_convert:BadOption', '%s must be a finite number', name);
    end
end

function [iBase, zBase] = side_bases(sBase, vBase, threePhase)
    if threePhase
        iBase = sBase / (sqrt(3) * vBase);
    else
        iBase = sBase / vBase;
    end
    zBase = (vBase * vBase) / sBase;
end

function rows = read_quantity_csv(csvPath)
    if ~isfile(csvPath)
        error('pu_convert:FileNotFound', 'CSV not found: %s', csvPath);
    end
    tableData = read_csv_table(csvPath);
    names = string(tableData.Properties.VariableNames);
    nRows = height(tableData);
    rows = cell(1, nRows);
    kept = 0;
    for rowIndex = 1:nRows
        item = struct();
        blankRow = true;
        for col = 1:numel(names)
            value = unwrap_cell(tableData{rowIndex, col});
            item.(char(names(col))) = value;
            if ~is_blank(value)
                blankRow = false;
            end
        end
        if blankRow
            continue
        end
        kept = kept + 1;
        rows{kept} = item;
    end
    rows = rows(1:kept);
    if kept == 0
        error('pu_convert:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function tableData = read_csv_table(csvPath)
    try
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
    catch
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
    end
    tableData = readtable(csvPath, opts);
    if height(tableData) == 0
        error('pu_convert:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function value = unwrap_cell(value)
    if iscell(value) && numel(value) == 1
        value = value{1};
    end
end

function row = convert_row(raw, ctx, index)
    if ~isstruct(raw) || numel(raw) ~= 1
        error('pu_convert:BadOption', 'each row must be a scalar struct');
    end
    quantityValue = struct_lookup(raw, {'quantity', 'qty', 'type'});
    if is_blank(quantityValue)
        if ctx.from_scalar
            quantityValue = ctx.quantity;
        else
            error('pu_convert:BadOption', 'quantity is required');
        end
    end
    quantity = normalize_quantity(quantityValue);

    directionValue = struct_lookup(raw, {'direction', 'dir'});
    if is_blank(directionValue)
        directionValue = ctx.direction;
    end
    direction = normalize_direction(directionValue);

    sideValue = struct_lookup(raw, {'side'});
    if is_blank(sideValue)
        sideValue = ctx.side;
    end
    side = normalize_side(sideValue);

    referValue = struct_lookup(raw, {'referto', 'refer', 'refertowinding'});
    if is_blank(referValue)
        if ctx.from_scalar
            referValue = ctx.refer_to;
        else
            referValue = '';
        end
    end
    refer = normalize_refer(referValue);
    if strcmp(refer, side)
        refer = '';
    end
    if ~isempty(refer) && ~any(strcmp(quantity, {'Z', 'R', 'X'}))
        error('pu_convert:BadOption', 'refer_to applies only to Z, R, and X');
    end

    valueRaw = struct_lookup(raw, {'value', 'val'});
    if is_blank(valueRaw)
        error('pu_convert:BadOption', 'value is required');
    end
    value = finite_number('value', valueRaw);

    name = char(as_text(struct_lookup(raw, {'name'})));
    if isempty(name) && ctx.from_scalar
        name = ctx.name;
    end
    if isempty(name)
        if ctx.from_scalar
            name = quantity;
        else
            name = sprintf('row%d', index);
        end
    end

    hint = char(as_text(struct_lookup(raw, {'unithint', 'unit', 'units'})));
    if isempty(hint) && ctx.from_scalar
        hint = ctx.unit_hint;
    end
    outHint = char(as_text(struct_lookup(raw, {'unitout'})));
    if isempty(outHint) && ctx.from_scalar
        outHint = ctx.unit_out;
    end
    hintKey = unit_key(hint);
    if strcmp(direction, 'to_si') && ~isempty(hint) && ~any(strcmp(hintKey, {'pu', 'perunit'}))
        error('pu_convert:BadOption', ...
            ['for direction to_si the input is per-unit; leave unit_hint blank or ''pu'', ', ...
            'and set unit_out for a scaled SI result']);
    end

    srcV = voltage_for(side, ctx);
    if isempty(refer)
        dstSide = side;
    else
        dstSide = refer;
    end
    dstV = voltage_for(dstSide, ctx);
    [~, zSrc] = side_bases(ctx.s_base, srcV, ctx.three_phase);
    [iSrc, ~] = side_bases(ctx.s_base, srcV, ctx.three_phase);
    [~, zDst] = side_bases(ctx.s_base, dstV, ctx.three_phase);
    siUnit = si_unit_of(quantity);
    if strcmp(quantity, 'V')
        baseUsed = srcV;
        dstSide = side;
    elseif strcmp(quantity, 'I')
        baseUsed = iSrc;
        dstSide = side;
    elseif any(strcmp(quantity, {'S', 'P', 'Q'}))
        baseUsed = ctx.s_base;
        dstSide = side;
    else
        baseUsed = zDst;
    end

    if strcmp(direction, 'to_pu')
        [scale, unitIn] = parse_input_unit(quantity, hint);
        valueSiSrc = value * scale;
        if any(strcmp(quantity, {'Z', 'R', 'X'})) && ~isempty(refer)
            valueSi = valueSiSrc * (dstV / srcV) ^ 2;
        else
            valueSi = valueSiSrc;
        end
        valuePu = valueSi / baseUsed;
        valueOut = valuePu;
        unitOut = 'pu';
    else
        valuePu = value;
        if any(strcmp(quantity, {'Z', 'R', 'X'}))
            valueSiSrc = valuePu * zSrc;
            if ~isempty(refer)
                valueSi = valueSiSrc * (dstV / srcV) ^ 2;
            else
                valueSi = valueSiSrc;
            end
        else
            valueSi = valuePu * baseUsed;
        end
        [scale, unitOut] = parse_output_unit(quantity, outHint);
        valueOut = valueSi / scale;
        unitIn = 'pu';
    end

    row = struct( ...
        'name', name, ...
        'quantity', quantity, ...
        'direction', direction, ...
        'side', side, ...
        'refer_to', refer, ...
        'winding', dstSide, ...
        'value_in', value, ...
        'unit_in', unitIn, ...
        'value_pu', valuePu, ...
        'value_si', valueSi, ...
        'si_unit', siUnit, ...
        'value_out', valueOut, ...
        'unit_out', unitOut, ...
        'base_used', baseUsed);
end

function quantity = normalize_quantity(value)
    if is_blank(value)
        error('pu_convert:BadOption', 'quantity is required');
    end
    switch normalize_key(value)
        case {'v', 'voltage', 'u'}
            quantity = 'V';
        case {'i', 'current'}
            quantity = 'I';
        case {'s', 'power', 'apparent'}
            quantity = 'S';
        case {'p', 'active'}
            quantity = 'P';
        case {'q', 'reactive'}
            quantity = 'Q';
        case {'z', 'impedance'}
            quantity = 'Z';
        case {'r', 'resistance'}
            quantity = 'R';
        case {'x', 'reactance'}
            quantity = 'X';
        otherwise
            error('pu_convert:BadOption', ...
                'quantity must be one of: V, I, S, P, Q, Z, R, X');
    end
end

function direction = normalize_direction(value)
    switch normalize_key(value)
        case {'topu', 'sitopu', 'namedtopu'}
            direction = 'to_pu';
        case {'tosi', 'putosi', 'putonamed'}
            direction = 'to_si';
        otherwise
            error('pu_convert:BadOption', 'direction must be ''to_pu'' or ''to_si''');
    end
end

function side = normalize_side(value)
    if is_blank(value)
        value = 'same';
    end
    switch normalize_key(value)
        case {'same', 'primary', 'none'}
            side = 'same';
        case {'hv', 'high', 'highside', 'highvoltage'}
            side = 'hv';
        case {'lv', 'low', 'lowside', 'lowvoltage'}
            side = 'lv';
        otherwise
            error('pu_convert:BadOption', 'side must be ''same'', ''hv'', or ''lv''');
    end
end

function refer = normalize_refer(value)
    if is_blank(value)
        refer = '';
        return
    end
    switch normalize_key(value)
        case {'same', 'primary', 'none', 'na'}
            refer = '';
        case {'hv', 'high', 'highside', 'highvoltage'}
            refer = 'hv';
        case {'lv', 'low', 'lowside', 'lowvoltage'}
            refer = 'lv';
        otherwise
            error('pu_convert:BadOption', 'refer_to must be ''hv'', ''lv'', or empty');
    end
end

function volts = voltage_for(side, ctx)
    if strcmp(side, 'hv')
        volts = ctx.v_hv;
    elseif strcmp(side, 'lv')
        volts = ctx.v_lv;
    else
        volts = ctx.v_same;
    end
end

function unit = si_unit_of(quantity)
    switch quantity
        case 'V'
            unit = 'V';
        case 'I'
            unit = 'A';
        case 'S'
            unit = 'VA';
        case 'P'
            unit = 'W';
        case 'Q'
            unit = 'var';
        otherwise
            unit = 'ohm';
    end
end

function family = family_of(quantity)
    if strcmp(quantity, 'V')
        family = 'V';
    elseif strcmp(quantity, 'I')
        family = 'I';
    elseif any(strcmp(quantity, {'S', 'P', 'Q'}))
        family = 'S';
    else
        family = 'Z';
    end
end

function [family, scale, label, known] = unit_spec(key)
    known = true;
    switch key
        case 'v'
            family = 'V'; scale = 1; label = 'V';
        case 'kv'
            family = 'V'; scale = 1e3; label = 'kV';
        case 'a'
            family = 'I'; scale = 1; label = 'A';
        case 'ka'
            family = 'I'; scale = 1e3; label = 'kA';
        case 'va'
            family = 'S'; scale = 1; label = 'VA';
        case 'kva'
            family = 'S'; scale = 1e3; label = 'kVA';
        case 'mva'
            family = 'S'; scale = 1e6; label = 'MVA';
        case 'w'
            family = 'S'; scale = 1; label = 'W';
        case 'kw'
            family = 'S'; scale = 1e3; label = 'kW';
        case 'mw'
            family = 'S'; scale = 1e6; label = 'MW';
        case 'var'
            family = 'S'; scale = 1; label = 'var';
        case 'kvar'
            family = 'S'; scale = 1e3; label = 'kvar';
        case 'mvar'
            family = 'S'; scale = 1e6; label = 'Mvar';
        case {'ohm', 'ohms'}
            family = 'Z'; scale = 1; label = 'ohm';
        case {'pu', 'perunit'}
            family = 'pu'; scale = 1; label = 'pu';
        otherwise
            known = false;
            family = '';
            scale = NaN;
            label = '';
    end
end

function [scale, label] = parse_input_unit(quantity, unitHint)
    siUnit = si_unit_of(quantity);
    if isempty(unitHint)
        scale = 1;
        label = siUnit;
        return
    end
    [family, scale, label, known] = unit_spec(unit_key(unitHint));
    if ~known
        error('pu_convert:BadOption', 'unit_hint ''%s'' is not a supported unit', unitHint);
    end
    if strcmp(family, 'pu')
        error('pu_convert:BadOption', ...
            'unit_hint ''pu'' is not a named unit; direction to_pu expects a SI value');
    end
    if ~strcmp(family, family_of(quantity))
        error('pu_convert:BadOption', ...
            'unit_hint ''%s'' does not match quantity %s', label, quantity);
    end
end

function [scale, label] = parse_output_unit(quantity, unitOut)
    siUnit = si_unit_of(quantity);
    if isempty(unitOut)
        scale = 1;
        label = siUnit;
        return
    end
    [family, scale, label, known] = unit_spec(unit_key(unitOut));
    if ~known
        error('pu_convert:BadOption', 'unit_out ''%s'' is not a supported unit', unitOut);
    end
    if strcmp(family, 'pu')
        scale = 1;
        label = siUnit;
        return
    end
    if ~strcmp(family, family_of(quantity))
        error('pu_convert:BadOption', ...
            'unit_out ''%s'' does not match quantity %s', label, quantity);
    end
end

function key = unit_key(value)
    text = lower(strtrim(as_text(value)));
    text = replace(text, string(char(937)), "ohm");
    text = replace(text, string(char(8486)), "ohm");
    key = char(regexprep(text, '[\s_\-./]', ''));
end

function key = normalize_key(value)
    text = lower(strtrim(as_text(value)));
    key = char(regexprep(text, '[\s_\-]', ''));
end

function value = struct_lookup(data, keys)
    names = string(fieldnames(data));
    norms = strings(size(names));
    for index = 1:numel(names)
        norms(index) = string(normalize_key(names(index)));
    end
    keys = string(keys);
    for index = 1:numel(keys)
        found = find(norms == string(normalize_key(keys(index))), 1, 'first');
        if ~isempty(found)
            value = data.(char(names(found)));
            return
        end
    end
    value = [];
end

function tf = is_blank(value)
    if isempty(value)
        tf = true;
        return
    end
    if iscell(value)
        if isempty(value)
            tf = true;
            return
        end
        if numel(value) == 1
            value = value{1};
        else
            tf = false;
            return
        end
        if isempty(value)
            tf = true;
            return
        end
    end
    if ismissing(value)
        tf = true;
        return
    end
    if isstring(value) || ischar(value)
        tf = all(strlength(strtrim(string(value))) == 0);
        return
    end
    if isnumeric(value) && all(~isfinite(value))
        tf = true;
        return
    end
    tf = false;
end

function text = as_text(value)
    if is_blank(value)
        text = "";
        return
    end
    if iscell(value)
        value = value{1};
    end
    text = strtrim(string(value));
end

function row = empty_row_template()
    row = struct( ...
        'name', '', ...
        'quantity', '', ...
        'direction', '', ...
        'side', '', ...
        'refer_to', '', ...
        'winding', '', ...
        'value_in', NaN, ...
        'unit_in', '', ...
        'value_pu', NaN, ...
        'value_si', NaN, ...
        'si_unit', '', ...
        'value_out', NaN, ...
        'unit_out', '', ...
        'base_used', NaN);
end

function rows = empty_rows()
    rows = repmat(empty_row_template(), 1, 0);
end

function write_rows_csv(csvPath, rows)
    folder = fileparts(csvPath);
    if ~isempty(folder) && ~exist(folder, 'dir')
        mkdir(folder);
    end
    fields = {'name', 'quantity', 'direction', 'side', 'refer_to', 'winding', ...
        'value_in', 'unit_in', 'value_pu', 'value_si', 'si_unit', ...
        'value_out', 'unit_out', 'base_used'};
    nRows = numel(rows);
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('pu_convert:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s\n', strjoin(fields, ','));
    for index = 1:nRows
        row = rows(index);
        fprintf(fid, '%s,%s,%s,%s,%s,%s,%.12g,%s,%.12g,%.12g,%s,%.12g,%s,%.12g\n', ...
            csv_cell(row.name), csv_cell(row.quantity), csv_cell(row.direction), ...
            csv_cell(row.side), csv_cell(row.refer_to), csv_cell(row.winding), ...
            row.value_in, csv_cell(row.unit_in), row.value_pu, row.value_si, ...
            csv_cell(row.si_unit), row.value_out, csv_cell(row.unit_out), row.base_used);
    end
end

function text = csv_cell(value)
    text = char(string(value));
    if contains(text, {',', '"', newline})
        text = ['"', strrep(text, '"', '""'), '"'];
    end
end

function fig = render_figure(rows, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    nRows = numel(rows);
    figH = max(420, 42 * nRows + 160);
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [100 100 980 figH], ...
        'Name', 'pu-convert', 'NumberTitle', 'off');
    ax = axes('Parent', fig);
    values = zeros(nRows, 1);
    colors = zeros(nRows, 3);
    names = cell(nRows, 1);
    yPos = (nRows:-1:1).';
    for index = 1:nRows
        values(index) = rows(index).value_pu;
        colors(index, :) = quantity_color(rows(index).quantity);
        names{index} = rows(index).name;
    end
    barHandle = barh(ax, yPos, values, 'BarWidth', 0.72, 'EdgeColor', 'none');
    barHandle.FaceColor = 'flat';
    barHandle.CData = colors;
    barHandle.HandleVisibility = 'off';
    set(ax, 'YTick', 1:nRows, 'YTickLabel', names(nRows:-1:1));
    ylim(ax, [0.4, nRows + 0.6]);
    zeroLine = xline(ax, 0, 'Color', [0.4 0.4 0.4], 'LineWidth', 0.8);
    zeroLine.HandleVisibility = 'off';
    xlabel(ax, 'Per-unit value');
    title(ax, 'Per-unit values (mixed quantities)');
    grid(ax, 'on');
    ax.XGrid = 'on';
    ax.YGrid = 'off';
    ax.GridColor = [0.82 0.82 0.82];
    ax.GridAlpha = 0.35;
    box(ax, 'on');
    set(ax, 'FontSize', 11);
    hold(ax, 'on');
    seen = {};
    handleList = {};
    labels = {};
    for index = 1:nRows
        quantity = rows(index).quantity;
        if any(strcmp(seen, quantity))
            continue
        end
        seen{end + 1} = quantity; %#ok<AGROW>
        proxy = plot(ax, nan, nan, 's', ...
            'MarkerFaceColor', quantity_color(quantity), ...
            'MarkerEdgeColor', 'none', ...
            'MarkerSize', 10);
        handleList{end + 1} = proxy; %#ok<AGROW>
        labels{end + 1} = quantity; %#ok<AGROW>
    end
    legendHandle = legend(ax, [handleList{:}], labels, 'Location', 'best');
    legendHandle.Title.String = 'quantity';
    finiteVals = values(isfinite(values));
    if ~isempty(finiteVals)
        low = min([0, min(finiteVals)]);
        high = max([0, max(finiteVals)]);
        span = max(high - low, 0.5);
        xlim(ax, [low - 0.08 * span, high + 0.18 * span]);
    end
    if ~isempty(outputPng)
        folder = fileparts(outputPng);
        if ~isempty(folder) && ~exist(folder, 'dir')
            mkdir(folder);
        end
        exportgraphics(fig, outputPng, 'Resolution', 150);
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function color = quantity_color(quantity)
    switch quantity
        case 'V'
            color = [31, 78, 121] / 255;
        case 'I'
            color = [192, 57, 43] / 255;
        case 'S'
            color = [230, 126, 34] / 255;
        case 'P'
            color = [214, 137, 16] / 255;
        case 'Q'
            color = [108, 52, 131] / 255;
        case 'Z'
            color = [61, 122, 106] / 255;
        case 'R'
            color = [26, 82, 118] / 255;
        otherwise
            color = [17, 122, 101] / 255;
    end
end
