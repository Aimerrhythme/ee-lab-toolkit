function result = bearing_envelope_spectrum(csvPath, varargin)
%BEARING_ENVELOPE_SPECTRUM Band-pass, Hilbert envelope, fault markers, features.
%   result = bearing_envelope_spectrum(csvPath, 'rpm',1797, 'n_balls',9, ...
%       'ball_d',7.94, 'pitch_d',39.04, 'contact_deg',0, 'band',[2000 5000], ...
%       'tol_hz',3, 'f_max',500, 'output_csv','', 'output_png','', 'show',false)
%   Input CSV: t_s,accel. Same semantics as python/bearing_envelope_spectrum.py.
%   Base MATLAB only (no toolboxes).

    p = inputParser;
    addParameter(p, 'rpm', 1797);
    addParameter(p, 'n_balls', 9);
    addParameter(p, 'ball_d', 7.94);
    addParameter(p, 'pitch_d', 39.04);
    addParameter(p, 'contact_deg', 0);
    addParameter(p, 'band', [2000 5000]);
    addParameter(p, 'tol_hz', 3);
    addParameter(p, 'f_max', 500);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;

    M = readmatrix(csvPath, 'NumHeaderLines', 1);
    t = M(:, 1);
    x = M(:, 2);
    if numel(x) < 16 || any(~isfinite(x)) || any(~isfinite(t))
        error('need >= 16 finite samples');
    end
    dt = diff(t);
    if any(dt <= 0)
        error('t_s must be strictly increasing');
    end
    fs = 1 / median(dt);

    fr = o.rpm / 60;
    c = (o.ball_d / o.pitch_d) * cos(deg2rad(o.contact_deg));
    freqs.fr = fr;
    freqs.bpfo = o.n_balls / 2 * fr * (1 - c);
    freqs.bpfi = o.n_balls / 2 * fr * (1 + c);
    freqs.bsf = o.pitch_d / (2 * o.ball_d) * fr * (1 - c^2);
    freqs.ftf = fr / 2 * (1 - c);

    % zero-phase FFT band-pass
    n = numel(x);
    if ~(0 <= o.band(1) && o.band(1) < o.band(2) && o.band(2) <= fs / 2)
        error('need 0 <= f_lo < f_hi <= fs/2');
    end
    fAll = (0:n-1)' * fs / n;
    fAll(fAll > fs / 2) = fAll(fAll > fs / 2) - fs;   % signed frequencies
    X = fft(x);
    keep = abs(fAll) >= o.band(1) & abs(fAll) <= o.band(2);
    xb = real(ifft(X .* keep));

    % Hilbert envelope (FFT method)
    H = zeros(n, 1);
    if mod(n, 2) == 0
        H(1) = 1; H(n/2 + 1) = 1; H(2:n/2) = 2;
    else
        H(1) = 1; H(2:(n+1)/2) = 2;
    end
    env = abs(ifft(fft(xb) .* H));

    % Hann-windowed single-sided amplitude spectrum of the envelope
    e0 = env - mean(env);
    w = 0.5 - 0.5 * cos(2 * pi * (0:n-1)' / (n - 1));   % numpy.hanning
    A = abs(fft(e0 .* w)) * 2 / sum(w);
    nh = floor(n / 2) + 1;
    fEnv = (0:nh-1)' * fs / n;
    aEnv = A(1:nh);

    sel = fEnv >= 10 & fEnv <= o.f_max;
    floorAmp = median(aEnv(sel));
    f = struct();
    f.rms = sqrt(mean(x.^2));
    f.peak = max(abs(x));
    f.crest = f.peak / f.rms;
    f.kurtosis = kurt(x);
    f.env_rms = sqrt(mean((env - mean(env)).^2));
    f.env_kurtosis = kurt(env);
    f.floor = floorAmp;
    names = {'fr', 'bpfo', 'bpfi'};
    for i = 1:3
        nm = names{i};
        m = fEnv >= freqs.(nm) - o.tol_hz & fEnv <= freqs.(nm) + o.tol_hz;
        if any(m), a = max(aEnv(m)); else, a = NaN; end
        f.(['amp_' nm]) = a;
        f.(['snr_' nm]) = a / floorAmp;
    end

    result.fs = fs;
    result.freqs = freqs;
    result.features = f;
    result.f_env = fEnv;
    result.amp_env = aEnv;
    result.summary = sprintf('fs=%.1f Hz fr=%.2f bpfo=%.2f bpfi=%.2f\nfeature,value', ...
        fs, freqs.fr, freqs.bpfo, freqs.bpfi);
    fn = fieldnames(f);
    for i = 1:numel(fn)
        result.summary = sprintf('%s\n%s,%.4f', result.summary, fn{i}, f.(fn{i}));
    end

    if ~isempty(o.output_csv)
        d = fileparts(o.output_csv);
        if ~isempty(d) && exist(d, 'dir') ~= 7, mkdir(d); end
        fid = fopen(o.output_csv, 'w');
        fprintf(fid, 'feature,value\n');
        for i = 1:numel(fn)
            fprintf(fid, '%s,%.6f\n', fn{i}, f.(fn{i}));
        end
        fclose(fid);
    end

    if ~isempty(o.output_png) || o.show
        if o.show, vis = 'on'; else, vis = 'off'; end
        fig = figure('Visible', vis, 'Position', [100 100 1000 380]);
        subplot(1, 2, 1);
        k = min(n, floor(0.1 * fs));
        plot((0:k-1) / fs, x(1:k));
        title(sprintf('Raw signal (first %.2f s)', k / fs)); xlabel('t (s)'); ylabel('accel');
        subplot(1, 2, 2);
        mm = fEnv <= o.f_max;
        plot(fEnv(mm), aEnv(mm)); hold on;
        cols = {'k', 'r', 'g'};
        for i = 1:3
            xline(freqs.(names{i}), '--', 'Color', cols{i}, ...
                'DisplayName', sprintf('%s %.1f Hz', names{i}, freqs.(names{i})));
        end
        title(sprintf('Envelope spectrum (band %.0f-%.0f Hz)', o.band(1), o.band(2)));
        xlabel('Hz'); ylabel('amplitude'); legend('show');
        if ~isempty(o.output_png)
            d = fileparts(o.output_png);
            if ~isempty(d) && exist(d, 'dir') ~= 7, mkdir(d); end
            saveas(fig, o.output_png);
        end
        if ~o.show, close(fig); end
    end
end

function k = kurt(v)
    d = v - mean(v);
    s2 = mean(d.^2);
    if s2 > 0, k = mean(d.^4) / s2^2; else, k = 0; end
end
