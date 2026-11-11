function result = evcs_load_window(csv_path, varargin)
%EVCS_LOAD_WINDOW Clean EV charging sessions, resample to station load, cut windows.
%   result = evcs_load_window(csv_path, 'step_min', 15, 'input_len', 8, ...
%       'horizon', 4, 'stride', 4, 'max_power_kw', 150, 'output_csv', path)
%
%   CSV columns: session_id,start_time,end_time,power_kw (times as
%   'yyyy-MM-dd HH:mm:ss'). A row is dropped if a field is missing, end <=
%   start, or power_kw is not in (0, max_power_kw]. Each kept session adds
%   power_kw to every bin in proportion to its overlap with the bin, so a bin
%   value is the mean station power (kW) over that bin.
%
%   Result fields match the Python tool: time, load_kw, X, y, window_start,
%   n_sessions, n_dropped, step_min, output_csv.

    p = inputParser;
    addParameter(p, 'step_min', 15);
    addParameter(p, 'input_len', 8);
    addParameter(p, 'horizon', 4);
    addParameter(p, 'stride', 4);
    addParameter(p, 'max_power_kw', 150);
    addParameter(p, 'output_csv', '');
    parse(p, varargin{:});
    step = p.Results.step_min;
    L = p.Results.input_len;
    H = p.Results.horizon;
    S = p.Results.stride;
    if step <= 0 || L < 1 || H < 1 || S < 1
        error('evcs_load_window:badArg', ...
            'step_min, input_len, horizon, stride must be positive');
    end

    T = readtable(csv_path, 'TextType', 'string');
    nSessions = height(T);
    fmt = 'yyyy-MM-dd HH:mm:ss';
    st = datetime(string(T.start_time), 'InputFormat', fmt);
    en = datetime(string(T.end_time), 'InputFormat', fmt);
    pw = double(T.power_kw);
    ok = ~isnat(st) & ~isnat(en) & isfinite(pw) & pw > 0 & pw <= p.Results.max_power_kw;
    ok = ok & (en > st);
    nDropped = sum(~ok);
    if ~any(ok)
        error('evcs_load_window:noData', 'no valid sessions after cleaning');
    end
    st = st(ok);
    en = en(ok);
    pw = pw(ok);

    tmin = min(st);
    day0 = dateshift(tmin, 'start', 'day');
    origin = day0 + minutes(floor(minutes(tmin - day0) / step) * step);
    sMin = minutes(st - origin);
    eMin = minutes(en - origin);
    nbins = ceil(max(eMin) / step);
    energy = zeros(nbins, 1);
    for i = 1:numel(pw)
        b0 = floor(sMin(i) / step);
        b1 = min(ceil(eMin(i) / step), nbins);
        for b = b0:(b1 - 1)
            lo = max(sMin(i), b * step);
            hi = min(eMin(i), (b + 1) * step);
            if hi > lo
                energy(b + 1) = energy(b + 1) + pw(i) * (hi - lo);
            end
        end
    end
    load_kw = energy / step;
    tm = origin + minutes((0:nbins - 1)' * step);

    span = L + H;
    if nbins >= span
        nwin = floor((nbins - span) / S) + 1;
    else
        nwin = 0;
    end
    X = zeros(nwin, L);
    y = zeros(nwin, H);
    for k = 1:nwin
        i = (k - 1) * S;
        X(k, :) = load_kw(i + 1:i + L)';
        y(k, :) = load_kw(i + L + 1:i + span)';
    end
    wstart = tm((0:nwin - 1)' * S + 1);

    result = struct('time', tm, 'load_kw', load_kw, 'X', X, 'y', y, ...
        'window_start', wstart, 'n_sessions', nSessions, ...
        'n_dropped', nDropped, 'step_min', step, 'output_csv', '');
    if ~isempty(p.Results.output_csv)
        result.output_csv = write_windows_csv(result, p.Results.output_csv);
    end
end

function path = write_windows_csv(result, path)
%WRITE_WINDOWS_CSV Columns: window_start, x_0..x_{L-1}, y_0..y_{H-1} (kW).
    outDir = fileparts(path);
    if ~isempty(outDir) && ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    L = size(result.X, 2);
    H = size(result.y, 2);
    names = ['window_start', compose('x_%d', 0:L - 1), compose('y_%d', 0:H - 1)];
    fid = fopen(path, 'w');
    fprintf(fid, '%s\n', strjoin(string(names), ','));
    vals = round([result.X, result.y] * 1000) / 1000;
    for k = 1:size(vals, 1)
        stamp = char(result.window_start(k), 'yyyy-MM-dd HH:mm:ss');
        fprintf(fid, '%s%s\n', stamp, sprintf(',%g', vals(k, :)));
    end
    fclose(fid);
end
