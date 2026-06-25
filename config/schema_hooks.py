_ERROR_SCHEMA = {'$ref': '#/components/schemas/ErrorDetail'}

_ERROR_RESPONSES = {
    '400': ('Bad request — validation error or missing required field.', True),
    '401': ('Authentication credentials were not provided or are invalid.', False),
    '403': ('You do not have permission to perform this action.', False),
    '404': ('Not found.', True),
}


def add_error_responses(result, generator, request, public):
    result.setdefault('components', {}).setdefault('schemas', {})['ErrorDetail'] = {
        'type': 'object',
        'properties': {'detail': {'type': 'string'}},
    }

    for path, path_data in result.get('paths', {}).items():
        has_path_param = '{' in path
        for method, operation in path_data.items():
            if not isinstance(operation, dict):
                continue
            responses = operation.setdefault('responses', {})
            is_mutating = method.upper() in ('POST', 'PUT', 'PATCH')
            for code, (description, conditional) in _ERROR_RESPONSES.items():
                if code in responses:
                    continue
                if code == '400' and not is_mutating:
                    continue
                if code == '404' and not has_path_param:
                    continue
                responses[code] = {
                    'description': description,
                    'content': {'application/json': {'schema': _ERROR_SCHEMA}},
                }

    return result
