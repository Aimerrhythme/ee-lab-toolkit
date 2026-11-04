function rows = read_param_table(csvPath)
%READ_PARAM_TABLE Read a parameter CSV and return the checked rows.
    result = simulink_param_export(csvPath, 'strict', true);
    rows = result.rows;
end
