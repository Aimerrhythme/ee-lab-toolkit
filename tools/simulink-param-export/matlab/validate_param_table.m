function errors = validate_param_table(source)
%VALIDATE_PARAM_TABLE Return row issues without raising.
%   A header that cannot be mapped still raises simulink_param_export:BadTable.
    result = simulink_param_export(source, 'strict', false);
    errors = result.errors;
end
