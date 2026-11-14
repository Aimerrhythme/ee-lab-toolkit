function result = grid_to_graph_export(varargin)
%GRID_TO_GRAPH_EXPORT Bus graph, edge table, and positive-sequence Ybus.
%   RESULT = GRID_TO_GRAPH_EXPORT()
%   RESULT = GRID_TO_GRAPH_EXPORT('grid.csv', 'output_dir', 'out', ...
%       'output_png', 'graph.png', 'show', false)
%
%   Series impedance is ohms referred to the from-bus. b_siemens is the
%   total charging susceptance and g_siemens is the total shunt conductance,
%   both in siemens at the from-bus voltage. The off-nominal tap and the
%   phase shift sit on the from side.
%       z_base = vn_from_kv^2 / s_base_mva
%       y_base = s_base_mva / vn_from_kv^2
%       Ys = 1 / (r_pu + j x_pu)
%       a = tap * exp(j * shift_deg * pi / 180)
%       Yff = (Ys + Ysh / 2) / |a|^2
%       Yft = -Ys / conj(a)
%       Ytf = -Ys / a
%       Ytt = Ys + Ysh / 2
%   A bus shunt is added to the diagonal only. Out-of-service branches stay
%   in the branch table and stay out of the adjacency matrix and Ybus.
%   Parallel in-service branches still set one adjacency entry.
%
%   This file is engine 'builtin'. It matches Python engine='builtin'.
%   engine 'auto' means builtin here. engine 'pandapower' is Python only.
%   Exported bus_index, edge_index, and from_index / to_index are 0-based.
%
%   Name-value keys: s_base_mva, engine, network, self_loop, csv_path,
%   output_dir, output_png, show.
%
%   RESULT.preview and RESULT.summary are the same text Python prints.

    [source, rest] = split_source(varargin);
    assert_pairs(rest);
    parser = inputParser;
    parser.FunctionName = 'grid_to_graph_export';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('s_base_mva', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('engine', 'builtin', @is_text_scalar);
    parser.addParameter('network', '', @is_text_scalar);
    parser.addParameter('self_loop', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_dir', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    engineName = normalize_engine(opt.engine);
    if strcmp(engineName, 'pandapower')
        error('grid_to_graph_export:BadInput', ...
            ['engine ''pandapower'' is the Python path. ', ...
            'MATLAB implements engine ''builtin''']);
    end
    if strcmp(engineName, 'auto')
        engineName = 'builtin';
    end
    networkName = strtrim(to_char(opt.network));
    if ~isempty(networkName) && ~any(strcmpi(networkName, {'synthetic', 'builtin'}))
        error('grid_to_graph_export:BadInput', ...
            'network ''%s'' needs engine ''pandapower''. The builtin engine reads the synthetic CSV', ...
            networkName);
    end
    if isempty(opt.s_base_mva)
        base = 10;
    else
        base = positive_number('s_base_mva', opt.s_base_mva);
    end
    selfLoop = coerce_bool(opt.self_loop, 'self_loop');
    showFig = coerce_bool(opt.show, 'show');
    csvPath = resolve_csv(source, opt.csv_path);
    [busesIn, branchesIn, shuntsIn] = load_grid(csvPath);
    if same_file(csvPath, default_csv())
        netName = 'synthetic';
    else
        [~, netName, ~] = fileparts(csvPath);
    end

    [outBuses, outBranches, outShunts, outEdges, adjacency, ybus, preview] = ...
        assemble(busesIn, branchesIn, shuntsIn, base, engineName, netName, selfLoop);
    summary = format_summary(preview, outBuses, ybus);

    outputDir = strtrim(to_char(opt.output_dir));
    outputPng = strtrim(to_char(opt.output_png));
    if ~isempty(outputDir)
        write_bundle(outputDir, outBuses, outBranches, outShunts, outEdges, adjacency, ybus);
    end
    fig = [];
    if ~isempty(outputPng) || showFig
        fig = render_figure(outBuses, outBranches, ybus, netName, outputPng, showFig);
    end

    result = struct();
    result.engine = engineName;
    result.network = netName;
    result.s_base_mva = base;
    result.self_loop = selfLoop;
    result.n_bus = numel(outBuses);
    result.n_branch = numel(outBranches);
    result.n_branch_in_service = count_in_service(outBranches);
    result.n_edge = numel(outEdges);
    result.n_shunt = numel(outShunts);
    result.n_shunt_in_service = count_in_service(outShunts);
    result.bus_ids = {outBuses.bus_id};
    result.buses = outBuses;
    result.branches = outBranches;
    result.shunts = outShunts;
    result.edges = outEdges;
    result.adjacency = adjacency;
    result.ybus = ybus;
    result.preview = preview;
    result.summary = summary;
    result.output_dir = outputDir;
    result.output_png = outputPng;
    result.fig = fig;
end

function [buses, branches, shuntsOut, edges, adjacency, ybus, preview] = ...
        assemble(busesIn, branchesIn, shuntsIn, base, engineName, netName, selfLoop)
    if isempty(busesIn)
        error('grid_to_graph_export:BadInput', 'no in-service bus');
    end
    assert_unique({busesIn.bus_id}, 'bus_id');
    keptMask = [busesIn.in_service] == 1;
    kept = busesIn(keptMask);
    if isempty(kept)
        error('grid_to_graph_export:BadInput', 'no in-service bus');
    end
    index = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for i = 1:numel(kept)
        index(kept(i).bus_id) = i;
    end
    nBus = numel(kept);
    if ~isempty(branchesIn)
        assert_unique({branchesIn.branch_id}, 'branch_id');
    end
    if ~isempty(shuntsIn)
        assert_unique({shuntsIn.shunt_id}, 'shunt_id');
    end

    branches = repmat(branch_out_template(), 1, 0);
    for k = 1:numel(branchesIn)
        branches(end + 1) = solve_branch(branchesIn(k), busesIn, index, base); %#ok<AGROW>
    end
    for k = 1:numel(branches)
        branches(k).branch_index = k - 1;
    end
    shuntsOut = repmat(shunt_out_template(), 1, 0);
    for k = 1:numel(shuntsIn)
        shuntsOut(end + 1) = solve_shunt(shuntsIn(k), busesIn, index, base); %#ok<AGROW>
    end
    for k = 1:numel(shuntsOut)
        shuntsOut(k).shunt_index = k - 1;
    end

    adjacency = zeros(nBus, nBus);
    ybus = complex(zeros(nBus, nBus));
    edges = repmat(edge_template(), 1, 0);
    for k = 1:numel(branches)
        if ~branches(k).in_service
            continue
        end
        i = branches(k).from_index + 1;
        j = branches(k).to_index + 1;
        adjacency(i, j) = 1;
        adjacency(j, i) = 1;
        ybus(i, i) = ybus(i, i) + branches(k).yff;
        ybus(i, j) = ybus(i, j) + branches(k).yft;
        ybus(j, i) = ybus(j, i) + branches(k).ytf;
        ybus(j, j) = ybus(j, j) + branches(k).ytt;
        edges(end + 1) = make_edge(branches(k), 'forward', i - 1, j - 1, ...
            branches(k).yff, branches(k).yft, numel(edges)); %#ok<AGROW>
        edges(end + 1) = make_edge(branches(k), 'reverse', j - 1, i - 1, ...
            branches(k).ytt, branches(k).ytf, numel(edges)); %#ok<AGROW>
    end
    for k = 1:numel(shuntsOut)
        if shuntsOut(k).in_service && ~isnan(shuntsOut(k).bus_index)
            i = shuntsOut(k).bus_index + 1;
            ybus(i, i) = ybus(i, i) + shuntsOut(k).g_pu + 1i * shuntsOut(k).b_pu;
        end
    end
    if selfLoop
        adjacency(1:nBus + 1:end) = 1;
    end

    buses = repmat(bus_out_template(), 1, nBus);
    for i = 1:nBus
        src = kept(i);
        [zBase, yBase] = bases(src.vn_kv, base);
        [pKnown, qKnown, vKnown, thetaKnown] = masks_of(src.bus_type);
        item = bus_out_template();
        item.bus_index = i - 1;
        item.bus_id = src.bus_id;
        item.bus_name = src.bus_name;
        item.bus_type = src.bus_type;
        item.bus_type_code = type_code(src.bus_type);
        item.vn_kv = src.vn_kv;
        item.z_base_ohm = zBase;
        item.y_base_s = yBase;
        item.p_mw = src.p_mw;
        item.q_mvar = src.q_mvar;
        item.vm_pu = src.vm_pu;
        item.va_deg = src.va_deg;
        item.p_known = pKnown;
        item.q_known = qKnown;
        item.v_known = vKnown;
        item.theta_known = thetaKnown;
        item.degree = sum(adjacency(i, :)) - adjacency(i, i);
        item.in_service = 1;
        item.x = src.x;
        item.y = src.y;
        item.members = src.bus_id;
        buses(i) = item;
    end

    nIn = count_in_service(branches);
    nShuntIn = count_in_service(shuntsOut);
    preview = preview_line(engineName, netName, buses, branches, numel(branches), ...
        nIn, numel(edges), nShuntIn, selfLoop, adjacency, ybus);
end

function branch = solve_branch(raw, busesIn, index, base)
    fromBus = must_bus(busesIn, raw.from_bus, raw.branch_id);
    must_bus(busesIn, raw.to_bus, raw.branch_id);
    if strcmp(raw.from_bus, raw.to_bus)
        error('grid_to_graph_export:BadInput', ...
            'branch %s connects %s to itself', raw.branch_id, raw.from_bus);
    end
    if ~(isfinite(fromBus.vn_kv) && fromBus.vn_kv > 0)
        error('grid_to_graph_export:BadInput', '%s vn_kv must be positive', raw.branch_id);
    end
    [zBase, yBase] = bases(fromBus.vn_kv, base);
    [rPu, xPu, gPu, bPu, rOhm, xOhm, gS, bS] = branch_pu(raw, zBase, yBase);
    tap = raw.tap;
    if isnan(tap)
        tap = 1;
    end
    shift = raw.shift_deg;
    if isnan(shift)
        shift = 0;
    end
    inGraph = raw.in_service == 1 && isKey(index, raw.from_bus) && isKey(index, raw.to_bus);
    yff = 0;
    yft = 0;
    ytf = 0;
    ytt = 0;
    ys = 0;
    try
        [yff, yft, ytf, ytt, ys] = branch_stamp(rPu, xPu, gPu, bPu, tap, shift);
    catch exc
        if inGraph || text_has(exc.message, 'tap must')
            error('grid_to_graph_export:BadInput', 'branch %s: %s', raw.branch_id, exc.message);
        end
    end
    branch = branch_out_template();
    branch.branch_id = raw.branch_id;
    branch.element = raw.element;
    branch.from_bus = raw.from_bus;
    branch.to_bus = raw.to_bus;
    branch.from_index = map_index(index, raw.from_bus);
    branch.to_index = map_index(index, raw.to_bus);
    branch.r_ohm = rOhm;
    branch.x_ohm = xOhm;
    branch.b_siemens = bS;
    branch.g_siemens = gS;
    branch.r_pu = rPu;
    branch.x_pu = xPu;
    branch.b_pu = bPu;
    branch.g_pu = gPu;
    branch.g_series = real(ys);
    branch.b_series = imag(ys);
    branch.tap = tap;
    branch.shift_deg = shift;
    branch.rate_mva = raw.rate_mva;
    branch.length_km = raw.length_km;
    branch.in_service = double(inGraph);
    branch.yff = yff;
    branch.yft = yft;
    branch.ytf = ytf;
    branch.ytt = ytt;
end

function [rPu, xPu, gPu, bPu, rOhm, xOhm, gS, bS] = branch_pu(raw, zBase, yBase)
    hasPu = ~isnan(raw.r_pu) || ~isnan(raw.x_pu);
    hasOhm = ~isnan(raw.r_ohm) || ~isnan(raw.x_ohm);
    if hasPu && hasOhm
        error('grid_to_graph_export:BadInput', ...
            'branch %s sets both ohm and pu series impedance', raw.branch_id);
    end
    if hasPu
        if isnan(raw.r_pu) || isnan(raw.x_pu)
            error('grid_to_graph_export:BadInput', ...
                'branch %s needs both r_pu and x_pu', raw.branch_id);
        end
        if ~isnan(raw.g_siemens) || ~isnan(raw.b_siemens)
            error('grid_to_graph_export:BadInput', ...
                'branch %s sets both siemens and pu shunt values', raw.branch_id);
        end
        rPu = raw.r_pu;
        xPu = raw.x_pu;
        gPu = zero_if_nan(raw.g_pu);
        bPu = zero_if_nan(raw.b_pu);
        rOhm = rPu * zBase;
        xOhm = xPu * zBase;
        gS = gPu * yBase;
        bS = bPu * yBase;
        return
    end
    if ~hasOhm
        error('grid_to_graph_export:BadInput', ...
            'branch %s needs r_ohm and x_ohm, or r_pu and x_pu', raw.branch_id);
    end
    if ~isnan(raw.g_pu) || ~isnan(raw.b_pu)
        error('grid_to_graph_export:BadInput', ...
            'branch %s sets both siemens and pu shunt values', raw.branch_id);
    end
    rOhm = zero_if_nan(raw.r_ohm);
    xOhm = zero_if_nan(raw.x_ohm);
    gS = zero_if_nan(raw.g_siemens);
    bS = zero_if_nan(raw.b_siemens);
    rPu = rOhm / zBase;
    xPu = xOhm / zBase;
    gPu = gS / yBase;
    bPu = bS / yBase;
end

function shunt = solve_shunt(raw, busesIn, index, base)
    bus = must_bus(busesIn, raw.bus_id, raw.shunt_id);
    if ~(isfinite(bus.vn_kv) && bus.vn_kv > 0)
        error('grid_to_graph_export:BadInput', '%s vn_kv must be positive', raw.shunt_id);
    end
    [~, yBase] = bases(bus.vn_kv, base);
    hasPu = ~isnan(raw.g_pu) || ~isnan(raw.b_pu);
    hasS = ~isnan(raw.g_siemens) || ~isnan(raw.b_siemens);
    if hasPu && hasS
        error('grid_to_graph_export:BadInput', ...
            'shunt %s sets both siemens and pu values', raw.shunt_id);
    end
    if ~hasPu && ~hasS
        error('grid_to_graph_export:BadInput', ...
            'shunt %s needs g_siemens or b_siemens', raw.shunt_id);
    end
    if hasPu
        gPu = zero_if_nan(raw.g_pu);
        bPu = zero_if_nan(raw.b_pu);
        gS = gPu * yBase;
        bS = bPu * yBase;
    else
        gS = zero_if_nan(raw.g_siemens);
        bS = zero_if_nan(raw.b_siemens);
        gPu = gS / yBase;
        bPu = bS / yBase;
    end
    inGraph = raw.in_service == 1 && isKey(index, raw.bus_id);
    shunt = shunt_out_template();
    shunt.shunt_id = raw.shunt_id;
    shunt.bus_id = raw.bus_id;
    shunt.bus_index = map_index(index, raw.bus_id);
    shunt.g_siemens = gS;
    shunt.b_siemens = bS;
    shunt.g_pu = gPu;
    shunt.b_pu = bPu;
    shunt.in_service = double(inGraph);
end

function [yff, yft, ytf, ytt, ys] = branch_stamp(rPu, xPu, gPu, bPu, tap, shiftDeg)
    if ~(isfinite(tap) && tap > 0)
        error('grid_to_graph_export:BadInput', 'tap must be positive');
    end
    if ~(isfinite(rPu) && isfinite(xPu) && isfinite(gPu) && isfinite(bPu) && isfinite(shiftDeg))
        error('grid_to_graph_export:BadInput', 'branch pi parameters must be finite');
    end
    series = rPu + 1i * xPu;
    if series == 0
        error('grid_to_graph_export:BadInput', 'zero series impedance');
    end
    ys = 1 / series;
    angle = shiftDeg * pi / 180;
    a = tap * (cos(angle) + 1i * sin(angle));
    ysh = gPu + 1i * bPu;
    yff = (ys + ysh / 2) / (tap * tap);
    yft = -ys / conj(a);
    ytf = -ys / a;
    ytt = ys + ysh / 2;
end

function edge = make_edge(branch, orientation, fromIndex, toIndex, ySelf, yMutual, edgeIndex)
    edge = edge_template();
    edge.edge_index = edgeIndex;
    edge.branch_id = branch.branch_id;
    edge.element = branch.element;
    edge.orientation = orientation;
    if strcmp(orientation, 'forward')
        edge.from_bus = branch.from_bus;
        edge.to_bus = branch.to_bus;
    else
        edge.from_bus = branch.to_bus;
        edge.to_bus = branch.from_bus;
    end
    edge.from_index = fromIndex;
    edge.to_index = toIndex;
    edge.r_pu = branch.r_pu;
    edge.x_pu = branch.x_pu;
    edge.b_pu = branch.b_pu;
    edge.g_pu = branch.g_pu;
    edge.g_series = branch.g_series;
    edge.b_series = branch.b_series;
    edge.tap = branch.tap;
    edge.shift_deg = branch.shift_deg;
    edge.rate_mva = branch.rate_mva;
    edge.length_km = branch.length_km;
    edge.y_self_g = real(ySelf);
    edge.y_self_b = imag(ySelf);
    edge.y_mutual_g = real(yMutual);
    edge.y_mutual_b = imag(yMutual);
end

function preview = preview_line(engineName, netName, buses, branches, nBranch, ...
        nIn, nEdge, nShuntIn, selfLoop, adjacency, ybus)
    ids = {buses.bus_id};
    nBus = numel(ids);
    bestI = [];
    bestJ = [];
    bestMag = -1;
    for i = 1:nBus
        for j = 1:nBus
            if i == j
                continue
            end
            mag = abs(ybus(i, j));
            if mag > bestMag
                bestMag = mag;
                bestI = i;
                bestJ = j;
            end
        end
    end
    if isempty(bestI)
        offText = 'off=none';
    else
        offText = sprintf('off[%s,%s]=%s', ids{bestI}, ids{bestJ}, fmt_jb(ybus(bestI, bestJ)));
    end
    tapText = 'tap=none';
    for k = 1:numel(branches)
        if ~branches(k).in_service
            continue
        end
        if abs(branches(k).tap - 1) > 1e-9 || abs(branches(k).shift_deg) > 1e-9
            tapText = sprintf('tap[%s]=%.4f Yfrom[%s]=%s Yto[%s]=%s', ...
                branches(k).branch_id, branches(k).tap, ...
                branches(k).from_bus, fmt_jb(branches(k).yff), ...
                branches(k).to_bus, fmt_jb(branches(k).ytt));
            break
        end
    end
    openNames = {};
    for k = 1:numel(branches)
        if ~branches(k).in_service
            openNames{end + 1} = branches(k).branch_id; %#ok<AGROW>
        end
    end
    if isempty(openNames)
        openText = 'none';
    else
        openText = strjoin(openNames, ',');
    end
    symmetric = double(isequal(adjacency, adjacency.'));
    preview = sprintf(['grid-to-graph-export: engine=%s network=%s buses=%d ', ...
        'branches=%d in_service=%d directed=%d shunts=%d ', ...
        'self_loop=%d Y[%s,%s]=%s %s %s open=%s adj_sym=%d'], ...
        engineName, netName, nBus, nBranch, nIn, nEdge, nShuntIn, ...
        double(selfLoop), ids{1}, ids{1}, fmt_jb(ybus(1, 1)), offText, tapText, ...
        openText, symmetric);
end

function summary = format_summary(preview, buses, ybus)
    lines = cell(1, numel(buses) + 2);
    lines{1} = preview;
    lines{2} = sprintf('%-6s %-6s %3s %10s %10s %10s %10s %8s %8s  known', ...
        'bus', 'type', 'deg', 'G', 'B', 'P_mw', 'Q_mvar', 'Vm', 'Va');
    for i = 1:numel(buses)
        bus = buses(i);
        lines{i + 2} = sprintf('%-6s %-6s %3d %10.4f %10.4f %s %s %8.4f %8.4f  %s', ...
            bus.bus_id, bus.bus_type, bus.degree, ...
            real(ybus(i, i)), imag(ybus(i, i)), ...
            fmt_opt(bus.p_mw, 10), fmt_opt(bus.q_mvar, 10), ...
            bus.vm_pu, bus.va_deg, known_text(bus));
    end
    summary = strjoin(lines, newline);
end

function [buses, branches, shunts] = load_grid(path)
    if exist(path, 'file') ~= 2
        error('grid_to_graph_export:BadInput', 'grid CSV not found: %s', path);
    end
    fid = fopen(path, 'r', 'n', 'UTF-8');
    if fid < 0
        error('grid_to_graph_export:BadInput', 'grid CSV not found: %s', path);
    end
    cleaner = onCleanup(@() fclose(fid));
    headerLine = fgetl(fid);
    if ~ischar(headerLine)
        error('grid_to_graph_export:BadInput', '%s has no header', path);
    end
    headerLine = strip_line(headerLine);
    header = split_csv_line(headerLine);
    col = struct();
    for k = 1:numel(header)
        key = norm_key(header{k});
        if ~isempty(key)
            col.(key) = k;
        end
    end
    buses = repmat(bus_in_template(), 1, 0);
    branches = repmat(branch_in_template(), 1, 0);
    shunts = repmat(shunt_in_template(), 1, 0);
    lineNo = 1;
    while true
        line = fgetl(fid);
        if ~ischar(line)
            break
        end
        lineNo = lineNo + 1;
        line = strip_line(line);
        if isempty(strtrim(line))
            continue
        end
        cells = split_csv_line(line);
        if all(cellfun(@(c) isempty(strtrim(c)), cells))
            continue
        end
        kindText = lower(strtrim(cell_of(cells, col, 'kind')));
        kind = kind_alias(kindText);
        if isempty(kind)
            error('grid_to_graph_export:BadInput', ...
                'row %d: kind must be bus, line, trafo, or shunt', lineNo);
        end
        name = cell_of(cells, col, 'name');
        if strcmp(kind, 'bus')
            buses(end + 1) = parse_bus(cells, col, name, lineNo); %#ok<AGROW>
        elseif strcmp(kind, 'shunt')
            shunts(end + 1) = parse_shunt(cells, col, name, lineNo, numel(shunts) + 1); %#ok<AGROW>
        else
            branches(end + 1) = parse_branch(cells, col, name, kind, lineNo, numel(branches) + 1); %#ok<AGROW>
        end
    end
    if isempty(buses)
        error('grid_to_graph_export:BadInput', '%s has no bus rows', path);
    end
end

function bus = parse_bus(cells, col, name, lineNo)
    busId = strtrim(cell_of(cells, col, 'bus_id'));
    if isempty(busId)
        error('grid_to_graph_export:BadInput', 'row %d: bus_id is required', lineNo);
    end
    busType = type_alias(lower(strtrim(cell_of(cells, col, 'bus_type'))));
    if isempty(busType)
        error('grid_to_graph_export:BadInput', ...
            'row %d: bus_type must be slack, pv, or pq', lineNo);
    end
    vn = require_float(cells, col, 'vn_kv', lineNo);
    if vn <= 0
        error('grid_to_graph_export:BadInput', 'row %d: vn_kv must be positive', lineNo);
    end
    pMw = optional_float(cells, col, 'p_mw', lineNo);
    qMvar = optional_float(cells, col, 'q_mvar', lineNo);
    vm = optional_float(cells, col, 'vm_pu', lineNo);
    va = optional_float(cells, col, 'va_deg', lineNo);
    if strcmp(busType, 'slack')
        if isnan(vm) || isnan(va)
            error('grid_to_graph_export:BadInput', ...
                'row %d: slack bus needs vm_pu and va_deg', lineNo);
        end
    elseif strcmp(busType, 'pv')
        if isnan(pMw) || isnan(vm)
            error('grid_to_graph_export:BadInput', ...
                'row %d: pv bus needs p_mw and vm_pu', lineNo);
        end
        if isnan(va)
            va = 0;
        end
    else
        if isnan(pMw) || isnan(qMvar)
            error('grid_to_graph_export:BadInput', ...
                'row %d: pq bus needs p_mw and q_mvar', lineNo);
        end
        if isnan(vm)
            vm = 1;
        end
        if isnan(va)
            va = 0;
        end
    end
    bus = bus_in_template();
    bus.bus_id = busId;
    if isempty(strtrim(name))
        bus.bus_name = busId;
    else
        bus.bus_name = strtrim(name);
    end
    bus.bus_type = busType;
    bus.vn_kv = vn;
    bus.p_mw = pMw;
    bus.q_mvar = qMvar;
    bus.vm_pu = vm;
    bus.va_deg = va;
    bus.in_service = double(parse_flag(cell_of(cells, col, 'in_service'), lineNo, true));
    bus.x = optional_float(cells, col, 'x', lineNo);
    bus.y = optional_float(cells, col, 'y', lineNo);
end

function branch = parse_branch(cells, col, name, kind, lineNo, ordinal)
    fromBus = strtrim(cell_of(cells, col, 'from_bus'));
    toBus = strtrim(cell_of(cells, col, 'to_bus'));
    if isempty(fromBus) || isempty(toBus)
        error('grid_to_graph_export:BadInput', ...
            'row %d: from_bus and to_bus are required', lineNo);
    end
    if isempty(strtrim(name))
        branchId = sprintf('branch_%d', ordinal);
    else
        branchId = strtrim(name);
    end
    lengthKm = optional_float(cells, col, 'length_km', lineNo);
    rate = optional_float(cells, col, 'rate_mva', lineNo);
    if ~isnan(lengthKm) && lengthKm < 0
        error('grid_to_graph_export:BadInput', 'row %d: length_km cannot be negative', lineNo);
    end
    if ~isnan(rate) && rate < 0
        error('grid_to_graph_export:BadInput', 'row %d: rate_mva cannot be negative', lineNo);
    end
    branch = branch_in_template();
    branch.branch_id = branchId;
    branch.element = kind;
    branch.from_bus = fromBus;
    branch.to_bus = toBus;
    branch.r_ohm = optional_float(cells, col, 'r_ohm', lineNo);
    branch.x_ohm = optional_float(cells, col, 'x_ohm', lineNo);
    branch.b_siemens = optional_float(cells, col, 'b_siemens', lineNo);
    branch.g_siemens = optional_float(cells, col, 'g_siemens', lineNo);
    branch.r_pu = optional_float(cells, col, 'r_pu', lineNo);
    branch.x_pu = optional_float(cells, col, 'x_pu', lineNo);
    branch.b_pu = optional_float(cells, col, 'b_pu', lineNo);
    branch.g_pu = optional_float(cells, col, 'g_pu', lineNo);
    branch.tap = optional_float(cells, col, 'tap', lineNo);
    branch.shift_deg = optional_float(cells, col, 'shift_deg', lineNo);
    branch.rate_mva = rate;
    branch.length_km = lengthKm;
    branch.in_service = double(parse_flag(cell_of(cells, col, 'in_service'), lineNo, true));
end

function shunt = parse_shunt(cells, col, name, lineNo, ordinal)
    busId = strtrim(cell_of(cells, col, 'bus_id'));
    if isempty(busId)
        error('grid_to_graph_export:BadInput', 'row %d: shunt bus_id is required', lineNo);
    end
    if isempty(strtrim(name))
        shuntId = sprintf('shunt_%d', ordinal);
    else
        shuntId = strtrim(name);
    end
    shunt = shunt_in_template();
    shunt.shunt_id = shuntId;
    shunt.bus_id = busId;
    shunt.g_siemens = optional_float(cells, col, 'g_siemens', lineNo);
    shunt.b_siemens = optional_float(cells, col, 'b_siemens', lineNo);
    shunt.g_pu = optional_float(cells, col, 'g_pu', lineNo);
    shunt.b_pu = optional_float(cells, col, 'b_pu', lineNo);
    shunt.in_service = double(parse_flag(cell_of(cells, col, 'in_service'), lineNo, true));
end

function write_bundle(directory, buses, branches, shunts, edges, adjacency, ybus)
    ensure_dir(directory);
    ids = {buses.bus_id};
    write_table(fullfile(directory, 'nodes.csv'), node_columns(), node_rows(buses));
    write_table(fullfile(directory, 'branches.csv'), branch_columns(), branch_rows(branches));
    write_table(fullfile(directory, 'edges.csv'), edge_columns(), edge_rows(edges));
    write_table(fullfile(directory, 'shunts.csv'), shunt_columns(), shunt_rows(shunts));
    write_square(fullfile(directory, 'adjacency.csv'), ids, adjacency, true);
    write_square(fullfile(directory, 'ybus_g.csv'), ids, real(ybus), false);
    write_square(fullfile(directory, 'ybus_b.csv'), ids, imag(ybus), false);
end

function fig = render_figure(buses, branches, ybus, netName, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 80 1020 440]);
    try
        subplot(1, 2, 1);
        draw_graph(gca, buses, branches);
        subplot(1, 2, 2);
        draw_susceptance(gca, buses, ybus);
        titleText = sprintf('%s: graph and Ybus susceptance', netName);
        if exist('sgtitle', 'file') == 2 || exist('sgtitle', 'builtin') == 5
            sgtitle(titleText);
        else
            annotation(fig, 'textbox', [0.15 0.93 0.7 0.06], 'String', titleText, ...
                'EdgeColor', 'none', 'HorizontalAlignment', 'center', ...
                'FontSize', 12, 'FitBoxToText', 'off');
        end
        if ~isempty(outputPng)
            ensure_dir(fileparts(outputPng));
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
    catch exc
        if isgraphics(fig)
            close(fig);
        end
        rethrow(exc);
    end
end

function draw_graph(ax, buses, branches)
    coords = layout_buses(buses);
    lineColor = [31, 78, 121] / 255;
    trafoColor = [192, 57, 43] / 255;
    openColor = [149, 165, 166] / 255;
    sawLine = false;
    sawTrafo = false;
    sawOpen = false;
    nIn = count_in_service(branches);
    hold(ax, 'on');
    for k = 1:numel(branches)
        if isnan(branches(k).from_index) || isnan(branches(k).to_index)
            continue
        end
        p0 = coords(branches(k).from_index + 1, :);
        p1 = coords(branches(k).to_index + 1, :);
        if ~branches(k).in_service
            plot(ax, [p0(1) p1(1)], [p0(2) p1(2)], '--', 'Color', openColor, 'LineWidth', 1.2);
            sawOpen = true;
        elseif strcmp(branches(k).element, 'trafo') || abs(branches(k).tap - 1) > 1e-9
            plot(ax, [p0(1) p1(1)], [p0(2) p1(2)], '-', 'Color', trafoColor, 'LineWidth', 2);
            sawTrafo = true;
        else
            plot(ax, [p0(1) p1(1)], [p0(2) p1(2)], '-', 'Color', lineColor, 'LineWidth', 1.6);
            sawLine = true;
        end
        if nIn <= 12 && branches(k).in_service
            text(ax, (p0(1) + p1(1)) / 2, (p0(2) + p1(2)) / 2, branches(k).branch_id, ...
                'FontSize', 8, 'Color', [0.2 0.2 0.2]);
        end
    end
    for i = 1:numel(buses)
        marker = 'o';
        if strcmp(buses(i).bus_type, 'slack')
            marker = 's';
        elseif strcmp(buses(i).bus_type, 'pv')
            marker = 'd';
        end
        plot(ax, coords(i, 1), coords(i, 2), marker, ...
            'MarkerSize', 9, 'MarkerFaceColor', [0.957 0.945 0.918], ...
            'MarkerEdgeColor', lineColor, 'LineWidth', 1.2);
        text(ax, coords(i, 1), coords(i, 2), ['  ' buses(i).bus_id], 'FontSize', 9);
    end
    handles = {};
    labels = {};
    if sawLine
        handles{end + 1} = plot(ax, nan, nan, '-', 'Color', lineColor, 'LineWidth', 1.6); %#ok<AGROW>
        labels{end + 1} = 'line'; %#ok<AGROW>
    end
    if sawTrafo
        handles{end + 1} = plot(ax, nan, nan, '-', 'Color', trafoColor, 'LineWidth', 2); %#ok<AGROW>
        labels{end + 1} = 'transformer'; %#ok<AGROW>
    end
    if sawOpen
        handles{end + 1} = plot(ax, nan, nan, '--', 'Color', openColor, 'LineWidth', 1.2); %#ok<AGROW>
        labels{end + 1} = 'open'; %#ok<AGROW>
    end
    if ~isempty(handles)
        legend(ax, [handles{:}], labels, 'Box', 'off', 'Location', 'best');
    end
    title(ax, 'Bus graph');
    axis(ax, 'equal');
    grid(ax, 'on');
    hold(ax, 'off');
end

function draw_susceptance(ax, buses, ybus)
    data = imag(ybus);
    limit = max(abs(data(:)));
    if isempty(limit) || limit == 0
        limit = 1;
    end
    imagesc(ax, data);
    set(ax, 'YDir', 'reverse');
    colormap(ax, diverging_map());
    set(ax, 'CLim', [-limit, limit]);
    ids = {buses.bus_id};
    nBus = numel(ids);
    set(ax, 'XTick', 1:nBus, 'YTick', 1:nBus, ...
        'XTickLabel', ids, 'YTickLabel', ids, ...
        'XTickLabelRotation', 45, 'FontSize', 8);
    title(ax, 'B = imag(Ybus) (pu)');
    if nBus <= 8
        for i = 1:nBus
            for j = 1:nBus
                text(ax, j, i, sprintf('%.2f', data(i, j)), ...
                    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
                    'FontSize', 7, 'Color', [0.1 0.1 0.1]);
            end
        end
    end
    colorbar(ax);
end

function coords = layout_buses(buses)
    nBus = numel(buses);
    coords = zeros(nBus, 2);
    missing = false;
    for i = 1:nBus
        if isnan(buses(i).x) || isnan(buses(i).y)
            missing = true;
            break
        end
    end
    if missing
        for i = 1:nBus
            angle = 2 * pi * (i - 1) / nBus;
            coords(i, :) = [cos(angle), sin(angle)];
        end
    else
        for i = 1:nBus
            coords(i, :) = [buses(i).x, buses(i).y];
        end
    end
end

function cmap = diverging_map()
    n = 128;
    left = [linspace(0.23, 0.97, n)', linspace(0.30, 0.97, n)', linspace(0.75, 0.97, n)'];
    right = [linspace(0.97, 0.71, n)', linspace(0.97, 0.16, n)', linspace(0.97, 0.16, n)'];
    cmap = [left; right];
end

function write_table(path, header, rows)
    folder = fileparts(path);
    ensure_dir(folder);
    fid = fopen(path, 'w', 'n', 'UTF-8');
    if fid < 0
        error('grid_to_graph_export:BadInput', 'cannot write %s', path);
    end
    cleaner = onCleanup(@() fclose(fid));
    fprintf(fid, '%s\n', strjoin(escape_cells(header), ','));
    for r = 1:numel(rows)
        fprintf(fid, '%s\n', strjoin(escape_cells(rows{r}), ','));
    end
    clear cleaner
end

function write_square(path, ids, matrix, integer)
    nBus = numel(ids);
    header = [{ 'bus_id' }, ids];
    rows = cell(1, nBus);
    for i = 1:nBus
        values = cell(1, nBus);
        for j = 1:nBus
            if integer
                values{j} = sprintf('%d', matrix(i, j));
            else
                values{j} = sprintf('%.10f', matrix(i, j));
            end
        end
        rows{i} = [{ ids{i} }, values];
    end
    write_table(path, header, rows);
end

function rows = node_rows(buses)
    rows = cell(1, numel(buses));
    for i = 1:numel(buses)
        bus = buses(i);
        rows{i} = { ...
            sprintf('%d', bus.bus_index), bus.bus_id, bus.bus_name, bus.bus_type, ...
            sprintf('%d', bus.bus_type_code), csv_num(bus.vn_kv), csv_num(bus.z_base_ohm), ...
            csv_num(bus.y_base_s), csv_num(bus.p_mw), csv_num(bus.q_mvar), ...
            csv_num(bus.vm_pu), csv_num(bus.va_deg), sprintf('%d', bus.p_known), ...
            sprintf('%d', bus.q_known), sprintf('%d', bus.v_known), ...
            sprintf('%d', bus.theta_known), sprintf('%d', bus.degree), ...
            sprintf('%d', bus.in_service), csv_num(bus.x), csv_num(bus.y), bus.members};
    end
end

function rows = branch_rows(branches)
    rows = cell(1, numel(branches));
    for i = 1:numel(branches)
        item = branches(i);
        rows{i} = { ...
            sprintf('%d', item.branch_index), item.branch_id, item.element, ...
            item.from_bus, item.to_bus, csv_index(item.from_index), csv_index(item.to_index), ...
            csv_num(item.r_ohm), csv_num(item.x_ohm), csv_num(item.b_siemens), ...
            csv_num(item.g_siemens), csv_num(item.r_pu), csv_num(item.x_pu), ...
            csv_num(item.b_pu), csv_num(item.g_pu), csv_num(item.g_series), ...
            csv_num(item.b_series), csv_num(item.tap), csv_num(item.shift_deg), ...
            csv_num(item.rate_mva), csv_num(item.length_km), sprintf('%d', item.in_service)};
    end
end

function rows = edge_rows(edges)
    rows = cell(1, numel(edges));
    for i = 1:numel(edges)
        item = edges(i);
        rows{i} = { ...
            sprintf('%d', item.edge_index), item.branch_id, item.element, item.orientation, ...
            item.from_bus, item.to_bus, sprintf('%d', item.from_index), sprintf('%d', item.to_index), ...
            csv_num(item.r_pu), csv_num(item.x_pu), csv_num(item.b_pu), csv_num(item.g_pu), ...
            csv_num(item.g_series), csv_num(item.b_series), csv_num(item.tap), ...
            csv_num(item.shift_deg), csv_num(item.rate_mva), csv_num(item.length_km), ...
            csv_num(item.y_self_g), csv_num(item.y_self_b), ...
            csv_num(item.y_mutual_g), csv_num(item.y_mutual_b)};
    end
end

function rows = shunt_rows(shunts)
    rows = cell(1, numel(shunts));
    for i = 1:numel(shunts)
        item = shunts(i);
        rows{i} = { ...
            sprintf('%d', item.shunt_index), item.shunt_id, item.bus_id, ...
            csv_index(item.bus_index), csv_num(item.g_siemens), csv_num(item.b_siemens), ...
            csv_num(item.g_pu), csv_num(item.b_pu), sprintf('%d', item.in_service)};
    end
end

function header = node_columns()
    header = { ...
        'bus_index', 'bus_id', 'bus_name', 'bus_type', 'bus_type_code', 'vn_kv', ...
        'z_base_ohm', 'y_base_s', 'p_mw', 'q_mvar', 'vm_pu', 'va_deg', ...
        'p_known', 'q_known', 'v_known', 'theta_known', 'degree', 'in_service', ...
        'x', 'y', 'members'};
end

function header = branch_columns()
    header = { ...
        'branch_index', 'branch_id', 'element', 'from_bus', 'to_bus', 'from_index', ...
        'to_index', 'r_ohm', 'x_ohm', 'b_siemens', 'g_siemens', 'r_pu', 'x_pu', ...
        'b_pu', 'g_pu', 'g_series', 'b_series', 'tap', 'shift_deg', 'rate_mva', ...
        'length_km', 'in_service'};
end

function header = edge_columns()
    header = { ...
        'edge_index', 'branch_id', 'element', 'orientation', 'from_bus', 'to_bus', ...
        'from_index', 'to_index', 'r_pu', 'x_pu', 'b_pu', 'g_pu', 'g_series', ...
        'b_series', 'tap', 'shift_deg', 'rate_mva', 'length_km', ...
        'y_self_g', 'y_self_b', 'y_mutual_g', 'y_mutual_b'};
end

function header = shunt_columns()
    header = { ...
        'shunt_index', 'shunt_id', 'bus_id', 'bus_index', 'g_siemens', 'b_siemens', ...
        'g_pu', 'b_pu', 'in_service'};
end

function s = bus_in_template()
    s = struct('bus_id', '', 'bus_name', '', 'bus_type', '', 'vn_kv', NaN, ...
        'p_mw', NaN, 'q_mvar', NaN, 'vm_pu', NaN, 'va_deg', NaN, ...
        'in_service', 1, 'x', NaN, 'y', NaN);
end

function s = branch_in_template()
    s = struct('branch_id', '', 'element', 'line', 'from_bus', '', 'to_bus', '', ...
        'r_ohm', NaN, 'x_ohm', NaN, 'b_siemens', NaN, 'g_siemens', NaN, ...
        'r_pu', NaN, 'x_pu', NaN, 'b_pu', NaN, 'g_pu', NaN, ...
        'tap', NaN, 'shift_deg', NaN, 'rate_mva', NaN, 'length_km', NaN, 'in_service', 1);
end

function s = shunt_in_template()
    s = struct('shunt_id', '', 'bus_id', '', 'g_siemens', NaN, 'b_siemens', NaN, ...
        'g_pu', NaN, 'b_pu', NaN, 'in_service', 1);
end

function s = bus_out_template()
    s = struct('bus_index', 0, 'bus_id', '', 'bus_name', '', 'bus_type', '', ...
        'bus_type_code', 0, 'vn_kv', NaN, 'z_base_ohm', NaN, 'y_base_s', NaN, ...
        'p_mw', NaN, 'q_mvar', NaN, 'vm_pu', NaN, 'va_deg', NaN, ...
        'p_known', 0, 'q_known', 0, 'v_known', 0, 'theta_known', 0, ...
        'degree', 0, 'in_service', 1, 'x', NaN, 'y', NaN, 'members', '');
end

function s = branch_out_template()
    s = struct('branch_index', 0, 'branch_id', '', 'element', 'line', ...
        'from_bus', '', 'to_bus', '', 'from_index', NaN, 'to_index', NaN, ...
        'r_ohm', NaN, 'x_ohm', NaN, 'b_siemens', NaN, 'g_siemens', NaN, ...
        'r_pu', NaN, 'x_pu', NaN, 'b_pu', NaN, 'g_pu', NaN, ...
        'g_series', 0, 'b_series', 0, 'tap', 1, 'shift_deg', 0, ...
        'rate_mva', NaN, 'length_km', NaN, 'in_service', 0, ...
        'yff', 0, 'yft', 0, 'ytf', 0, 'ytt', 0);
end

function s = shunt_out_template()
    s = struct('shunt_index', 0, 'shunt_id', '', 'bus_id', '', 'bus_index', NaN, ...
        'g_siemens', 0, 'b_siemens', 0, 'g_pu', 0, 'b_pu', 0, 'in_service', 0);
end

function s = edge_template()
    s = struct('edge_index', 0, 'branch_id', '', 'element', 'line', ...
        'orientation', '', 'from_bus', '', 'to_bus', '', ...
        'from_index', 0, 'to_index', 0, 'r_pu', 0, 'x_pu', 0, 'b_pu', 0, 'g_pu', 0, ...
        'g_series', 0, 'b_series', 0, 'tap', 1, 'shift_deg', 0, ...
        'rate_mva', NaN, 'length_km', NaN, ...
        'y_self_g', 0, 'y_self_b', 0, 'y_mutual_g', 0, 'y_mutual_b', 0);
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
    if ~(ischar(value) || (isstring(value) && isscalar(value)))
        tf = false;
        return
    end
    keys = {'s_base_mva', 'engine', 'network', 'self_loop', 'csv_path', ...
        'output_dir', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(to_char(value)), keys));
end

function assert_pairs(args)
    if mod(numel(args), 2) ~= 0
        error('grid_to_graph_export:BadInput', 'name-value arguments must come in pairs');
    end
end

function name = normalize_engine(value)
    name = lower(strtrim(to_char(value)));
    if ~any(strcmp(name, {'builtin', 'pandapower', 'auto'}))
        error('grid_to_graph_export:BadInput', 'engine must be builtin, pandapower, or auto');
    end
end

function path = resolve_csv(source, csvOpt)
    named = strtrim(to_char(csvOpt));
    if ~isempty(source) && ~isempty(named)
        error('grid_to_graph_export:BadInput', ...
            'pass the CSV either as the first argument or as csv_path');
    end
    if ~isempty(source)
        path = to_char(source);
        return
    end
    if ~isempty(named)
        path = named;
        return
    end
    path = default_csv();
end

function path = default_csv()
    here = fileparts(mfilename('fullpath'));
    path = fullfile(fileparts(here), 'examples', 'data', 'synthetic_grid.csv');
end

function tf = same_file(a, b)
    tf = strcmp(canonical_path(a), canonical_path(b));
end

function path = canonical_path(path)
    path = char(path);
    try
        file = java.io.File(path);
        got = char(file.getCanonicalPath());
        if ~isempty(got)
            path = got;
            return
        end
    catch
    end
    if ~is_absolute_path(path)
        path = fullfile(pwd, path);
    end
    path = collapse_path(path);
end

function tf = is_absolute_path(path)
    tf = ~isempty(path) && (path(1) == '/' || path(1) == '\' || ...
        ~isempty(regexp(path, '^[A-Za-z]:', 'once')));
end

function path = collapse_path(path)
    slash = '/';
    if any(path == '\') && all(path ~= '/')
        slash = '\';
    end
    text = strrep(path, '\', '/');
    absolute = ~isempty(text) && text(1) == '/';
    pieces = strsplit(text, '/');
    keep = {};
    for i = 1:numel(pieces)
        part = pieces{i};
        if isempty(part) || strcmp(part, '.')
            continue
        end
        if strcmp(part, '..')
            if ~isempty(keep)
                keep(end) = [];
            end
            continue
        end
        keep{end + 1} = part; %#ok<AGROW>
    end
    path = strjoin(keep, '/');
    if absolute
        path = ['/' path];
    end
    if slash == '\'
        path = strrep(path, '/', '\');
    end
end

function [zBase, yBase] = bases(vnKv, sBase)
    zBase = (vnKv * vnKv) / sBase;
    yBase = sBase / (vnKv * vnKv);
end

function value = positive_number(name, value)
    if ~(isnumeric(value) && isscalar(value) && isfinite(value) && value > 0)
        error('grid_to_graph_export:BadInput', '%s must be positive', name);
    end
    value = double(value);
end

function tf = coerce_bool(value, name)
    if islogical(value) && isscalar(value)
        tf = value;
        return
    end
    if isnumeric(value) && isscalar(value) && (value == 0 || value == 1)
        tf = logical(value);
        return
    end
    if ischar(value) || (isstring(value) && isscalar(value))
        token = lower(strtrim(to_char(value)));
        if any(strcmp(token, {'1', 'true', 'yes'}))
            tf = true;
            return
        end
        if any(strcmp(token, {'0', 'false', 'no'}))
            tf = false;
            return
        end
    end
    error('grid_to_graph_export:BadInput', '%s must be true or false', name);
end

function bus = must_bus(buses, busId, label)
    for i = 1:numel(buses)
        if strcmp(buses(i).bus_id, busId)
            bus = buses(i);
            return
        end
    end
    error('grid_to_graph_export:BadInput', ...
        '%s references unknown bus %s', label, busId);
end

function idx = map_index(index, busId)
    if isKey(index, busId)
        idx = index(busId) - 1;
    else
        idx = NaN;
    end
end

function assert_unique(ids, label)
    for i = 1:numel(ids)
        for j = i + 1:numel(ids)
            if strcmp(ids{i}, ids{j})
                error('grid_to_graph_export:BadInput', 'duplicate %s %s', label, ids{i});
            end
        end
    end
end

function n = count_in_service(items)
    if isempty(items)
        n = 0;
        return
    end
    n = sum([items.in_service] == 1);
end

function [pKnown, qKnown, vKnown, thetaKnown] = masks_of(busType)
    if strcmp(busType, 'slack')
        pKnown = 0; qKnown = 0; vKnown = 1; thetaKnown = 1;
    elseif strcmp(busType, 'pv')
        pKnown = 1; qKnown = 0; vKnown = 1; thetaKnown = 0;
    else
        pKnown = 1; qKnown = 1; vKnown = 0; thetaKnown = 0;
    end
end

function code = type_code(busType)
    if strcmp(busType, 'slack')
        code = 3;
    elseif strcmp(busType, 'pv')
        code = 2;
    else
        code = 1;
    end
end

function text = known_text(bus)
    tokens = {};
    if bus.p_known
        tokens{end + 1} = 'P'; %#ok<AGROW>
    end
    if bus.q_known
        tokens{end + 1} = 'Q'; %#ok<AGROW>
    end
    if bus.v_known
        tokens{end + 1} = 'V'; %#ok<AGROW>
    end
    if bus.theta_known
        tokens{end + 1} = 'theta'; %#ok<AGROW>
    end
    if isempty(tokens)
        text = '';
    else
        text = strjoin(tokens, ',');
    end
end

function text = fmt_jb(value)
    realPart = real(value);
    imagPart = imag(value);
    if abs(realPart) < 5e-13
        realPart = 0;
    end
    if abs(imagPart) < 5e-13
        imagPart = 0;
    end
    if imagPart < 0
        signChar = '-';
    else
        signChar = '+';
    end
    text = sprintf('%.4f%sj%.4f', realPart, signChar, abs(imagPart));
end

function text = fmt_opt(value, width)
    if isnan(value)
        text = sprintf('%*s', width, '-');
    else
        text = sprintf('%*.4f', width, value);
    end
end

function text = csv_num(value)
    if isempty(value) || ~isscalar(value) || isnan(value)
        text = '';
    else
        text = sprintf('%.10f', double(value));
    end
end

function text = csv_index(value)
    if isempty(value) || ~isscalar(value) || isnan(value)
        text = '';
    else
        text = sprintf('%d', value);
    end
end

function value = zero_if_nan(value)
    if isnan(value)
        value = 0;
    end
end

function cells = escape_cells(cells)
    for k = 1:numel(cells)
        cells{k} = csv_escape(cells{k});
    end
end

function text = csv_escape(value)
    text = char(value);
    if text_has(text, {',', '"', newline, char(13)})
        text = ['"' strrep(text, '"', '""') '"'];
    end
end

function cells = split_csv_line(line)
    cells = {};
    buf = '';
    inQuote = false;
    i = 1;
    n = length(line);
    while i <= n
        ch = line(i);
        if inQuote
            if ch == '"'
                if i < n && line(i + 1) == '"'
                    buf = [buf '"']; %#ok<AGROW>
                    i = i + 1;
                else
                    inQuote = false;
                end
            else
                buf = [buf ch]; %#ok<AGROW>
            end
        elseif ch == '"'
            inQuote = true;
        elseif ch == ','
            cells{end + 1} = buf; %#ok<AGROW>
            buf = '';
        else
            buf = [buf ch]; %#ok<AGROW>
        end
        i = i + 1;
    end
    cells{end + 1} = buf; %#ok<AGROW>
end

function value = cell_of(cells, col, key)
    if ~isfield(col, key) || col.(key) > numel(cells)
        value = '';
        return
    end
    value = strtrim(cells{col.(key)});
end

function value = optional_float(cells, col, key, lineNo)
    text = cell_of(cells, col, key);
    if isempty(strtrim(text))
        value = NaN;
        return
    end
    value = str2double(text);
    if ~isfinite(value)
        error('grid_to_graph_export:BadInput', 'row %d: %s is not a number', lineNo, key);
    end
end

function value = require_float(cells, col, key, lineNo)
    value = optional_float(cells, col, key, lineNo);
    if isnan(value)
        error('grid_to_graph_export:BadInput', 'row %d: %s is required', lineNo, key);
    end
end

function tf = parse_flag(text, lineNo, default)
    token = lower(strtrim(text));
    if isempty(token)
        tf = default;
        return
    end
    if any(strcmp(token, {'1', 'true', 'yes', 'y'}))
        tf = true;
        return
    end
    if any(strcmp(token, {'0', 'false', 'no', 'n'}))
        tf = false;
        return
    end
    error('grid_to_graph_export:BadInput', 'row %d: in_service must be 0 or 1', lineNo);
end

function key = norm_key(text)
    text = lower(strtrim(text));
    key = regexprep(text, '[^a-z0-9_]', '');
end

function kind = kind_alias(text)
    switch text
        case {'bus', 'node'}
            kind = 'bus';
        case {'line', 'branch'}
            kind = 'line';
        case {'trafo', 'transformer', 'xfmr'}
            kind = 'trafo';
        case {'shunt', 'capacitor', 'reactor'}
            kind = 'shunt';
        otherwise
            kind = '';
    end
end

function busType = type_alias(text)
    switch text
        case {'pq', 'load'}
            busType = 'pq';
        case {'pv', 'generator', 'gen'}
            busType = 'pv';
        case {'slack', 'ref', 'reference', 'swing', 'vtheta'}
            busType = 'slack';
        otherwise
            busType = '';
    end
end

function line = strip_line(line)
    if ~isempty(line) && double(line(1)) == 65279
        line = line(2:end);
    end
    line = strrep(line, char(13), '');
end

function ensure_dir(folder)
    if isempty(folder) || exist(folder, 'dir') == 7
        return
    end
    parent = fileparts(folder);
    if ~isempty(parent)
        ensure_dir(parent);
    end
    mkdir(folder);
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    if isstring(value)
        ok = isscalar(value);
        return
    end
    ok = false;
end

function tf = text_has(text, pattern)
    text = char(text);
    if ischar(pattern)
        pattern = {pattern};
    end
    tf = false;
    for i = 1:numel(pattern)
        piece = char(pattern{i});
        if ~isempty(piece) && ~isempty(strfind(text, piece)) %#ok<STREMP>
            tf = true;
            return
        end
    end
end

function text = to_char(value)
    if isstring(value)
        text = char(value);
    elseif ischar(value)
        text = value;
    else
        text = '';
    end
end
