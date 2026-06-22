TRUE_VALUES = {'true', 'yes', 'y'}
FALSE_VALUES = {'false', 'no', 'n'}


def parse_yes_no(value, field_name):
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f'{field_name} must be yes or no.')


def normalize_yes_no(value, field_name):
    return 'true' if parse_yes_no(value, field_name) else 'false'
