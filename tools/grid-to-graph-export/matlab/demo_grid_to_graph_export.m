function demo_grid_to_graph_export()
%DEMO_GRID_TO_GRAPH_EXPORT Export the synthetic 4-bus graph and Ybus.
%   From this folder, call demo_grid_to_graph_export. Tables go to
%   examples/output/grid_to_graph_export_matlab/ and the figure to
%   examples/output/grid_to_graph_export_demo_matlab.png (gitignored).
%   Set 'show', true on the call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_grid.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    bundle = fullfile(outDir, 'grid_to_graph_export_matlab');
    png = fullfile(outDir, 'grid_to_graph_export_demo_matlab.png');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end

    result = grid_to_graph_export(csvPath, ...
        'output_dir', bundle, 'output_png', png, 'show', false);
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_dir);
end
