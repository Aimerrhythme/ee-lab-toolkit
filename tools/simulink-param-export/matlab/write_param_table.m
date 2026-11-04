function outputCsv = write_param_table(rows, csvPath)
%WRITE_PARAM_TABLE Check rows and write the canonical parameter CSV.
    result = simulink_param_export(rows, 'output_csv', csvPath, 'strict', true);
    outputCsv = result.output_csv;
end
