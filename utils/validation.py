def require_non_empty(value, field_name):
    if not value:
        raise ValueError(f'{field_name} is required')
    return value
