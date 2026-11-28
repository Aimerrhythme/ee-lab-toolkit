function res = ett_window_loader(csv_path, input_len, pred_len, varargin)
%ETT_WINDOW_LOADER Load ETT-format CSV, split chronologically, scale with TRAIN stats, cut windows.
%   res = ett_window_loader(csv_path, input_len, pred_len)
%   res = ett_window_loader(..., 'split', [0.6 0.2 0.2], 'target', 'OT', 'stride', 1)
%
%   CSV columns: date,HUFL,HULL,MUFL,MULL,LUFL,LULL,OT (first column = date).
%   res.train / res.val / res.test have fields
%       X     [n x input_len x n_features]  scaled inputs (all columns)
%       Y     [n x pred_len]                scaled target
%       start [n x 1]                       1-based row of the first input step
%   Other fields: columns, target, mean, std (TRAIN only), bounds, dates, summary.
%   Windows never straddle a split boundary, so there is no leakage.

    p = inputParser;
    addParameter(p, 'split', [0.6 0.2 0.2]);
    addParameter(p, 'target', 'OT');
    addParameter(p, 'stride', 1);
    parse(p, varargin{:});
    split = p.Results.split(:)';
    target = p.Results.target;
    stride = p.Results.stride;

    if input_len < 1 || pred_len < 1 || stride < 1
        error('ett_window_loader:args', 'input_len, pred_len and stride must be >= 1');
    end
    if numel(split) ~= 3 || any(split <= 0) || abs(sum(split) - 1) > 1e-9
        error('ett_window_loader:split', 'split must be 3 positive fractions summing to 1');
    end

    % ---- read file (date column as text, the rest numeric)
    fid = fopen(csv_path, 'r');
    if fid < 0
        error('ett_window_loader:file', 'cannot open %s', csv_path);
    end
    cleaner = onCleanup(@() fclose(fid));
    header = strtrim(strsplit(strtrim(fgetl(fid)), ','));
    if ~strcmpi(header{1}, 'date')
        error('ett_window_loader:header', 'first column must be ''date''');
    end
    columns = header(2:end);
    nf = numel(columns);
    C = textscan(fid, ['%s' repmat('%f', 1, nf)], 'Delimiter', ',');
    dates = C{1};
    data = [C{2:end}];
    if any(isnan(data(:)))
        error('ett_window_loader:nan', 'NaN found; clean the file first');
    end
    if ~issorted(string(dates))
        error('ett_window_loader:order', 'dates must be in ascending order');
    end
    j = find(strcmp(columns, target), 1);
    if isempty(j)
        error('ett_window_loader:target', 'target %s not in columns', target);
    end

    % ---- chronological split and TRAIN-only statistics
    n = size(data, 1);
    b1 = floor(n * split(1));
    b2 = b1 + floor(n * split(2));
    mu = mean(data(1:b1, :), 1);
    sd = std(data(1:b1, :), 1, 1);      % population std (ddof = 0), same as NumPy default
    sd(sd == 0) = 1;
    scaled = (data - mu) ./ sd;

    res.train = make_windows(scaled(1:b1, :), j, input_len, pred_len, stride, 0);
    res.val   = make_windows(scaled(b1+1:b2, :), j, input_len, pred_len, stride, b1);
    res.test  = make_windows(scaled(b2+1:n, :), j, input_len, pred_len, stride, b2);
    res.columns = columns;
    res.target = target;
    res.mean = mu;
    res.std = sd;
    res.bounds = [b1 b2 n];
    res.dates = dates;
    res.summary = sprintf(['ett-window-loader: rows=%d target=%s train=%d val=%d test=%d ' ...
        'windows, train_%s_mean=%.4f'], n, target, size(res.train.X, 1), ...
        size(res.val.X, 1), size(res.test.X, 1), target, mu(j));
end

function ws = make_windows(seg, j, input_len, pred_len, stride, offset)
    n = size(seg, 1);
    if n >= input_len + pred_len
        nw = floor((n - input_len - pred_len) / stride) + 1;
    else
        nw = 0;
    end
    X = zeros(nw, input_len, size(seg, 2));
    Y = zeros(nw, pred_len);
    start = zeros(nw, 1);
    for k = 1:nw
        s = (k - 1) * stride + 1;                      % 1-based within the segment
        X(k, :, :) = reshape(seg(s:s+input_len-1, :), 1, input_len, size(seg, 2));
        Y(k, :) = seg(s+input_len:s+input_len+pred_len-1, j)';
        start(k) = offset + s;
    end
    ws.X = X;
    ws.Y = Y;
    ws.start = start;
end
