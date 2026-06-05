EXACT_SCORE_POINTS = 20
CORRECT_RESULT_POINTS = 5
CORRECT_GOAL_DIFFERENCE_POINTS = 5
GOALSCORER_POINTS = 5
RED_CARD_POINTS = 5

DEFAULT_RULESET_CONFIG = {
    'score_prediction': {
        'exact_score': 20,
        'correct_result': 5,
        'correct_goal_difference': 5,
    },
    'event_prediction': {
        'goalscorer': 10,
        'red_card': 10,
    },
}

REQUIRED_RULESET_KEYS = {
    'score_prediction': {
        'exact_score',
        'correct_result',
        'correct_goal_difference',
    },
    'event_prediction': {
        'goalscorer',
        'red_card',
    },
}


def validate_ruleset_config(config):
    if not isinstance(config, dict):
        raise ValueError('Ruleset config must be a JSON object.')

    for section, required_keys in REQUIRED_RULESET_KEYS.items():
        section_config = config.get(section)
        if not isinstance(section_config, dict):
            raise ValueError(f'Ruleset config must include {section}.')

        missing_keys = required_keys - set(section_config)
        if missing_keys:
            missing = ', '.join(sorted(missing_keys))
            raise ValueError(f'Ruleset config {section} is missing: {missing}.')

        for key in required_keys:
            value = section_config[key]
            if not isinstance(value, int) or value < 0:
                raise ValueError(f'Ruleset config {section}.{key} must be a non-negative integer.')

    return config
