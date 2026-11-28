function demo_ett_window_loader()
%DEMO_ETT_WINDOW_LOADER Window the synthetic ETT-format CSV and plot OT vs load.
%   Outputs go to examples/output/ (gitignored).

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_ett.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    res = ett_window_loader(csvPath, 96, 24, 'split', [0.6 0.2 0.2], 'target', 'OT');
    fprintf('%s\n', res.summary);
    names = {'train', 'val', 'test'};
    for i = 1:3
        ws = res.(names{i});
        fprintf('%s: X[%s] Y[%s] first_start_row=%d (1-based)\n', names{i}, ...
            num2str(size(ws.X)), num2str(size(ws.Y)), ws.start(1));
    end
    fprintf('train mean OT=%.3f std OT=%.3f\n', res.mean(end), res.std(end));

    % re-read the raw series for the figure
    fid = fopen(csvPath, 'r');
    fgetl(fid);
    C = textscan(fid, ['%s' repmat('%f', 1, 7)], 'Delimiter', ',');
    fclose(fid);
    ot = C{8};
    load_sum = C{2} + C{4} + C{6};   % HUFL + MUFL + LUFL
    x = (1:numel(ot))';
    fig = figure('Visible', 'off');
    yyaxis left;  plot(x, ot, 'r-'); ylabel('OT (deg C)');
    yyaxis right; plot(x, load_sum, 'b-'); ylabel('useful load (synthetic units)');
    hold on;
    xline(res.bounds(1) + 0.5, 'k--');
    xline(res.bounds(2) + 0.5, 'k--');
    xlabel('hour index');
    title('Synthetic ETT-format data: OT vs load (dashed = train/val/test split)');
    png = fullfile(outDir, 'ett_window_loader_demo_matlab.png');
    saveas(fig, png);
    close(fig);
    fprintf('figure saved: %s\n', png);
end
