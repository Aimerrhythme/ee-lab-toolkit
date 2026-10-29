function result = motor_torque_speed(source, varargin)
%MOTOR_TORQUE_SPEED Torque-speed curves for an induction motor and a DC motor.
%   RESULT = MOTOR_TORQUE_SPEED()
%   RESULT = MOTOR_TORQUE_SPEED('cases.csv', 'output_png', 'curves.png', 'show', false)
%   RESULT = MOTOR_TORQUE_SPEED('motor', 'dc_separate', 'v', 220, 'k_phi', 1.5)
%
%   Same curves as python/motor_torque_speed.py, in base MATLAB (no toolbox).
%   poles is the number of poles (4 for a 4-pole machine), not pole pairs.
%
%   Induction, per phase, parameters referred to the stator:
%       n_sync = 120 * f / poles
%       omega_sync = 2 * pi * n_sync / 60
%       Zm = Rc || j Xm          (Rc open when core loss is neglected)
%       Z2 = R2/s + j X2         (rotor open at s = 0)
%       P_ag = 3 * |I2|^2 * R2 / s
%       T = P_ag / omega_sync
%       P_mech = (1 - s) * P_ag
%       s_bd = R2 / sqrt(Rth^2 + (Xth + X2)^2)
%       T_bd = 3/(2*omega_sync) * |Vth|^2 / (Rth + sqrt(Rth^2 + (Xth + X2)^2))
%   T_bd does not depend on R2. Developed torque scales with Vph^2.
%
%   Separately excited: omega = V/K_phi - (Ra/K_phi^2)*T
%   Shunt: K_phi = k_f * V / Rf, so no-load speed is Rf/k_f
%   Series: T = k_f * I^2, omega = V/sqrt(k_f*T) - (Ra+Rs)/k_f
%   K_phi is in V*s/rad (same as N*m/A). No brush drop, no saturation.
%
%   A CSV with several rows and no name returns every row. Pass name to
%   select one row. Blank CSV cells keep the matching argument.
%
%   Name-value keys match Python: name, motor, v, f, poles, connection,
%   r1, x1, r2, x2, xm, rc, p_rated, s_rated, t_rated, ra, rf, rs, k_phi,
%   k_f, i_min, i_max, s_min, s_max, n_points, csv_path, output_csv,
%   output_png, show.

    if nargin < 1
        source = [];
    end
    [source, rest] = split_source(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'motor_torque_speed';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('name', '', @is_text_scalar);
    parser.addParameter('motor', 'induction', @is_text_scalar);
    parser.addParameter('v', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('f', 50, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('poles', 4, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('connection', 'y', @is_text_scalar);
    parser.addParameter('r1', 0.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('x1', 1.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('r2', 0.4, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('x2', 1.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('xm', 40, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('rc', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('p_rated', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('s_rated', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('t_rated', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('ra', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('rf', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('rs', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('k_phi', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('k_f', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('i_min', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('i_max', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('s_min', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('s_max', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('n_points', 401, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    specs = resolve_specs(parser.Results, source, rest);

    nCases = numel(specs);
    built = cell(1, nCases);
    for index = 1:nCases
        built{index} = build_case(specs{index});
    end
    cases = [built{:}];
    summary = format_summary(cases);

    outputCsv = as_char(parser.Results.output_csv);
    outputPng = as_char(parser.Results.output_png);
    showFig = as_bool('show', parser.Results.show);
    if ~isempty(outputCsv)
        write_summary(outputCsv, cases);
    end
    if ~isempty(outputPng) || showFig
        fig = render_figure(cases, outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.cases = cases;
    result.summary = summary;
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = fig;
end

function [source, rest] = split_source(source, args)
    rest = args;
    if is_parameter_name(source)
        if isempty(args)
            rest = {source};
        else
            rest = [{source}, args];
        end
        source = [];
    end
end

function specs = resolve_specs(opt, source, rest)
    csvPath = as_char(opt.csv_path);
    if isnumeric(source) && ~isempty(source)
        error('motor_torque_speed:BadOption', ...
            'pass parameters by name; the first argument is a CSV path');
    end
    if is_text_scalar(source) && ~isempty(as_char(source))
        text = as_char(source);
        if is_parameter_name(text)
            error('motor_torque_speed:BadOption', ...
                '''%s'' is a parameter name. Pass the CSV path as the first argument or as csv_path=', ...
                text);
        end
        if was_passed(rest, 'csv_path')
            error('motor_torque_speed:BadOption', ...
                'pass a CSV path once, either positionally or as csv_path=');
        end
        csvPath = text;
    elseif ~isempty(source) && ~(is_text_scalar(source) && isempty(as_char(source)))
        error('motor_torque_speed:BadOption', 'source must be a CSV path or omitted');
    end
    if isempty(csvPath)
        specs = {opt};
        return
    end
    rows = read_case_csv(csvPath);
    picked = select_rows(rows, as_char(opt.name));
    specs = cell(1, numel(picked));
    for index = 1:numel(picked)
        specs{index} = merge_row(opt, picked{index});
    end
end

function rows = read_case_csv(csvPath)
    if exist(csvPath, 'file') ~= 2
        error('motor_torque_speed:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if numel(raw) >= 3 && raw(1) == char(239) && raw(2) == char(187) && raw(3) == char(191)
        raw = raw(4:end);
    end
    raw = strrep(raw, sprintf('\r\n'), sprintf('\n'));
    raw = strrep(raw, sprintf('\r'), sprintf('\n'));
    lines = strsplit(raw, sprintf('\n'));
    kept = {};
    for index = 1:numel(lines)
        if ~isempty(strtrim(lines{index}))
            kept{end + 1} = lines{index}; %#ok<AGROW>
        end
    end
    if numel(kept) < 2
        error('motor_torque_speed:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
    commaCount = numel(strfind(kept{1}, ','));
    semiCount = numel(strfind(kept{1}, ';'));
    if semiCount > commaCount
        delim = ';';
    else
        delim = ',';
    end
    headers = split_line(kept{1}, delim);
    for index = 1:numel(headers)
        headers{index} = strtrim(headers{index});
        if isempty(headers{index})
            error('motor_torque_speed:BadOption', 'CSV header has an empty column name');
        end
    end
    rows = {};
    for index = 2:numel(kept)
        cells = split_line(kept{index}, delim);
        while numel(cells) < numel(headers)
            cells{end + 1} = ''; %#ok<AGROW>
        end
        item = struct();
        blank = true;
        for col = 1:numel(headers)
            value = strtrim(cells{col});
            item.(headers{col}) = value;
            if ~isempty(value)
                blank = false;
            end
        end
        if ~blank
            rows{end + 1} = item; %#ok<AGROW>
        end
    end
    if isempty(rows)
        error('motor_torque_speed:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function cells = split_line(line, delim)
    cells = {};
    bucket = '';
    for index = 1:numel(line)
        if line(index) == delim
            cells{end + 1} = bucket; %#ok<AGROW>
            bucket = '';
        else
            bucket = [bucket, line(index)]; %#ok<AGROW>
        end
    end
    cells{end + 1} = bucket; %#ok<AGROW>
end

function picked = select_rows(rows, name)
    if isempty(name)
        picked = rows;
        return
    end
    picked = {};
    for index = 1:numel(rows)
        rowName = char(as_text(struct_lookup(rows{index}, {'name'})));
        if strcmp(rowName, name)
            picked{end + 1} = rows{index}; %#ok<AGROW>
        end
    end
    if isempty(picked)
        error('motor_torque_speed:BadOption', 'name ''%s'' was not found in the CSV', name);
    end
    if numel(picked) > 1
        error('motor_torque_speed:BadOption', ...
            'name ''%s'' appears more than once in the CSV', name);
    end
end

function spec = merge_row(opt, row)
    spec = opt;
    pairs = { ...
        'name', {'name'}; ...
        'motor', {'motor', 'type', 'kind'}; ...
        'v', {'v', 'vline', 'vt', 'voltage'}; ...
        'f', {'f', 'frequency', 'freq'}; ...
        'poles', {'poles'}; ...
        'connection', {'connection', 'conn'}; ...
        'r1', {'r1'}; ...
        'x1', {'x1'}; ...
        'r2', {'r2'}; ...
        'x2', {'x2'}; ...
        'xm', {'xm'}; ...
        'rc', {'rc'}; ...
        'p_rated', {'prated'}; ...
        's_rated', {'srated'}; ...
        't_rated', {'trated'}; ...
        'ra', {'ra'}; ...
        'rf', {'rf'}; ...
        'rs', {'rs'}; ...
        'k_phi', {'kphi'}; ...
        'k_f', {'kf'}; ...
        'i_min', {'imin'}; ...
        'i_max', {'imax'}; ...
        's_min', {'smin'}; ...
        's_max', {'smax'}; ...
        'n_points', {'npoints'}};
    for index = 1:size(pairs, 1)
        value = struct_lookup(row, pairs{index, 2});
        if ~is_blank(value)
            spec.(pairs{index, 1}) = value;
        end
    end
    if is_blank(spec.name)
        spec.name = '';
    end
end

function motorCase = build_case(spec)
    motor = normalize_motor(spec.motor);
    spec.motor = motor;
    spec.name = as_char(spec.name);
    optionalKeys = {'v', 'rc', 'p_rated', 's_rated', 't_rated', 'ra', 'rf', 'rs', ...
        'k_phi', 'k_f', 'i_min', 'i_max'};
    for index = 1:numel(optionalKeys)
        key = optionalKeys{index};
        spec.(key) = optional_number(key, spec.(key));
    end
    reject_unused(motor, spec);
    if strcmp(motor, 'induction')
        motorCase = build_induction(spec);
    elseif strcmp(motor, 'dc_series')
        motorCase = build_series(spec);
    else
        motorCase = build_dc_linear(spec);
    end
end

function reject_unused(motor, spec)
    if strcmp(motor, 'induction')
        banned = {'t_rated', 'ra', 'rf', 'rs', 'k_phi', 'k_f', 'i_min', 'i_max'};
    elseif strcmp(motor, 'dc_separate')
        banned = {'s_rated', 'rc', 'rf', 'rs', 'k_f', 'i_min', 'i_max'};
    elseif strcmp(motor, 'dc_shunt')
        banned = {'s_rated', 'rc', 'rs', 'k_phi', 'i_min', 'i_max'};
    else
        banned = {'s_rated', 'rc', 'rf', 'k_phi'};
    end
    for index = 1:numel(banned)
        if ~isempty(spec.(banned{index}))
            error('motor_torque_speed:BadOption', ...
                '%s does not apply to motor ''%s''', banned{index}, motor);
        end
    end
end

function motorCase = build_induction(spec)
    vLine = positive_or_default('v', spec.v, 380);
    frequency = positive_number('f', spec.f);
    poles = positive_int('poles', spec.poles, 2, 64);
    if mod(poles, 2) ~= 0
        error('motor_torque_speed:BadOption', 'poles must be an even integer (2, 4, 6, ...)');
    end
    connection = normalize_connection(spec.connection);
    r1 = nonnegative_number('r1', spec.r1);
    x1 = nonnegative_number('x1', spec.x1);
    r2 = positive_number('r2', spec.r2);
    x2 = nonnegative_number('x2', spec.x2);
    xm = positive_number('xm', spec.xm);
    if isempty(spec.rc)
        rc = inf;
    else
        rc = spec.rc;
    end
    if ~(rc > 0)
        error('motor_torque_speed:BadOption', 'rc must be a positive finite number or inf');
    end
    sMin = finite_number('s_min', spec.s_min);
    sMax = finite_number('s_max', spec.s_max);
    check_slip_window(sMin, sMax);
    nPoints = positive_int('n_points', spec.n_points, 1, 5001);
    if nPoints == 1 && sMin ~= sMax
        error('motor_torque_speed:BadOption', 'n_points=1 requires s_min == s_max');
    end
    if isempty(spec.p_rated)
        pRated = [];
    else
        pRated = positive_number('p_rated', spec.p_rated);
    end
    if isempty(spec.s_rated)
        sRatedGiven = [];
    else
        sRatedGiven = finite_number('s_rated', spec.s_rated);
        if sRatedGiven < -2 || sRatedGiven > 3
            error('motor_torque_speed:BadOption', 's_rated must lie in [-2, 3]');
        end
    end

    if strcmp(connection, 'd')
        vPhase = vLine;
    else
        vPhase = vLine / sqrt(3);
    end
    nSync = 120 * frequency / poles;
    omegaSync = 2 * pi * nSync / 60;
    zMag = magnetizing(xm, rc);
    z1 = r1 + 1i * x1;
    vTh = vPhase * zMag / (z1 + zMag);
    zTh = z1 * zMag / (z1 + zMag);
    machine = struct();
    machine.v_phase = vPhase;
    machine.connection = connection;
    machine.r1 = r1;
    machine.x1 = x1;
    machine.r2 = r2;
    machine.x2 = x2;
    machine.xm = xm;
    machine.rc = rc;
    machine.n_sync = nSync;
    machine.omega_sync = omegaSync;
    machine.v_th = vTh;
    machine.r_th = real(zTh);
    machine.x_th = imag(zTh);

    sBd = breakdown_slip(machine);
    tBd = breakdown_torque(machine);
    startPoint = induction_point(machine, 1);
    if ~isempty(sRatedGiven)
        rated = induction_point(machine, sRatedGiven);
    elseif ~isempty(pRated)
        rated = induction_point(machine, solve_induction_slip(machine, pRated, sBd));
    else
        rated = [];
    end
    slip = insert_slip(linspace(sMin, sMax, nPoints).', sBd);
    points = repmat(startPoint, numel(slip), 1);
    for index = 1:numel(slip)
        points(index) = induction_point(machine, slip(index));
    end

    scalars = base_scalars();
    scalars.name = spec.name;
    scalars.motor = 'induction';
    scalars.connection = connection;
    scalars.v = vLine;
    scalars.f = frequency;
    scalars.poles = poles;
    scalars.r1 = r1;
    scalars.x1 = x1;
    scalars.r2 = r2;
    scalars.x2 = x2;
    scalars.xm = xm;
    scalars.rc = rc;
    scalars.n_sync_rpm = nSync;
    scalars.omega_sync_rad_s = omegaSync;
    scalars.v_phase = vPhase;
    scalars.v_th = abs(vTh);
    scalars.r_th = machine.r_th;
    scalars.x_th = machine.x_th;
    scalars.torque_start_nm = startPoint.torque_nm;
    scalars.slip_breakdown = sBd;
    scalars.speed_breakdown_rpm = (1 - sBd) * nSync;
    scalars.torque_breakdown_nm = tBd;
    scalars.p_rated_w = nan_if_empty(pRated);
    scalars.s_min = sMin;
    scalars.s_max = sMax;
    scalars.n_points = nPoints;
    motorCase = assemble_case(scalars, rated, points);
end

function motorCase = build_dc_linear(spec)
    motor = spec.motor;
    v = positive_or_default('v', spec.v, 220);
    nPoints = positive_int('n_points', spec.n_points, 2, 5001);
    if isempty(spec.p_rated)
        pRated = [];
    else
        pRated = positive_number('p_rated', spec.p_rated);
    end
    if isempty(spec.t_rated)
        tRatedGiven = [];
    else
        tRatedGiven = positive_number('t_rated', spec.t_rated);
    end
    if strcmp(motor, 'dc_shunt')
        ra = positive_or_default('ra', spec.ra, 1);
        rf = positive_or_default('rf', spec.rf, 220);
        kF = positive_or_default('k_f', spec.k_f, 1.5);
        iField = v / rf;
        kPhi = kF * iField;
        rs = NaN;
    else
        ra = positive_or_default('ra', spec.ra, 1);
        rf = NaN;
        kF = NaN;
        iField = NaN;
        kPhi = positive_or_default('k_phi', spec.k_phi, 1.5);
        rs = NaN;
    end
    iStall = v / ra;
    tStall = kPhi * iStall;
    speedNoLoad = rpm_from_omega(v / kPhi);
    if ~isempty(tRatedGiven)
        if tRatedGiven > tStall * (1 + 1e-12)
            error('motor_torque_speed:BadOption', ...
                't_rated must be positive and at most the stall torque');
        end
        tRated = min(tRatedGiven, tStall);
    elseif ~isempty(pRated)
        tRated = solve_linear_torque(v, ra, kPhi, pRated, tStall);
    else
        tRated = [];
    end
    if isempty(tRated)
        rated = [];
    else
        rated = dc_linear_point(v, ra, kPhi, iField, tRated);
    end
    torque = linspace(0, tStall, nPoints).';
    points = repmat(dc_linear_point(v, ra, kPhi, iField, 0), nPoints, 1);
    for index = 1:nPoints
        points(index) = dc_linear_point(v, ra, kPhi, iField, torque(index));
    end

    scalars = base_scalars();
    scalars.name = spec.name;
    scalars.motor = motor;
    scalars.v = v;
    scalars.ra = ra;
    scalars.rf = rf;
    scalars.rs = rs;
    scalars.k_phi = kPhi;
    scalars.k_f = kF;
    scalars.i_field_a = iField;
    scalars.speed_noload_rpm = speedNoLoad;
    scalars.torque_stall_nm = tStall;
    scalars.i_stall_a = iStall;
    scalars.p_rated_w = nan_if_empty(pRated);
    scalars.n_points = nPoints;
    motorCase = assemble_case(scalars, rated, points);
end

function motorCase = build_series(spec)
    v = positive_or_default('v', spec.v, 220);
    if isempty(spec.ra)
        ra = 0.4;
    else
        ra = nonnegative_number('ra', spec.ra);
    end
    if isempty(spec.rs)
        rs = 0.2;
    else
        rs = nonnegative_number('rs', spec.rs);
    end
    kF = positive_or_default('k_f', spec.k_f, 0.08);
    rTot = ra + rs;
    if ~(rTot > 0)
        error('motor_torque_speed:BadOption', 'ra + rs must be a positive finite number');
    end
    nPoints = positive_int('n_points', spec.n_points, 2, 5001);
    if isempty(spec.p_rated)
        pRated = [];
    else
        pRated = positive_number('p_rated', spec.p_rated);
    end
    if isempty(spec.t_rated)
        tRatedGiven = [];
    else
        tRatedGiven = positive_number('t_rated', spec.t_rated);
    end
    iStall = v / rTot;
    tStall = kF * iStall * iStall;
    iMin = positive_or_default('i_min', spec.i_min, 0.08 * iStall);
    iMax = positive_or_default('i_max', spec.i_max, 0.45 * iStall);
    if iMax <= iMin || iMax > iStall * (1 + 1e-12)
        error('motor_torque_speed:BadOption', ...
            'i_max must be greater than i_min and at most the stall current');
    end
    iMax = min(iMax, iStall);
    if ~isempty(tRatedGiven)
        if tRatedGiven > tStall * (1 + 1e-12)
            error('motor_torque_speed:BadOption', ...
                't_rated must be positive and at most the stall torque');
        end
        tRated = min(tRatedGiven, tStall);
    elseif ~isempty(pRated)
        tRated = solve_series_torque(v, rTot, kF, pRated);
    else
        tRated = [];
    end
    if isempty(tRated)
        rated = [];
    else
        rated = series_point(v, rTot, kF, tRated);
    end
    current = linspace(iMin, iMax, nPoints).';
    torque = kF * current .* current;
    points = repmat(series_point(v, rTot, kF, torque(1)), nPoints, 1);
    for index = 1:nPoints
        points(index) = series_point(v, rTot, kF, torque(index));
    end

    scalars = base_scalars();
    scalars.name = spec.name;
    scalars.motor = 'dc_series';
    scalars.v = v;
    scalars.ra = ra;
    scalars.rs = rs;
    scalars.k_f = kF;
    scalars.speed_noload_rpm = inf;
    scalars.torque_stall_nm = tStall;
    scalars.i_stall_a = iStall;
    scalars.i_min = iMin;
    scalars.i_max = iMax;
    scalars.p_rated_w = nan_if_empty(pRated);
    scalars.n_points = nPoints;
    motorCase = assemble_case(scalars, rated, points);
end

function scalars = base_scalars()
    scalars = struct();
    scalars.name = '';
    scalars.motor = '';
    scalars.connection = '';
    scalars.v = NaN;
    scalars.f = NaN;
    scalars.poles = NaN;
    scalars.r1 = NaN;
    scalars.x1 = NaN;
    scalars.r2 = NaN;
    scalars.x2 = NaN;
    scalars.xm = NaN;
    scalars.rc = NaN;
    scalars.n_sync_rpm = NaN;
    scalars.omega_sync_rad_s = NaN;
    scalars.v_phase = NaN;
    scalars.v_th = NaN;
    scalars.r_th = NaN;
    scalars.x_th = NaN;
    scalars.torque_start_nm = NaN;
    scalars.slip_breakdown = NaN;
    scalars.speed_breakdown_rpm = NaN;
    scalars.torque_breakdown_nm = NaN;
    scalars.s_rated = NaN;
    scalars.speed_rated_rpm = NaN;
    scalars.torque_rated_nm = NaN;
    scalars.i_line_rated_a = NaN;
    scalars.i2_rated_a = NaN;
    scalars.power_mech_rated_w = NaN;
    scalars.power_in_rated_w = NaN;
    scalars.pf_rated = NaN;
    scalars.efficiency_rated = NaN;
    scalars.p_rated_w = NaN;
    scalars.ra = NaN;
    scalars.rf = NaN;
    scalars.rs = NaN;
    scalars.k_phi = NaN;
    scalars.k_f = NaN;
    scalars.i_field_a = NaN;
    scalars.speed_noload_rpm = NaN;
    scalars.torque_stall_nm = NaN;
    scalars.i_stall_a = NaN;
    scalars.i_min = NaN;
    scalars.i_max = NaN;
    scalars.s_min = NaN;
    scalars.s_max = NaN;
    scalars.n_points = 0;
end

function motorCase = assemble_case(scalars, rated, points)
    motorCase = scalars;
    if isempty(rated)
        motorCase.s_rated = NaN;
        motorCase.speed_rated_rpm = NaN;
        motorCase.torque_rated_nm = NaN;
        motorCase.i_line_rated_a = NaN;
        motorCase.i2_rated_a = NaN;
        motorCase.power_mech_rated_w = NaN;
        motorCase.power_in_rated_w = NaN;
        motorCase.pf_rated = NaN;
        motorCase.efficiency_rated = NaN;
    else
        motorCase.s_rated = rated.slip;
        motorCase.speed_rated_rpm = rated.speed_rpm;
        motorCase.torque_rated_nm = rated.torque_nm;
        motorCase.i_line_rated_a = rated.i_line_a;
        motorCase.i2_rated_a = rated.i2_a;
        motorCase.power_mech_rated_w = rated.power_mech_w;
        motorCase.power_in_rated_w = rated.power_in_w;
        motorCase.pf_rated = rated.power_factor;
        motorCase.efficiency_rated = rated.efficiency;
    end
    n = numel(points);
    motorCase.n_samples = n;
    motorCase.slip = zeros(n, 1);
    motorCase.speed_rpm = zeros(n, 1);
    motorCase.speed_rad_s = zeros(n, 1);
    motorCase.torque_nm = zeros(n, 1);
    motorCase.i_line_a = zeros(n, 1);
    motorCase.i_phase_a = zeros(n, 1);
    motorCase.i2_a = zeros(n, 1);
    motorCase.power_in_w = zeros(n, 1);
    motorCase.power_mech_w = zeros(n, 1);
    motorCase.power_factor = zeros(n, 1);
    motorCase.efficiency = zeros(n, 1);
    for index = 1:n
        motorCase.slip(index) = points(index).slip;
        motorCase.speed_rpm(index) = points(index).speed_rpm;
        motorCase.speed_rad_s(index) = points(index).speed_rad_s;
        motorCase.torque_nm(index) = points(index).torque_nm;
        motorCase.i_line_a(index) = points(index).i_line_a;
        motorCase.i_phase_a(index) = points(index).i_phase_a;
        motorCase.i2_a(index) = points(index).i2_a;
        motorCase.power_in_w(index) = points(index).power_in_w;
        motorCase.power_mech_w(index) = points(index).power_mech_w;
        motorCase.power_factor(index) = points(index).power_factor;
        motorCase.efficiency(index) = points(index).efficiency;
    end
end

function value = nan_if_empty(raw)
    if isempty(raw)
        value = NaN;
    else
        value = raw;
    end
end

function zMag = magnetizing(xm, rc)
    if ~isfinite(rc)
        zMag = 1i * xm;
    else
        zMag = 1 / (1 / rc + 1 / (1i * xm));
    end
end

function point = make_point(slip, speedRpm, speedRad, torque, iLine, iPhase, i2, pIn, pMech, pf, eta)
    point = struct();
    point.slip = slip;
    point.speed_rpm = speedRpm;
    point.speed_rad_s = speedRad;
    point.torque_nm = torque;
    point.i_line_a = iLine;
    point.i_phase_a = iPhase;
    point.i2_a = i2;
    point.power_in_w = pIn;
    point.power_mech_w = pMech;
    point.power_factor = pf;
    point.efficiency = eta;
end

function point = induction_point(machine, slip)
    z1 = machine.r1 + 1i * machine.x1;
    zMag = magnetizing(machine.xm, machine.rc);
    if abs(slip) <= 1e-14
        zIn = z1 + zMag;
        i1 = machine.v_phase / zIn;
        i2 = 0;
        pAg = 0;
        slipUsed = 0;
    else
        z2 = machine.r2 / slip + 1i * machine.x2;
        zF = 1 / (1 / zMag + 1 / z2);
        zIn = z1 + zF;
        i1 = machine.v_phase / zIn;
        i2 = (i1 * zF) / z2;
        pAg = 3 * (abs(i2) ^ 2) * machine.r2 / slip;
        slipUsed = slip;
    end
    pIn = 3 * machine.v_phase * real(i1);
    torque = pAg / machine.omega_sync;
    pMech = (1 - slipUsed) * pAg;
    iPhase = abs(i1);
    if strcmp(machine.connection, 'y')
        iLine = iPhase;
    else
        iLine = sqrt(3) * iPhase;
    end
    apparent = 3 * machine.v_phase * iPhase;
    if apparent > 0
        powerFactor = pIn / apparent;
    else
        powerFactor = NaN;
    end
    if slipUsed > 0 && slipUsed < 1 && pIn > 0 && pMech > 0
        efficiency = pMech / pIn;
    else
        efficiency = NaN;
    end
    omega = (1 - slipUsed) * machine.omega_sync;
    point = make_point(slipUsed, (1 - slipUsed) * machine.n_sync, omega, torque, ...
        iLine, iPhase, abs(i2), pIn, pMech, powerFactor, efficiency);
end

function slip = breakdown_slip(machine)
    reactance = machine.x_th + machine.x2;
    slip = machine.r2 / sqrt(machine.r_th ^ 2 + reactance ^ 2);
end

function torque = breakdown_torque(machine)
    reactance = machine.x_th + machine.x2;
    magnitude = sqrt(machine.r_th ^ 2 + reactance ^ 2);
    denominator = machine.r_th + magnitude;
    if ~(denominator > 0)
        error('motor_torque_speed:BadOption', 'breakdown torque is undefined for these impedances');
    end
    torque = (3 / (2 * machine.omega_sync)) * (abs(machine.v_th) ^ 2) / denominator;
end

function slipRated = solve_induction_slip(machine, pRated, slipBreakdown)
    sHi = min(slipBreakdown, 1);
    if ~(sHi > 1e-8)
        error('motor_torque_speed:BadOption', 'breakdown slip is too small to solve for p_rated');
    end
    sLo = min(1e-6, sHi * 1e-4);
    slips = zeros(200, 1);
    powers = zeros(200, 1);
    for index = 1:200
        slips(index) = sLo + (sHi - sLo) * (index - 1) / 199;
        sample = induction_point(machine, slips(index));
        powers(index) = sample.power_mech_w;
    end
    [peak, peakIndex] = max(powers);
    if pRated > peak && (pRated - peak) > max(1e-6, 1e-8 * max(peak, 1))
        error('motor_torque_speed:BadOption', ...
            'p_rated is above the developed power in the stable region');
    end
    if powers(1) >= pRated
        lo = 0;
        hi = slips(1);
    else
        found = 0;
        for index = 1:(peakIndex - 1)
            if powers(index) <= pRated && pRated <= powers(index + 1)
                found = index;
                break
            end
        end
        if found == 0
            if abs(peak - pRated) <= max(1e-6, 1e-7 * pRated)
                slipRated = slips(peakIndex);
                return
            end
            error('motor_torque_speed:BadOption', ...
                'p_rated is above the developed power in the stable region');
        end
        lo = slips(found);
        hi = slips(found + 1);
    end
    for step = 1:60 %#ok<NASGU>
        mid = 0.5 * (lo + hi);
        sample = induction_point(machine, mid);
        if sample.power_mech_w < pRated
            lo = mid;
        else
            hi = mid;
        end
    end
    slipRated = 0.5 * (lo + hi);
end

function slip = insert_slip(slip, extra)
    slip = slip(:);
    if isempty(slip) || extra <= slip(1) || extra >= slip(end)
        return
    end
    if min(abs(slip - extra)) <= 1e-12 * max(1, abs(extra))
        return
    end
    slip = sort([slip; extra]);
end

function point = dc_linear_point(v, ra, kPhi, iField, torque)
    iArmature = torque / kPhi;
    omega = (v - iArmature * ra) / kPhi;
    if abs(omega) <= 1e-12 * max(abs(v / kPhi), 1)
        omega = 0;
    end
    pMech = torque * omega;
    if isfinite(iField)
        iLine = iArmature + iField;
    else
        iLine = iArmature;
    end
    pIn = v * iLine;
    if pMech > 0 && pIn > 0
        efficiency = pMech / pIn;
    elseif pIn > 0 && pMech == 0
        efficiency = 0;
    else
        efficiency = NaN;
    end
    point = make_point(NaN, rpm_from_omega(omega), omega, torque, iLine, iArmature, ...
        NaN, pIn, pMech, NaN, efficiency);
end

function torque = solve_linear_torque(v, ra, kPhi, pRated, tStall)
    omega0 = v / kPhi;
    slope = ra / (kPhi * kPhi);
    discriminant = omega0 * omega0 - 4 * slope * pRated;
    if discriminant < -1e-9 * omega0 * omega0
        error('motor_torque_speed:BadOption', 'p_rated is above the maximum developed power');
    end
    discriminant = max(discriminant, 0);
    torque = (omega0 - sqrt(discriminant)) / (2 * slope);
    if torque < 0 || torque > tStall * (1 + 1e-9)
        error('motor_torque_speed:BadOption', 'p_rated is above the maximum developed power');
    end
    torque = min(max(torque, 0), tStall);
end

function point = series_point(v, rTot, kF, torque)
    if ~(torque > 0)
        error('motor_torque_speed:BadOption', 'series torque must be positive');
    end
    current = sqrt(torque / kF);
    omega = v / (kF * current) - rTot / kF;
    pMech = torque * omega;
    pIn = v * current;
    if pMech > 0 && pIn > 0
        efficiency = pMech / pIn;
    elseif pIn > 0 && abs(pMech) <= 1e-9 * pIn
        efficiency = 0;
    else
        efficiency = NaN;
    end
    point = make_point(NaN, rpm_from_omega(omega), omega, torque, current, current, ...
        NaN, pIn, pMech, NaN, efficiency);
end

function torque = solve_series_torque(v, rTot, kF, pRated)
    a = rTot / kF;
    b = -v / sqrt(kF);
    discriminant = b * b - 4 * a * pRated;
    if discriminant < -1e-9 * b * b
        error('motor_torque_speed:BadOption', 'p_rated is above the maximum developed power');
    end
    discriminant = max(discriminant, 0);
    u = (-b - sqrt(discriminant)) / (2 * a);
    if ~(u > 0)
        error('motor_torque_speed:BadOption', 'p_rated is above the maximum developed power');
    end
    torque = u * u;
end

function rpm = rpm_from_omega(omega)
    rpm = omega * 60 / (2 * pi);
end

function check_slip_window(sMin, sMax)
    if sMin < -2 || sMax > 3
        error('motor_torque_speed:BadOption', 's_min and s_max must lie in [-2, 3]');
    end
    if sMax < sMin
        error('motor_torque_speed:BadOption', 's_max must be greater than or equal to s_min');
    end
end

function text = format_summary(cases)
    parts = cell(1, numel(cases));
    for index = 1:numel(cases)
        parts{index} = format_case(cases(index));
    end
    text = strjoin(parts, sprintf('\n\n'));
end

function text = format_case(motorCase)
    head = sprintf('name=%s  motor=%s', motorCase.name, motorCase.motor);
    if strcmp(motorCase.motor, 'induction')
        lines = { ...
            sprintf(['%s  connection=%s  V=%s  f=%s  poles=%s  n_sync=%s  N=%d'], ...
                head, motorCase.connection, compact_num(motorCase.v), compact_num(motorCase.f), ...
                compact_num(motorCase.poles), compact_num(motorCase.n_sync_rpm), motorCase.n_samples), ...
            sprintf(['R1=%s  X1=%s  R2=%s  X2=%s  Xm=%s  Rc=%s  Vph=%s  Vth=%s  Rth=%s  Xth=%s'], ...
                compact_num(motorCase.r1), compact_num(motorCase.x1), compact_num(motorCase.r2), ...
                compact_num(motorCase.x2), compact_num(motorCase.xm), compact_num(motorCase.rc), ...
                compact_num(motorCase.v_phase), compact_num(motorCase.v_th), ...
                compact_num(motorCase.r_th), compact_num(motorCase.x_th)), ...
            sprintf('T_start=%s  s_bd=%s  n_bd=%s  T_bd=%s', ...
                compact_num(motorCase.torque_start_nm), compact_num(motorCase.slip_breakdown), ...
                compact_num(motorCase.speed_breakdown_rpm), compact_num(motorCase.torque_breakdown_nm)), ...
            rated_induction(motorCase)};
    elseif strcmp(motorCase.motor, 'dc_shunt')
        lines = { ...
            sprintf('%s  V=%s  Ra=%s  Rf=%s  Kf=%s  Kphi=%s  If=%s  N=%d', ...
                head, compact_num(motorCase.v), compact_num(motorCase.ra), compact_num(motorCase.rf), ...
                compact_num(motorCase.k_f), compact_num(motorCase.k_phi), ...
                compact_num(motorCase.i_field_a), motorCase.n_samples), ...
            sprintf('n0=%s  T_stall=%s  I_stall=%s', ...
                compact_num(motorCase.speed_noload_rpm), compact_num(motorCase.torque_stall_nm), ...
                compact_num(motorCase.i_stall_a)), ...
            rated_dc(motorCase)};
    elseif strcmp(motorCase.motor, 'dc_series')
        lines = { ...
            sprintf('%s  V=%s  Ra=%s  Rs=%s  Kf=%s  Imin=%s  Imax=%s  N=%d', ...
                head, compact_num(motorCase.v), compact_num(motorCase.ra), compact_num(motorCase.rs), ...
                compact_num(motorCase.k_f), compact_num(motorCase.i_min), compact_num(motorCase.i_max), ...
                motorCase.n_samples), ...
            sprintf('n0=%s  T_stall=%s  I_stall=%s', ...
                compact_num(motorCase.speed_noload_rpm), compact_num(motorCase.torque_stall_nm), ...
                compact_num(motorCase.i_stall_a)), ...
            rated_dc(motorCase)};
    else
        lines = { ...
            sprintf('%s  V=%s  Ra=%s  Kphi=%s  N=%d', ...
                head, compact_num(motorCase.v), compact_num(motorCase.ra), ...
                compact_num(motorCase.k_phi), motorCase.n_samples), ...
            sprintf('n0=%s  T_stall=%s  I_stall=%s', ...
                compact_num(motorCase.speed_noload_rpm), compact_num(motorCase.torque_stall_nm), ...
                compact_num(motorCase.i_stall_a)), ...
            rated_dc(motorCase)};
    end
    text = strjoin(lines, sprintf('\n'));
end

function text = rated_induction(motorCase)
    if ~isfinite(motorCase.s_rated)
        text = 'rated  undefined';
        return
    end
    text = sprintf(['rated  s=%s  n=%s  T=%s  I_line=%s  I2=%s  ', ...
        'P_mech=%s  P_in=%s  pf=%s  eta=%s'], ...
        compact_num(motorCase.s_rated), compact_num(motorCase.speed_rated_rpm), ...
        compact_num(motorCase.torque_rated_nm), compact_num(motorCase.i_line_rated_a), ...
        compact_num(motorCase.i2_rated_a), compact_num(motorCase.power_mech_rated_w), ...
        compact_num(motorCase.power_in_rated_w), compact_num(motorCase.pf_rated), ...
        eta_text(motorCase.efficiency_rated));
end

function text = rated_dc(motorCase)
    if ~isfinite(motorCase.torque_rated_nm)
        text = 'rated  undefined';
        return
    end
    text = sprintf('rated  n=%s  T=%s  I_line=%s  P_mech=%s  P_in=%s  eta=%s', ...
        compact_num(motorCase.speed_rated_rpm), compact_num(motorCase.torque_rated_nm), ...
        compact_num(motorCase.i_line_rated_a), compact_num(motorCase.power_mech_rated_w), ...
        compact_num(motorCase.power_in_rated_w), eta_text(motorCase.efficiency_rated));
end

function text = eta_text(value)
    if ~isfinite(value)
        text = 'nan';
    else
        text = sprintf('%.4f%%', 100 * value);
    end
end

function write_summary(csvPath, cases)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('motor_torque_speed:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, ['name,motor,connection,v,f,poles,n_sync_rpm,v_phase,v_th,r_th,x_th,', ...
        'torque_start_nm,slip_breakdown,speed_breakdown_rpm,torque_breakdown_nm,', ...
        's_rated,speed_rated_rpm,torque_rated_nm,i_line_rated_a,i2_rated_a,', ...
        'power_mech_rated_w,power_in_rated_w,pf_rated,efficiency_rated,', ...
        'ra,rf,rs,k_phi,k_f,i_field_a,speed_noload_rpm,torque_stall_nm,i_stall_a\n']);
    for index = 1:numel(cases)
        item = cases(index);
        fprintf(fid, ['%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,', ...
            '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n'], ...
            item.name, item.motor, item.connection, ...
            csv_num(item.v), csv_num(item.f), csv_num(item.poles), csv_num(item.n_sync_rpm), ...
            csv_num(item.v_phase), csv_num(item.v_th), csv_num(item.r_th), csv_num(item.x_th), ...
            csv_num(item.torque_start_nm), csv_num(item.slip_breakdown), ...
            csv_num(item.speed_breakdown_rpm), csv_num(item.torque_breakdown_nm), ...
            csv_num(item.s_rated), csv_num(item.speed_rated_rpm), csv_num(item.torque_rated_nm), ...
            csv_num(item.i_line_rated_a), csv_num(item.i2_rated_a), ...
            csv_num(item.power_mech_rated_w), csv_num(item.power_in_rated_w), ...
            csv_num(item.pf_rated), csv_num(item.efficiency_rated), ...
            csv_num(item.ra), csv_num(item.rf), csv_num(item.rs), ...
            csv_num(item.k_phi), csv_num(item.k_f), csv_num(item.i_field_a), ...
            csv_num(item.speed_noload_rpm), csv_num(item.torque_stall_nm), csv_num(item.i_stall_a));
    end
end

function text = csv_num(value)
    if isempty(value) || ~isscalar(value) || ~isnumeric(value) || isnan(value)
        text = 'nan';
        return
    end
    if isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
        return
    end
    text = sprintf('%.12g', value);
end

function fig = render_figure(cases, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    groups = panel_groups(cases);
    nGroups = numel(groups);
    if nGroups == 1
        height = 540;
    elseif nGroups == 2
        height = 860;
    else
        height = 1220;
    end
    palette = [ ...
        31, 78, 121; ...
        192, 57, 43; ...
        14, 124, 102; ...
        230, 126, 34; ...
        108, 52, 131; ...
        26, 82, 118; ...
        146, 43, 33; ...
        27, 79, 114] / 255;
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 40 1040 height], ...
        'Name', 'motor-torque-speed', 'NumberTitle', 'off');
    for groupIndex = 1:nGroups
        ax = subplot(nGroups, 1, groupIndex, 'Parent', fig);
        hold(ax, 'on');
        group = groups{groupIndex};
        speeds = [];
        torques = [];
        labels = cell(1, numel(group.items));
        for index = 1:numel(group.items)
            item = group.items(index);
            color = palette(mod(index - 1, size(palette, 1)) + 1, :);
            labels{index} = case_label(item);
            plot(ax, item.speed_rpm, item.torque_nm, 'Color', color, 'LineWidth', 1.7);
            finiteSpeed = item.speed_rpm(isfinite(item.speed_rpm));
            finiteTorque = item.torque_nm(isfinite(item.torque_nm));
            speeds = [speeds; finiteSpeed(:)]; %#ok<AGROW>
            torques = [torques; finiteTorque(:)]; %#ok<AGROW>
            [speeds, torques] = draw_markers(ax, item, color, speeds, torques);
        end
        hold(ax, 'off');
        style_speed_axis(ax, group.title, speeds, torques, labels);
    end
    if ~isempty(outputPng)
        folder = fileparts(outputPng);
        if ~isempty(folder) && exist(folder, 'dir') ~= 7
            mkdir(folder);
        end
        save_png(fig, outputPng);
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function groups = panel_groups(cases)
    groups = {};
    induction = cases(strcmp({cases.motor}, 'induction'));
    linearMask = strcmp({cases.motor}, 'dc_shunt') | strcmp({cases.motor}, 'dc_separate');
    linear = cases(linearMask);
    series = cases(strcmp({cases.motor}, 'dc_series'));
    if ~isempty(induction)
        groups{end + 1} = struct('title', 'Induction motor', 'items', induction); %#ok<AGROW>
    end
    if ~isempty(linear)
        groups{end + 1} = struct('title', 'DC shunt / separately excited', 'items', linear); %#ok<AGROW>
    end
    if ~isempty(series)
        groups{end + 1} = struct('title', 'DC series', 'items', series); %#ok<AGROW>
    end
end

function label = case_label(motorCase)
    if isempty(motorCase.name)
        label = motorCase.motor;
    else
        label = motorCase.name;
    end
end

function [speeds, torques] = draw_markers(ax, motorCase, color, speeds, torques)
    if strcmp(motorCase.motor, 'induction')
        if motorCase.s_min <= 1 && 1 <= motorCase.s_max && isfinite(motorCase.torque_start_nm)
            plot(ax, 0, motorCase.torque_start_nm, 's', 'Color', color, ...
                'MarkerFaceColor', color, 'MarkerSize', 6, 'HandleVisibility', 'off');
            speeds(end + 1, 1) = 0; %#ok<AGROW>
            torques(end + 1, 1) = motorCase.torque_start_nm; %#ok<AGROW>
        end
        if motorCase.s_min <= motorCase.slip_breakdown && motorCase.slip_breakdown <= motorCase.s_max
            plot(ax, motorCase.speed_breakdown_rpm, motorCase.torque_breakdown_nm, 'v', ...
                'Color', color, 'MarkerFaceColor', color, 'MarkerSize', 7, ...
                'HandleVisibility', 'off');
            speeds(end + 1, 1) = motorCase.speed_breakdown_rpm; %#ok<AGROW>
            torques(end + 1, 1) = motorCase.torque_breakdown_nm; %#ok<AGROW>
        end
    end
    if isfinite(motorCase.speed_rated_rpm) && isfinite(motorCase.torque_rated_nm)
        plot(ax, motorCase.speed_rated_rpm, motorCase.torque_rated_nm, 'o', ...
            'Color', color, 'MarkerFaceColor', color, 'MarkerSize', 6, ...
            'HandleVisibility', 'off');
        speeds(end + 1, 1) = motorCase.speed_rated_rpm; %#ok<AGROW>
        torques(end + 1, 1) = motorCase.torque_rated_nm; %#ok<AGROW>
    end
end

function style_speed_axis(ax, titleText, speeds, torques, labels)
    title(ax, titleText);
    xlabel(ax, 'Speed (rpm)');
    ylabel(ax, 'Torque (N·m)');
    style_axes(ax);
    % Labels are passed in so Octave's gnuplot legend does not have to read
    % DisplayName. Interpreter none keeps underscores in case names literal.
    % Markers are drawn with HandleVisibility off.
    try
        legend(ax, labels, 'Location', 'northeast', 'Box', 'on', 'Interpreter', 'none');
    catch
        legend(ax, labels, 'Location', 'northeast', 'Box', 'on');
    end
    if isempty(speeds) || isempty(torques)
        return
    end
    xmin = min(speeds);
    xmax = max(speeds);
    ymin = min(0, min(torques));
    ymax = max(torques);
    if xmax > xmin
        span = xmax - xmin;
    else
        span = max(abs(xmax), 1);
    end
    xpad = 0.04 * span;
    if ymax > ymin
        ySpan = ymax - ymin;
    else
        ySpan = max(abs(ymax), 1);
    end
    ypad = 0.08 * ySpan;
    if xmin >= -1e-9 && xmin <= 0.05 * max(xmax, 1)
        xmin = 0;
        xpadLeft = 0;
    else
        xpadLeft = xpad;
    end
    if ymin >= -1e-9
        ypadBottom = 0;
    else
        ypadBottom = ypad;
    end
    xlim(ax, [xmin - xpadLeft, xmax + xpad]);
    ylim(ax, [ymin - ypadBottom, ymax + ypad]);
end

function style_axes(ax)
    grid(ax, 'on');
    box(ax, 'on');
    set(ax, 'FontSize', 11);
    % Dot assignment of GridColor fails on Octave's gnuplot toolkit.
    try
        set(ax, 'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.8);
    catch
    end
end

function save_png(fig, outputPng)
    if ~isempty(which('exportgraphics'))
        exportgraphics(fig, outputPng, 'Resolution', 150);
    else
        print(fig, outputPng, '-dpng', '-r150');
    end
end

function value = struct_lookup(data, keys)
    names = fieldnames(data);
    for index = 1:numel(names)
        key = normalize_key(names{index});
        for candidate = 1:numel(keys)
            if strcmp(key, keys{candidate})
                value = data.(names{index});
                return
            end
        end
    end
    value = '';
end

function value = optional_number(name, raw)
    if is_blank(raw)
        value = [];
        return
    end
    if isnumeric(raw) && isscalar(raw) && isinf(raw)
        value = double(raw);
        return
    end
    if is_text_scalar(raw)
        text = lower(as_char(raw));
        if any(strcmp(text, {'inf', '+inf', 'infinity'}))
            value = inf;
            return
        end
    end
    value = finite_number(name, raw);
end

function value = positive_or_default(name, raw, defaultValue)
    if isempty(raw)
        value = defaultValue;
    else
        value = positive_number(name, raw);
    end
end

function motor = normalize_motor(value)
    key = normalize_key(value);
    if any(strcmp(key, {'induction', 'im', 'async', 'asynchronous', char("感应"), char("异步")}))
        motor = 'induction';
        return
    end
    if any(strcmp(key, {'dcshunt', 'shunt', char("并励")}))
        motor = 'dc_shunt';
        return
    end
    if any(strcmp(key, {'dcseparate', 'separate', 'separately', 'sep', char("他励")}))
        motor = 'dc_separate';
        return
    end
    if any(strcmp(key, {'dcseries', 'series', char("串励")}))
        motor = 'dc_series';
        return
    end
    error('motor_torque_speed:BadOption', ...
        'motor must be ''induction'', ''dc_shunt'', ''dc_separate'', or ''dc_series''');
end

function connection = normalize_connection(value)
    key = normalize_key(value);
    if any(strcmp(key, {'y', 'wye', 'star', char("星形")}))
        connection = 'y';
        return
    end
    if any(strcmp(key, {'d', 'delta', char("三角形")}))
        connection = 'd';
        return
    end
    error('motor_torque_speed:BadOption', 'connection must be ''y'' (star) or ''d'' (delta)');
end

function text = as_text(value)
    if is_blank(value)
        text = '';
        return
    end
    text = as_char(value);
end

function text = as_char(value)
    % Char in both MATLAB and Octave. MATLAB string scalars are converted;
    % Octave has no string() constructor.
    if ischar(value)
        text = strtrim(value);
        return
    end
    if is_string_value(value)
        text = strtrim(char(value));
        return
    end
    if isnumeric(value)
        if isempty(value)
            text = '';
        else
            text = strtrim(num2str(value));
        end
        return
    end
    text = strtrim(char(value));
end

function tf = is_string_value(value)
    tf = false;
    if exist('isstring', 'builtin') == 5 || exist('isstring', 'file') == 2
        tf = isstring(value);
    end
end

function key = normalize_key(value)
    text = lower(as_char(value));
    key = regexprep(text, '[\s_\-]', '');
end

function tf = is_blank(value)
    if isempty(value)
        tf = true;
        return
    end
    if ischar(value) || is_string_value(value)
        tf = isempty(as_char(value));
        return
    end
    if isnumeric(value) && isscalar(value) && isnan(value)
        tf = true;
        return
    end
    tf = false;
end

function text = compact_num(value)
    if isempty(value) || ~isscalar(value) || ~isnumeric(value) || isnan(value)
        text = 'nan';
        return
    end
    if isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
        return
    end
    text = sprintf('%.6g', value);
    if ~isempty(strfind(lower(text), 'e')) %#ok<STREMP>
        if abs(value - round(value)) <= 1e-6 * max(abs(value), 1)
            text = sprintf('%.0f', value);
        else
            text = sprintf('%.4f', value);
        end
    end
end

function number = finite_number(name, value)
    if iscell(value)
        if numel(value) ~= 1
            error('motor_torque_speed:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if ischar(value) || is_string_value(value)
        number = str2double(as_char(value));
    elseif isnumeric(value)
        number = double(value);
    else
        error('motor_torque_speed:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('motor_torque_speed:BadOption', '%s must be a finite number', name);
    end
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('motor_torque_speed:BadOption', '%s must be a positive finite number', name);
    end
end

function number = nonnegative_number(name, value)
    number = finite_number(name, value);
    if number < 0
        error('motor_torque_speed:BadOption', '%s must be zero or a positive finite number', name);
    end
end

function number = positive_int(name, value, minimum, maximum)
    number = finite_number(name, value);
    if abs(number - round(number)) > 1e-9
        error('motor_torque_speed:BadOption', '%s must be an integer from %d to %d', ...
            name, minimum, maximum);
    end
    number = round(number);
    if number < minimum || number > maximum
        error('motor_torque_speed:BadOption', '%s must be an integer from %d to %d', ...
            name, minimum, maximum);
    end
end

function tf = as_bool(name, value)
    if islogical(value) && isscalar(value)
        tf = value;
        return
    end
    if isnumeric(value) && isscalar(value) && (value == 0 || value == 1)
        tf = logical(value);
        return
    end
    error('motor_torque_speed:BadOption', '%s must be true or false', name);
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = is_string_value(value) && isscalar(value);
end

function tf = is_parameter_name(value)
    if isempty(value)
        tf = false;
        return
    end
    if ischar(value)
        text = value;
    elseif is_string_value(value) && isscalar(value)
        text = char(value);
    else
        tf = false;
        return
    end
    keys = {'name', 'motor', 'v', 'f', 'poles', 'connection', 'r1', 'x1', 'r2', 'x2', ...
        'xm', 'rc', 'p_rated', 's_rated', 't_rated', 'ra', 'rf', 'rs', 'k_phi', 'k_f', ...
        'i_min', 'i_max', 's_min', 's_max', 'n_points', 'csv_path', 'output_csv', ...
        'output_png', 'show'};
    tf = any(strcmpi(strtrim(text), keys));
end

function tf = was_passed(rest, key)
    tf = false;
    for index = 1:2:numel(rest)
        if is_parameter_name(rest{index}) && strcmpi(as_char(rest{index}), key)
            tf = true;
            return
        end
    end
end
