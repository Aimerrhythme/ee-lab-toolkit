function demo_bess_tou_qlearn_toy()
%DEMO_BESS_TOU_QLEARN_TOY Run bess-tou-qlearn-toy on the synthetic TOU tariff.
%   From this folder, call demo_bess_tou_qlearn_toy. Outputs go to
%   examples/output/ (gitignored).

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'tou_prices.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    r = bess_tou_qlearn_toy(csvPath, 'output_csv', fullfile(outDir, 'schedule_matlab.csv'));
    fprintf('bess-tou-qlearn-toy: hours=%d n_soc=%d greedy_cost=%.2f learned_cost=%.2f yuan\n', ...
        numel(r.prices), r.n_soc, r.greedy_cost, r.learned_cost);
    fig = figure('Visible', 'off');
    subplot(2, 1, 1);
    stairs(0:numel(r.prices)-1, r.prices);
    ylabel('price (yuan/kWh)');
    subplot(2, 1, 2);
    stairs(0:numel(r.prices), r.greedy_soc); hold on;
    stairs(0:numel(r.prices), r.learned_soc);
    xlabel('hour'); ylabel('SOC level'); legend('greedy', 'Q-learning');
    png = fullfile(outDir, 'bess_tou_qlearn_toy_demo_matlab.png');
    saveas(fig, png);
    close(fig);
    fprintf('saved %s\nsaved %s\n', png, r.output_csv);
end
