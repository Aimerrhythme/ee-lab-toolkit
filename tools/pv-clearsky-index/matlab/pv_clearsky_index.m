function result = pv_clearsky_index(csvPath, varargin)
%PV_CLEARSKY_INDEX Daily clear-sky index and clear/cloudy/overcast classification.
%   result = pv_clearsky_index(csvPath, 'lat', 25, 'clear_thr', 0.75, ...
%       'overcast_thr', 0.35, 'min_cosz', 0.2, 'output_csv', '', ...
%       'output_png', '', 'show', false)
%   CSV columns: date,hour,ghi (hour = local solar time, decimal hours).
%   Haurwitz clear-sky model, Cooper declination; kt = sum(ghi)/sum(ghi_cs)
%   over samples with cosz >= min_cosz.
    p = inputParser;
    addParameter(p, 'lat', 25);
    addParameter(p, 'clear_thr', 0.75);
    addParameter(p, 'overcast_thr', 0.35);
    addParameter(p, 'min_cosz', 0.2);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;
    if ~(o.overcast_thr > 0 && o.overcast_thr < o.clear_thr)
        error('need 0 < overcast_thr < clear_thr');
    end
    fid = fopen(csvPath, 'r');
    fgetl(fid);
    C = textscan(fid, '%s %f %f', 'Delimiter', ',');
    fclose(fid);
    dates = strtrim(C{1}); hours = C{2}; ghi = C{3};
    if isempty(ghi) || any(~isfinite(hours)) || any(~isfinite(ghi)) || any(ghi < 0) ...
            || any(hours < 0 | hours > 24)
        error('invalid or empty CSV');
    end
    doy = zeros(size(hours));
    for i = 1:numel(dates)
        dn = datenum(dates{i}, 'yyyy-mm-dd');
        doy(i) = dn - datenum(year(dn), 1, 1) + 1;
    end
    decl = deg2rad(23.45) * sin(2*pi*(284 + doy)/365);
    lat = deg2rad(o.lat);
    cosz = sin(lat)*sin(decl) + cos(lat)*cos(decl).*cos(deg2rad(15*(hours - 12)));
    cz = max(cosz, 1e-3);
    ghiCs = 1098 * cz .* exp(-0.057 ./ cz);
    ghiCs(cosz <= 1e-3) = 0;
    use = cosz >= o.min_cosz;
    [days, ia] = unique(dates, 'stable'); %#ok<ASGLU>
    nd = numel(days);
    kt = nan(nd, 1); sums = zeros(nd, 2); types = cell(1, nd);
    for i = 1:nd
        m = use & strcmp(dates, days{i});
        sums(i, :) = [sum(ghi(m)), sum(ghiCs(m))];
        if sums(i, 2) > 0, kt(i) = sums(i, 1) / sums(i, 2); end
        if isnan(kt(i)), types{i} = 'n/a';
        elseif kt(i) >= o.clear_thr, types{i} = 'clear';
        elseif kt(i) >= o.overcast_thr, types{i} = 'cloudy';
        else, types{i} = 'overcast';
        end
    end
    result = struct('dates', {days}, 'kt', kt, 'sky_type', {types}, ...
        'ghi_sum', sums(:, 1), 'clearsky_sum', sums(:, 2), 'lat', o.lat, 'n_days', nd);
    result.counts = struct('clear', sum(strcmp(types, 'clear')), ...
        'cloudy', sum(strcmp(types, 'cloudy')), 'overcast', sum(strcmp(types, 'overcast')));
    if ~isempty(o.output_csv)
        d = fileparts(o.output_csv);
        if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
        fo = fopen(o.output_csv, 'w');
        fprintf(fo, 'date,ghi_sum,clearsky_sum,kt,sky_type\n');
        for i = 1:nd
            fprintf(fo, '%s,%.2f,%.2f,%.4f,%s\n', days{i}, sums(i, 1), sums(i, 2), kt(i), types{i});
        end
        fclose(fo);
    end
    if ~isempty(o.output_png) || o.show
        vis = 'off'; if o.show, vis = 'on'; end
        fig = figure('Visible', vis, 'Position', [100 100 1000 380]);
        col = containers.Map({'clear', 'cloudy', 'overcast', 'n/a'}, ...
            {[1 .5 0], [.5 .5 .5], [0 .45 .74], [0 0 0]});
        subplot(1, 2, 1); hold on;
        for i = 1:nd
            m = strcmp(dates, days{i});
            plot(hours(m), ghi(m), 'Color', col(types{i}));
        end
        m1 = strcmp(dates, days{1});
        plot(hours(m1), ghiCs(m1), 'k--');
        xlabel('solar hour'); ylabel('GHI (W/m^2)'); title('Daily curves by sky type');
        subplot(1, 2, 2); hold on;
        for i = 1:nd
            bar(i - 1, max(kt(i), 0), 'FaceColor', col(types{i}));
        end
        xlabel('day index'); ylabel('clear-sky index kt'); title('Daily kt');
        if ~isempty(o.output_png)
            d = fileparts(o.output_png);
            if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
            saveas(fig, o.output_png);
        end
        if ~o.show, close(fig); end
    end
end
