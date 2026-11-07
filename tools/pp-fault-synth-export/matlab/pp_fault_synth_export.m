function result = pp_fault_synth_export(varargin)
%PP_FAULT_SYNTH_EXPORT Short-circuit samples and protection labels.
%   RESULT = PP_FAULT_SYNTH_EXPORT()
%   RESULT = PP_FAULT_SYNTH_EXPORT('feeder.csv', 'output_csv', 'out.csv', ...
%       'output_png', 'faults.png', 'show', false)
%
%   Radial MV feeder. Prefault voltage is 1.0 pu and load current is
%   ignored. Z2 = Z1. Fault resistance R_f is ohms at the faulted bus.
%       ABC  I1 = E / (Z1 + R_f)
%       AG   I1 = I2 = I0 = E / (Z1 + Z2 + Z0 + 3 R_f),  Ia = 3 I1
%       BC   I1 = -I2 = E / (Z1 + Z2 + R_f),  |Ib| = |Ic| = sqrt(3) |I1|
%   BG/CG cycle the AG pattern. AB/CA cycle the BC pattern.
%   label_protect is phase-to-ground, phase-to-phase, or three-phase.
%
%   This file is the zbus engine. It matches Python engine='zbus'.
%   engine 'auto' means zbus here. engine 'pandapower' is Python only.
%
%   Name-value keys: v_kv, s_base_mva, fault_types, r_fault_ohm, buses,
%   n_samples, seed, engine, network, z0_line_factor, z0_source_factor,
%   csv_path, output_csv, output_png, show.
%
%   RESULT.preview and RESULT.summary are the same text Python prints.

    [source, rest] = split_source(varargin);
    assert_pairs(rest);
    parser = inputParser;
    parser.FunctionName = 'pp_fault_synth_export';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('v_kv', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('s_base_mva', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('fault_types', '', @(x) ischar(x) || is_matlab_string(x) || iscell(x));
    parser.addParameter('r_fault_ohm', [0, 1, 5], @(x) isnumeric(x) && ~isempty(x));
    parser.addParameter('buses', '', @(x) ischar(x) || is_matlab_string(x) || iscell(x));
    parser.addParameter('n_samples', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('seed', 42, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('engine', 'zbus', @is_text_scalar);
    parser.addParameter('network', '', @is_text_scalar);
    parser.addParameter('z0_line_factor', 3, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('z0_source_factor', 1.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    engineName = normalize_engine(opt.engine);
    if strcmp(engineName, 'pandapower')
        error('pp_fault_synth_export:BadOption', ...
            ['engine ''pandapower'' is the Python CIGRE-MV path. ', ...
            'MATLAB implements the radial zbus engine']);
    end
    networkName = normalize_network(opt.network);
    if strcmp(networkName, 'cigre_mv')
        error('pp_fault_synth_export:BadOption', ...
            'network ''cigre_mv'' needs the Python engine ''pandapower''');
    end
    vKv = positive_number('v_kv', opt.v_kv);
    baseMva = positive_number('s_base_mva', opt.s_base_mva);
    seedValue = seed_number(opt.seed);
    lineFactor = positive_number('z0_line_factor', opt.z0_line_factor);
    sourceFactor = positive_number('z0_source_factor', opt.z0_source_factor);
    if was_passed(rest, 'fault_types')
        faultNames = parse_fault_types(opt.fault_types);
    else
        faultNames = {'AG', 'BG', 'CG', 'AB', 'BC', 'CA', 'ABC'};
    end
    resistances = parse_resistances(opt.r_fault_ohm);
    if was_passed(rest, 'buses')
        busFilter = parse_buses(opt.buses);
    else
        busFilter = {};
    end
    if was_passed(rest, 'n_samples')
        nSamples = positive_integer('n_samples', opt.n_samples);
    else
        nSamples = [];
    end
    feederPath = resolve_feeder_path(source, opt.csv_path);

    vLl = vKv * 1000;
    [sourceSpec, lines] = load_feeder(feederPath, sourceFactor, lineFactor);
    points = walk_radial(sourceSpec, lines, vLl);
    if ~isempty(busFilter)
        points = filter_buses(points, busFilter);
    end
    specs = selected_specs(faultNames);
    samples = build_grid(points, specs, resistances, baseMva * 1e6);
    nGrid = numel(samples);
    samples = subsample_rows(samples, nSamples, seedValue);
    for index = 1:numel(samples)
        samples(index).sample_id = index;
    end

    anchor = points(1).bus_id;
    remote = remote_bus(points);
    outputCsv = strtrim(to_char(opt.output_csv));
    outputPng = strtrim(to_char(opt.output_png));
    showFig = logical(opt.show);
    if ~isempty(outputCsv)
        write_samples_csv(outputCsv, samples);
    end

    result = struct();
    result.engine = 'zbus';
    result.network = 'radial';
    result.v_kv = vKv;
    result.v_ll_v = vLl;
    result.s_base_mva = baseMva;
    result.z_base_ohm = (vLl * vLl) / (baseMva * 1e6);
    result.i_base_a = (baseMva * 1e6) / (sqrt(3) * vLl);
    result.seed = seedValue;
    result.n_grid = nGrid;
    result.n_samples = numel(samples);
    result.anchor_bus = anchor;
    result.remote_bus = remote;
    result.samples = samples;
    result.summary = '';
    result.preview = '';
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = [];
    result.preview = format_preview(result);
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
    for index = 1:2:numel(rest)
        if ~is_parameter_name(rest{index})
            error('pp_fault_synth_export:BadOption', ...
                'options are name-value pairs; the feeder CSV is the first argument');
        end
    end
    if mod(numel(rest), 2) ~= 0
        error('pp_fault_synth_export:BadOption', 'name-value arguments must come in pairs');
    end
end

function tf = is_parameter_name(value)
    if ischar(value) || (is_matlab_string(value) && isscalar(value))
        text = to_char(value);
    else
        tf = false;
        return
    end
    keys = {'v_kv', 's_base_mva', 'fault_types', 'r_fault_ohm', 'buses', ...
        'n_samples', 'seed', 'engine', 'network', 'z0_line_factor', ...
        'z0_source_factor', 'csv_path', 'output_csv', 'output_png', 'show'};
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

function pathText = resolve_feeder_path(source, csvOpt)
    csvText = strtrim(to_char(csvOpt));
    if ischar(source) || (is_matlab_string(source) && isscalar(source))
        text = strtrim(to_char(source));
        if ~isempty(text)
            if is_parameter_name(text)
                error('pp_fault_synth_export:BadOption', ...
                    ['%s is a parameter name. Pass the CSV path as csv_path ', ...
                    'or as the first argument'], text);
            end
            if ~isempty(csvText)
                error('pp_fault_synth_export:BadOption', ...
                    'pass a CSV path once, either positionally or as csv_path');
            end
            csvText = text;
        end
    elseif ~isempty(source)
        error('pp_fault_synth_export:BadOption', 'source must be a feeder CSV path or omitted');
    end
    pathText = csvText;
end

function engineName = normalize_engine(value)
    switch normalize_key(value)
        case {'zbus', 'radial', 'fallback', 'numpy', 'auto'}
            engineName = 'zbus';
        case {'pandapower', 'pp', 'cigre'}
            engineName = 'pandapower';
        otherwise
            error('pp_fault_synth_export:BadOption', ...
                'engine must be ''zbus'', ''pandapower'', or ''auto''');
    end
end

function networkName = normalize_network(value)
    if isempty(strtrim(to_char(value)))
        networkName = 'radial';
        return
    end
    switch normalize_key(value)
        case {'radial', 'feeder'}
            networkName = 'radial';
        case {'cigremv', 'cigre', 'mv'}
            networkName = 'cigre_mv';
        otherwise
            error('pp_fault_synth_export:BadOption', ...
                'network must be ''radial'' or ''cigre_mv''');
    end
end

function names = parse_fault_types(value)
    tokens = text_list(value, 'fault_types');
    chosen = {};
    catalog = {'AG', 'BG', 'CG', 'AB', 'BC', 'CA', 'ABC'};
    for index = 1:numel(tokens)
        name = fault_alias(tokens{index});
        if isempty(name)
            error('pp_fault_synth_export:BadOption', ...
                'fault_types entries must be AG, BG, CG, AB, BC, CA, or ABC');
        end
        if ~any(strcmp(chosen, name))
            chosen{end + 1} = name; %#ok<AGROW>
        end
    end
    names = {};
    for index = 1:numel(catalog)
        if any(strcmp(chosen, catalog{index}))
            names{end + 1} = catalog{index}; %#ok<AGROW>
        end
    end
end

function name = fault_alias(token)
    switch normalize_key(token)
        case 'ag'
            name = 'AG';
        case 'bg'
            name = 'BG';
        case 'cg'
            name = 'CG';
        case 'ab'
            name = 'AB';
        case {'ca', 'ac'}
            name = 'CA';
        case 'bc'
            name = 'BC';
        case {'abc', '3ph', '3p'}
            name = 'ABC';
        case {'ll', '2ph', 'pp'}
            name = 'BC';
        case {'lg', 'slg', '1ph'}
            name = 'AG';
        otherwise
            name = '';
    end
end

function values = parse_resistances(value)
    numbers = double(value(:)).';
    if isempty(numbers)
        error('pp_fault_synth_export:BadOption', 'r_fault_ohm is empty');
    end
    values = zeros(1, numel(numbers));
    for index = 1:numel(numbers)
        values(index) = nonnegative_number('r_fault_ohm', numbers(index));
    end
end

function names = parse_buses(value)
    tokens = text_list(value, 'buses');
    names = {};
    for index = 1:numel(tokens)
        text = strtrim(tokens{index});
        if isempty(text)
            error('pp_fault_synth_export:BadOption', 'bus id is empty');
        end
        if ~any(strcmp(names, text))
            names{end + 1} = text; %#ok<AGROW>
        end
    end
end

function tokens = text_list(value, label)
    if iscell(value)
        if isempty(value)
            error('pp_fault_synth_export:BadOption', '%s is empty', label);
        end
        tokens = cell(1, numel(value));
        for index = 1:numel(value)
            tokens{index} = to_char(value{index});
        end
        return
    end
    text = strtrim(to_char(value));
    if isempty(text)
        error('pp_fault_synth_export:BadOption', '%s is empty', label);
    end
    tokens = {text};
end

function [sourceSpec, lines] = load_feeder(pathText, sourceFactor, lineFactor)
    if isempty(pathText)
        [sourceSpec, lines] = builtin_feeder(sourceFactor);
        return
    end
    rows = read_feeder_csv(pathText);
    sources = {};
    lines = repmat(line_template(), 1, 0);
    for index = 1:numel(rows)
        kind = normalize_key(struct_get(rows{index}, 'kind'));
        if any(strcmp(kind, {'source', 'grid', 'extgrid', 'externalgrid'}))
            sources{end + 1} = parse_source(rows{index}, index, sourceFactor); %#ok<AGROW>
        elseif any(strcmp(kind, {'line', 'cable', 'feeder', 'ohl'}))
            lines(end + 1) = parse_line(rows{index}, index, lineFactor); %#ok<AGROW>
        elseif isempty(kind)
            error('pp_fault_synth_export:BadOption', ...
                'row %d: kind is required (source or line)', index);
        else
            error('pp_fault_synth_export:BadOption', ...
                'row %d: kind must be source or line', index);
        end
    end
    if numel(sources) ~= 1
        error('pp_fault_synth_export:BadOption', ...
            'the feeder CSV needs exactly one source row');
    end
    if isempty(lines)
        error('pp_fault_synth_export:BadOption', ...
            'the feeder CSV needs at least one line row');
    end
    sourceSpec = sources{1};
end

function [sourceSpec, lines] = builtin_feeder(sourceFactor)
    z1 = z_from_magnitude(0.4, 10);
    sourceSpec = struct('bus_id', 'B0', 'z1', z1, 'z0', sourceFactor * z1);
    raw = { ...
        'L1', 'B0', 'B1', 1.5, 0.405, 0.525, 1.215, 1.575; ...
        'L2', 'B1', 'B2', 1.2, 0.48, 0.444, 1.44, 1.332; ...
        'L3', 'B2', 'B3', 0.8, 0.44, 0.304, 1.32, 0.912; ...
        'L4', 'B3', 'B4', 0.6, 0.39, 0.24, 1.17, 0.72};
    lines = repmat(line_template(), 1, size(raw, 1));
    for index = 1:size(raw, 1)
        lines(index).name = raw{index, 1};
        lines(index).from_bus = raw{index, 2};
        lines(index).to_bus = raw{index, 3};
        lines(index).length_km = raw{index, 4};
        lines(index).z1 = complex(raw{index, 5}, raw{index, 6});
        lines(index).z0 = complex(raw{index, 7}, raw{index, 8});
    end
end

function sourceSpec = parse_source(raw, index, defaultFactor)
    name = as_char(struct_get(raw, 'name'));
    if isempty(name)
        name = sprintf('source%d', index);
    end
    busId = as_char(struct_get(raw, 'from_bus'));
    if isempty(busId)
        error('pp_fault_synth_export:BadOption', ...
            '%s: source from_bus is the bus the grid connects to', name);
    end
    [z1, z0] = sequence_pair(raw, name, defaultFactor);
    sourceSpec = struct('bus_id', busId, 'z1', z1, 'z0', z0);
end

function line = parse_line(raw, index, defaultFactor)
    name = as_char(struct_get(raw, 'name'));
    if isempty(name)
        name = sprintf('L%d', index);
    end
    fromBus = as_char(struct_get(raw, 'from_bus'));
    toBus = as_char(struct_get(raw, 'to_bus'));
    if isempty(fromBus) || isempty(toBus)
        error('pp_fault_synth_export:BadOption', ...
            '%s: from_bus and to_bus are required', name);
    end
    if strcmp(fromBus, toBus)
        error('pp_fault_synth_export:BadOption', ...
            '%s: from_bus and to_bus must differ', name);
    end
    lengthKm = optional_number(raw, 'length_km');
    if isempty(lengthKm)
        lengthKm = 0;
    end
    if lengthKm < 0
        error('pp_fault_synth_export:BadOption', '%s: length_km must be >= 0', name);
    end
    [z1, z0] = sequence_pair(raw, name, defaultFactor);
    line = line_template();
    line.name = name;
    line.from_bus = fromBus;
    line.to_bus = toBus;
    line.length_km = lengthKm;
    line.z1 = z1;
    line.z0 = z0;
end

function [z1, z0] = sequence_pair(raw, label, defaultFactor)
    r1 = optional_number(raw, 'r1_ohm');
    x1 = optional_number(raw, 'x1_ohm');
    zMag = optional_number(raw, 'z1_ohm');
    xOverR = optional_number(raw, 'x_over_r');
    explicit = ~isempty(r1) || ~isempty(x1);
    if explicit && ~isempty(zMag)
        error('pp_fault_synth_export:BadOption', ...
            '%s: pass r1_ohm/x1_ohm or z1_ohm, not both', label);
    end
    if explicit
        if ~isempty(r1) && r1 < 0
            error('pp_fault_synth_export:BadOption', '%s: resistance must be >= 0', label);
        end
        if isempty(r1)
            r1 = 0;
        end
        if isempty(x1)
            x1 = 0;
        end
        z1 = complex(r1, x1);
    elseif ~isempty(zMag)
        if isempty(xOverR)
            xOverR = Inf;
        end
        z1 = z_from_magnitude(zMag, xOverR);
    else
        error('pp_fault_synth_export:BadOption', ...
            '%s: positive-sequence impedance is required', label);
    end
    if ~(abs(z1) > 0)
        error('pp_fault_synth_export:BadOption', ...
            '%s: impedance magnitude must be positive', label);
    end
    r0 = optional_number(raw, 'r0_ohm');
    x0 = optional_number(raw, 'x0_ohm');
    factor = optional_number(raw, 'z0_factor');
    if (~isempty(r0) || ~isempty(x0)) && ~isempty(factor)
        error('pp_fault_synth_export:BadOption', ...
            '%s: pass r0_ohm/x0_ohm or z0_factor, not both', label);
    end
    if ~isempty(r0) || ~isempty(x0)
        if ~isempty(r0) && r0 < 0
            error('pp_fault_synth_export:BadOption', '%s: resistance must be >= 0', label);
        end
        if isempty(r0)
            r0 = 0;
        end
        if isempty(x0)
            x0 = 0;
        end
        z0 = complex(r0, x0);
    else
        if isempty(factor)
            used = defaultFactor;
        else
            used = factor;
        end
        if ~(used > 0)
            error('pp_fault_synth_export:BadOption', ...
                '%s: z0_factor must be a positive finite number', label);
        end
        z0 = used * z1;
    end
    if ~(abs(z0) > 0)
        error('pp_fault_synth_export:BadOption', ...
            '%s: zero-sequence impedance magnitude must be positive', label);
    end
end

function z = z_from_magnitude(magnitude, xOverR)
    if ~(magnitude > 0)
        error('pp_fault_synth_export:BadOption', 'z1_ohm must be a positive finite number');
    end
    if isinf(xOverR)
        if xOverR > 0
            z = complex(0, magnitude);
        else
            z = complex(0, -magnitude);
        end
        return
    end
    scale = sqrt(1 + xOverR * xOverR);
    resistance = magnitude / scale;
    z = complex(resistance, resistance * xOverR);
end

function points = walk_radial(sourceSpec, lines, vLl)
    busNames = {sourceSpec.bus_id};
    for index = 1:numel(lines)
        busNames = add_name(busNames, lines(index).from_bus);
        busNames = add_name(busNames, lines(index).to_bus);
    end
    neighbors = cell(1, numel(busNames));
    for index = 1:numel(lines)
        left = find_bus(busNames, lines(index).from_bus);
        right = find_bus(busNames, lines(index).to_bus);
        neighbors{left}(end + 1) = index; %#ok<AGROW>
        neighbors{right}(end + 1) = index; %#ok<AGROW>
    end
    root = find_bus(busNames, sourceSpec.bus_id);
    known = false(1, numel(busNames));
    known(root) = true;
    queue = root;
    head = 1;
    seen = false(1, numel(lines));
    points = repmat(point_template(), 1, numel(busNames));
    kept = 1;
    points(1) = point_template();
    points(1).bus_id = sourceSpec.bus_id;
    points(1).line_id = 'source';
    points(1).distance_km = 0;
    points(1).z1 = sourceSpec.z1;
    points(1).z0 = sourceSpec.z0;
    points(1).v_ll_v = vLl;
    points(1).order = 0;
    while head <= numel(queue)
        current = queue(head);
        head = head + 1;
        parent = points(find_point(points, kept, busNames{current}));
        for nIndex = 1:numel(neighbors{current})
            lineIndex = neighbors{current}(nIndex);
            if seen(lineIndex)
                continue
            end
            seen(lineIndex) = true;
            otherName = other_end(lines(lineIndex), busNames{current});
            other = find_bus(busNames, otherName);
            if known(other)
                error('pp_fault_synth_export:BadOption', ...
                    '%s: the feeder has a loop. The zbus engine is a radial tree', ...
                    lines(lineIndex).name);
            end
            known(other) = true;
            kept = kept + 1;
            points(kept) = point_template();
            points(kept).bus_id = otherName;
            points(kept).line_id = lines(lineIndex).name;
            points(kept).distance_km = parent.distance_km + lines(lineIndex).length_km;
            points(kept).z1 = parent.z1 + lines(lineIndex).z1;
            points(kept).z0 = parent.z0 + lines(lineIndex).z0;
            points(kept).v_ll_v = vLl;
            points(kept).order = kept - 1;
            queue(end + 1) = other; %#ok<AGROW>
        end
    end
    points = points(1:kept);
    if ~all(seen)
        error('pp_fault_synth_export:BadOption', ...
            'every line must belong to the radial tree fed by the source bus');
    end
    if numel(lines) > 0 && numel(points) == 1
        error('pp_fault_synth_export:BadOption', ...
            'source bus %s is not connected to a line', sourceSpec.bus_id);
    end
end

function points = filter_buses(points, busFilter)
    keep = false(1, numel(points));
    known = {points.bus_id};
    for index = 1:numel(busFilter)
        if ~any(strcmp(known, busFilter{index}))
            error('pp_fault_synth_export:BadOption', 'unknown bus ''%s''', busFilter{index});
        end
    end
    for index = 1:numel(points)
        keep(index) = any(strcmp(busFilter, points(index).bus_id));
    end
    points = points(keep);
    if isempty(points)
        error('pp_fault_synth_export:BadOption', 'bus filter removed every bus');
    end
end

function specs = selected_specs(names)
    catalog = fault_catalog();
    specs = catalog([]);
    for index = 1:numel(names)
        for slot = 1:numel(catalog)
            if strcmp(catalog(slot).name, names{index})
                specs(end + 1) = catalog(slot); %#ok<AGROW>
            end
        end
    end
end

function specs = fault_catalog()
    specs = repmat(spec_template(), 1, 7);
    specs(1) = spec_row('AG', 'slg', 0, 1, 'phase-to-ground');
    specs(2) = spec_row('BG', 'slg', 1, 2, 'phase-to-ground');
    specs(3) = spec_row('CG', 'slg', 2, 3, 'phase-to-ground');
    specs(4) = spec_row('AB', 'll', 2, 4, 'phase-to-phase');
    specs(5) = spec_row('BC', 'll', 0, 5, 'phase-to-phase');
    specs(6) = spec_row('CA', 'll', 1, 6, 'phase-to-phase');
    specs(7) = spec_row('ABC', 'abc', 0, 7, 'three-phase');
end

function samples = build_grid(points, specs, resistances, sBaseVa)
    nRows = numel(points) * numel(specs) * numel(resistances);
    samples = repmat(sample_template(), 1, nRows);
    cursor = 1;
    for pIndex = 1:numel(points)
        for sIndex = 1:numel(specs)
            for rIndex = 1:numel(resistances)
                samples(cursor) = evaluate_case( ...
                    points(pIndex), specs(sIndex), resistances(rIndex), sBaseVa);
                cursor = cursor + 1;
            end
        end
    end
end

function sample = evaluate_case(point, spec, resistance, sBaseVa)
    eVolts = point.v_ll_v / sqrt(3);
    [va, vb, vc, ia, ib, ic] = fault_phasors(point.z1, point.z0, resistance, spec.family, eVolts);
    [va, vb, vc, ia, ib, ic] = cycle_phases(va, vb, vc, ia, ib, ic, spec.steps);
    if strcmp(spec.family, 'abc')
        iFault = ia;
    elseif strcmp(spec.family, 'slg')
        iFault = ia + ib + ic;
    else
        iFault = largest_current(ia, ib, ic);
    end
    vBase = eVolts;
    iBase = sBaseVa / (sqrt(3) * point.v_ll_v);
    vaPu = clean_number(abs(va) / vBase);
    vbPu = clean_number(abs(vb) / vBase);
    vcPu = clean_number(abs(vc) / vBase);
    iaA = clean_number(abs(ia));
    ibA = clean_number(abs(ib));
    icA = clean_number(abs(ic));
    iFaultA = clean_number(abs(iFault));
    sample = sample_template();
    sample.sample_id = 0;
    sample.bus_id = point.bus_id;
    sample.line_id = point.line_id;
    sample.distance_km = point.distance_km;
    sample.fault_type = spec.name;
    sample.fault_type_code = spec.code;
    sample.label_protect = spec.label;
    sample.r_f_ohm = resistance;
    sample.v_a_pu = vaPu;
    sample.v_b_pu = vbPu;
    sample.v_c_pu = vcPu;
    sample.v_bus_mag_pu = min([vaPu, vbPu, vcPu]);
    sample.i_phase_a_a = iaA;
    sample.i_phase_b_a = ibA;
    sample.i_phase_c_a = icA;
    sample.i_fault_mag_a = iFaultA;
    sample.i_fault_mag_pu = clean_number(iFaultA / iBase);
    sample.engine = 'zbus';
end

function [va, vb, vc, ia, ib, ic] = fault_phasors(z1, z0, resistance, family, eVolts)
    a = complex(-0.5, sqrt(3) / 2);
    a2 = complex(-0.5, -sqrt(3) / 2);
    z2 = z1;
    if strcmp(family, 'abc')
        den = z1 + resistance;
        assert_nonzero(den);
        i1 = eVolts / den;
        ia = i1;
        ib = a2 * i1;
        ic = a * i1;
        va = i1 * resistance;
        vb = a2 * va;
        vc = a * va;
        return
    end
    if strcmp(family, 'slg')
        den = z1 + z2 + z0 + 3 * resistance;
        assert_nonzero(den);
        i1 = eVolts / den;
        ia = 3 * i1;
        ib = 0;
        ic = 0;
        v1 = eVolts - i1 * z1;
        v2 = -i1 * z2;
        v0 = -i1 * z0;
        va = v0 + v1 + v2;
        vb = v0 + a2 * v1 + a * v2;
        vc = v0 + a * v1 + a2 * v2;
        return
    end
    den = z1 + z2 + resistance;
    assert_nonzero(den);
    i1 = eVolts / den;
    i2 = -i1;
    ia = 0;
    ib = a2 * i1 + a * i2;
    ic = a * i1 + a2 * i2;
    v1 = eVolts - i1 * z1;
    v2 = -i2 * z2;
    va = v1 + v2;
    vb = a2 * v1 + a * v2;
    vc = a * v1 + a2 * v2;
end

function [va, vb, vc, ia, ib, ic] = cycle_phases(va, vb, vc, ia, ib, ic, steps)
    volts = [va, vb, vc];
    amps = [ia, ib, ic];
    if steps == 0
        order = [1, 2, 3];
    elseif steps == 1
        order = [3, 1, 2];
    else
        order = [2, 3, 1];
    end
    va = volts(order(1));
    vb = volts(order(2));
    vc = volts(order(3));
    ia = amps(order(1));
    ib = amps(order(2));
    ic = amps(order(3));
end

function current = largest_current(ia, ib, ic)
    currents = [ia, ib, ic];
    [~, index] = max(abs(currents));
    current = currents(index);
end

function assert_nonzero(value)
    if abs(value) < 1e-12
        error('pp_fault_synth_export:BadOption', ...
            'fault impedance cancels the Thevenin impedance');
    end
end

function value = clean_number(value)
    if abs(value) <= 1e-9
        value = 0;
    end
end

function samples = subsample_rows(samples, nSamples, seed)
    if isempty(nSamples) || nSamples == numel(samples)
        return
    end
    if nSamples > numel(samples)
        error('pp_fault_synth_export:BadOption', 'n_samples exceeds the fault grid');
    end
    state = mod(seed, 2147483647);
    if state <= 0
        state = 1;
    end
    order = 1:numel(samples);
    for index = numel(order):-1:2
        state = mod(16807 * state, 2147483647);
        swap = mod(state, index) + 1;
        temp = order(index);
        order(index) = order(swap);
        order(swap) = temp;
    end
    samples = samples(order(1:nSamples));
end

function busId = remote_bus(points)
    best = 1;
    bestScore = points(1).distance_km * 1e6 + points(1).order;
    for index = 2:numel(points)
        score = points(index).distance_km * 1e6 + points(index).order;
        if score > bestScore
            best = index;
            bestScore = score;
        end
    end
    busId = points(best).bus_id;
end

function text = format_preview(result)
    if result.n_samples == result.n_grid
        countText = sprintf('samples=%d', result.n_samples);
    else
        countText = sprintf('samples=%d grid=%d', result.n_samples, result.n_grid);
    end
    parts = {sprintf('pp-fault-synth-export: engine=%s network=%s %s', ...
        result.engine, result.network, countText)};
    ag = represent_sample(result, 'AG');
    if ~isempty(ag)
        parts{end + 1} = sprintf('AG@%s Rf=%.4f If=%.4f A Vmin=%.4f pu', ...
            ag.bus_id, ag.r_f_ohm, ag.i_fault_mag_a, ag.v_bus_mag_pu); %#ok<AGROW>
    end
    bc = represent_sample(result, 'BC');
    if ~isempty(bc)
        parts{end + 1} = sprintf('BC@%s If=%.4f A', bc.bus_id, bc.i_fault_mag_a); %#ok<AGROW>
    end
    abc = represent_sample(result, 'ABC');
    if ~isempty(abc)
        parts{end + 1} = sprintf('ABC@%s If=%.4f A', abc.bus_id, abc.i_fault_mag_a); %#ok<AGROW>
    end
    text = strjoin(parts, '  ');
end

function text = format_summary(result)
    if result.n_samples == result.n_grid
        countText = sprintf('samples=%d', result.n_samples);
    else
        countText = sprintf('samples=%d grid=%d', result.n_samples, result.n_grid);
    end
    catalog = fault_catalog();
    lines = cell(1, numel(catalog) + 3);
    lines{1} = sprintf(['engine=%s  network=%s  V=%.4f kV  S_base=%.4f MVA  ', ...
        'Z_base=%.4f ohm  I_base=%.4f A  %s  seed=%d'], ...
        result.engine, result.network, result.v_kv, result.s_base_mva, ...
        result.z_base_ohm, result.i_base_a, countText, result.seed);
    lines{2} = sprintf(['%-4s %4s  %-16s %5s %-8s %8s %12s %8s ', ...
        '%8s %8s %8s %12s %12s %12s'], ...
        'type', 'code', 'label', 'count', 'bus', 'Rf', 'If_A', 'Vmin', ...
        'Va', 'Vb', 'Vc', 'Ia', 'Ib', 'Ic');
    for index = 1:numel(catalog)
        spec = catalog(index);
        count = count_fault(result.samples, spec.name);
        row = represent_sample(result, spec.name);
        if isempty(row)
            lines{index + 2} = sprintf(['%-4s %4d  %-16s %5d %-8s %8s %12s %8s ', ...
                '%8s %8s %8s %12s %12s %12s'], ...
                spec.name, spec.code, spec.label, 0, ...
                '-', '-', '-', '-', '-', '-', '-', '-', '-', '-');
        else
            lines{index + 2} = sprintf(['%-4s %4d  %-16s %5d %-8s %8.4f %12.4f ', ...
                '%8.4f %8.4f %8.4f %8.4f %12.4f %12.4f %12.4f'], ...
                spec.name, spec.code, spec.label, count, row.bus_id, row.r_f_ohm, ...
                row.i_fault_mag_a, row.v_bus_mag_pu, row.v_a_pu, row.v_b_pu, row.v_c_pu, ...
                row.i_phase_a_a, row.i_phase_b_a, row.i_phase_c_a);
        end
    end
    remoteText = remote_line(result);
    if isempty(remoteText)
        lines = lines(1:numel(catalog) + 2);
    else
        lines{numel(catalog) + 3} = remoteText;
    end
    text = strjoin(lines, char(10));
end

function text = remote_line(result)
    faults = {'AG', 'BC', 'ABC'};
    remoteRows = result.samples([]);
    for index = 1:numel(result.samples)
        sample = result.samples(index);
        if strcmp(sample.bus_id, result.remote_bus) && any(strcmp(faults, sample.fault_type))
            remoteRows(end + 1) = sample; %#ok<AGROW>
        end
    end
    if isempty(remoteRows)
        text = '';
        return
    end
    remoteRf = min([remoteRows.r_f_ohm]);
    bits = {};
    for index = 1:numel(faults)
        for rowIndex = 1:numel(remoteRows)
            sample = remoteRows(rowIndex);
            if strcmp(sample.fault_type, faults{index}) && sample.r_f_ohm == remoteRf
                bits{end + 1} = sprintf('If_%s=%.4f A', faults{index}, sample.i_fault_mag_a); %#ok<AGROW>
                break
            end
        end
    end
    text = sprintf('remote bus=%s distance=%.4f km Rf=%.4f %s', ...
        result.remote_bus, remoteRows(1).distance_km, remoteRf, strjoin(bits, ' '));
end

function row = represent_sample(result, fault)
    row = represent_at(result.samples, fault, result.anchor_bus);
    if ~isempty(row)
        return
    end
    best = [];
    for index = 1:numel(result.samples)
        sample = result.samples(index);
        if ~strcmp(sample.fault_type, fault)
            continue
        end
        if isempty(best) || sample.r_f_ohm < best.r_f_ohm || ...
                (sample.r_f_ohm == best.r_f_ohm && sample.sample_id < best.sample_id)
            best = sample;
        end
    end
    row = best;
end

function row = represent_at(samples, fault, busId)
    row = [];
    for index = 1:numel(samples)
        sample = samples(index);
        if ~strcmp(sample.fault_type, fault) || ~strcmp(sample.bus_id, busId)
            continue
        end
        if isempty(row) || sample.r_f_ohm < row.r_f_ohm || ...
                (sample.r_f_ohm == row.r_f_ohm && sample.sample_id < row.sample_id)
            row = sample;
        end
    end
end

function count = count_fault(samples, fault)
    count = 0;
    for index = 1:numel(samples)
        if strcmp(samples(index).fault_type, fault)
            count = count + 1;
        end
    end
end

function write_samples_csv(csvPath, samples)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fields = {'sample_id', 'bus_id', 'line_id', 'distance_km', 'fault_type', ...
        'fault_type_code', 'label_protect', 'R_f_ohm', 'V_a_pu', 'V_b_pu', 'V_c_pu', ...
        'V_bus_mag_pu', 'I_phase_a_A', 'I_phase_b_A', 'I_phase_c_A', ...
        'I_fault_mag_A', 'I_fault_mag_pu', 'engine'};
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('pp_fault_synth_export:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s\n', strjoin(fields, ','));
    for index = 1:numel(samples)
        row = samples(index);
        fprintf(fid, '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n', ...
            csv_num(row.sample_id), csv_cell(row.bus_id), csv_cell(row.line_id), ...
            csv_num(row.distance_km), csv_cell(row.fault_type), csv_num(row.fault_type_code), ...
            csv_cell(row.label_protect), csv_num(row.r_f_ohm), ...
            csv_num(row.v_a_pu), csv_num(row.v_b_pu), csv_num(row.v_c_pu), ...
            csv_num(row.v_bus_mag_pu), csv_num(row.i_phase_a_a), csv_num(row.i_phase_b_a), ...
            csv_num(row.i_phase_c_a), csv_num(row.i_fault_mag_a), csv_num(row.i_fault_mag_pu), ...
            csv_cell(row.engine));
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
    bolted = min([result.samples.r_f_ohm]);
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 80 980 740], ...
        'Name', 'pp-fault-synth-export', 'NumberTitle', 'off');
    codes = {'AG', 'BC', 'ABC'};
    labels = {'AG (phase-to-ground)', 'BC (phase-to-phase)', 'ABC (three-phase)'};
    colors = [31, 78, 121; 192, 57, 43; 17, 122, 101] / 255;
    yLabels = {'Fault current (A)', 'Minimum phase voltage (pu)'};
    for panel = 1:2
        ax = subplot(2, 1, panel);
        hold(ax, 'on');
        for index = 1:numel(codes)
            [xs, ys] = series_xy(result, codes{index}, bolted, panel);
            if isempty(xs)
                continue
            end
            plotted = plot(ax, xs, ys, '-o', 'Color', colors(index, :), ...
                'LineWidth', 2, 'MarkerFaceColor', colors(index, :));
            set(plotted, 'DisplayName', labels{index});
        end
        ylabel(ax, yLabels{panel});
        grid(ax, 'on');
        set(ax, 'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.6);
        legend(ax, 'Location', 'best');
        set(ax, 'FontSize', 11);
        box(ax, 'on');
        if panel == 1
            title(ax, sprintf('%s short-circuit samples at Rf=%.4g ohm', ...
                result.network, bolted));
        else
            xlabel(ax, 'Distance from source (km)');
        end
    end
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

function [xs, ys] = series_xy(result, code, bolted, panel)
    xs = [];
    ys = [];
    for index = 1:numel(result.samples)
        sample = result.samples(index);
        if strcmp(sample.fault_type, code) && sample.r_f_ohm == bolted
            xs(end + 1) = sample.distance_km; %#ok<AGROW>
            if panel == 1
                ys(end + 1) = sample.i_fault_mag_a; %#ok<AGROW>
            else
                ys(end + 1) = sample.v_bus_mag_pu; %#ok<AGROW>
            end
        end
    end
    if isempty(xs)
        return
    end
    [xs, order] = sort(xs);
    ys = ys(order);
end

function rows = read_feeder_csv(csvPath)
    if exist(csvPath, 'file') ~= 2
        error('pp_fault_synth_export:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if numel(raw) >= 3 && raw(1) == char(239) && raw(2) == char(187) && raw(3) == char(191)
        raw = raw(4:end);
    end
    raw = strrep(raw, char(13), '');
    if isempty(strtrim(raw))
        error('pp_fault_synth_export:EmptyCsv', 'CSV is empty: %s', csvPath);
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
        error('pp_fault_synth_export:EmptyCsv', 'CSV is empty: %s', csvPath);
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
            error('pp_fault_synth_export:BadOption', 'unknown column ''%s''', strtrim(headers{col}));
        end
        canons{col} = canon;
    end
    rows = cell(1, numel(dataLines));
    kept = 0;
    for rowIndex = 1:numel(dataLines)
        cells = split_line(dataLines{rowIndex}, delimiter);
        if numel(cells) ~= numel(headers)
            error('pp_fault_synth_export:BadOption', ...
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
                error('pp_fault_synth_export:BadOption', 'duplicate column %s', canon);
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
        error('pp_fault_synth_export:EmptyCsv', 'CSV has no data rows: %s', csvPath);
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
        case {'kind', 'type'}
            canon = 'kind';
        case {'name', 'element', 'id'}
            canon = 'name';
        case {'frombus', 'from', 'bus', 'busfrom'}
            canon = 'from_bus';
        case {'tobus', 'to', 'busto'}
            canon = 'to_bus';
        case {'lengthkm', 'length', 'km'}
            canon = 'length_km';
        case {'r1ohm', 'r1'}
            canon = 'r1_ohm';
        case {'x1ohm', 'x1'}
            canon = 'x1_ohm';
        case {'r0ohm', 'r0'}
            canon = 'r0_ohm';
        case {'x0ohm', 'x0'}
            canon = 'x0_ohm';
        case {'z1ohm', 'z1'}
            canon = 'z1_ohm';
        case {'xoverr', 'xr'}
            canon = 'x_over_r';
        case {'z0factor', 'k0'}
            canon = 'z0_factor';
        otherwise
            canon = '';
    end
end

function names = add_name(names, name)
    if ~any(strcmp(names, name))
        names{end + 1} = name; %#ok<AGROW>
    end
end

function index = find_bus(names, name)
    index = find(strcmp(names, name), 1, 'first');
    if isempty(index)
        error('pp_fault_synth_export:BadOption', 'unknown bus ''%s''', name);
    end
end

function index = find_point(points, kept, name)
    index = [];
    for slot = 1:kept
        if strcmp(points(slot).bus_id, name)
            index = slot;
            return
        end
    end
end

function other = other_end(line, bus)
    if strcmp(line.from_bus, bus)
        other = line.to_bus;
    else
        other = line.from_bus;
    end
end

function row = point_template()
    row = struct('bus_id', '', 'line_id', '', 'distance_km', 0, ...
        'z1', complex(0, 0), 'z0', complex(0, 0), 'v_ll_v', 0, 'order', 0);
end

function row = line_template()
    row = struct('name', '', 'from_bus', '', 'to_bus', '', ...
        'length_km', 0, 'z1', complex(0, 0), 'z0', complex(0, 0));
end

function row = spec_template()
    row = struct('name', '', 'family', '', 'steps', 0, 'code', 0, 'label', '');
end

function row = spec_row(name, family, steps, code, label)
    row = spec_template();
    row.name = name;
    row.family = family;
    row.steps = steps;
    row.code = code;
    row.label = label;
end

function row = sample_template()
    row = struct( ...
        'sample_id', 0, ...
        'bus_id', '', ...
        'line_id', '', ...
        'distance_km', 0, ...
        'fault_type', '', ...
        'fault_type_code', 0, ...
        'label_protect', '', ...
        'r_f_ohm', 0, ...
        'v_a_pu', 0, ...
        'v_b_pu', 0, ...
        'v_c_pu', 0, ...
        'v_bus_mag_pu', 0, ...
        'i_phase_a_a', 0, ...
        'i_phase_b_a', 0, ...
        'i_phase_c_a', 0, ...
        'i_fault_mag_a', 0, ...
        'i_fault_mag_pu', 0, ...
        'engine', 'zbus');
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('pp_fault_synth_export:BadOption', '%s must be a positive finite number', name);
    end
end

function number = nonnegative_number(name, value)
    number = finite_number(name, value);
    if number < 0
        error('pp_fault_synth_export:BadOption', '%s must be >= 0', name);
    end
end

function number = positive_integer(name, value)
    number = finite_number(name, value);
    if ~(number > 0) || number ~= round(number)
        error('pp_fault_synth_export:BadOption', '%s must be a positive integer', name);
    end
    number = round(number);
end

function number = seed_number(value)
    number = finite_number('seed', value);
    if number ~= round(number)
        error('pp_fault_synth_export:BadOption', 'seed must be an integer');
    end
    number = round(number);
end

function number = finite_number(name, value)
    if iscell(value)
        if numel(value) ~= 1
            error('pp_fault_synth_export:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if ischar(value) || is_matlab_string(value)
        number = str2double(strtrim(to_char(value)));
    elseif isnumeric(value)
        number = double(value);
    else
        error('pp_fault_synth_export:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('pp_fault_synth_export:BadOption', '%s must be a finite number', name);
    end
end

function number = optional_number(data, field)
    if ~isfield(data, field) || is_blank(data.(field))
        number = [];
        return
    end
    number = finite_number(field, data.(field));
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

function text = csv_num(value)
    if ~isfinite(value)
        text = '';
        return
    end
    rounded = round(value);
    if value == rounded && abs(value) < 1e15
        text = sprintf('%.0f', value);
        return
    end
    text = sprintf('%.12g', value);
end

function text = csv_cell(value)
    text = to_char(value);
    if any(text == ',') || any(text == '"') || any(text == char(10)) || any(text == char(13))
        text = ['"', strrep(text, '"', '""'), '"'];
    end
end
