function demo_bearing_envelope_spectrum()
%DEMO_BEARING_ENVELOPE_SPECTRUM Envelope spectrum of the synthetic outer-race fault.
%   Outputs go to examples/output/ (gitignored).

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_bearing_vibration.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7, mkdir(outDir); end
    result = bearing_envelope_spectrum(csvPath, 'rpm', 1797, 'band', [2000 5000], ...
        'output_csv', fullfile(outDir, 'bearing_envelope_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'bearing_envelope_demo_matlab.png'), ...
        'show', false);
    fprintf('%s\n', result.summary);
    fprintf('outputs in %s\n', outDir);
end
