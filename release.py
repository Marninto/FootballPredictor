APP_VERSION = '0.0.6'

RELEASE_NOTES = {
    '0.0.1': ['Initial tracked release.'],
    '0.0.2': [
        'Added scheduled fixture announcements for upcoming matches.',
        'Added bot update announcements',
        'Changed prediction cutoff to kickoff time.',
        'Made fixture listings visible only to the requester.',
        'Added fixture-level points earned to fixture listings after scores are updated.',
    ],
    '0.0.3': [
        'Moved release note announcements to an admin command.',
        'Added scheduler status command for announcements.',
        'Added manual announcement run command for validation.',
    ],
    '0.0.4': [
        'Added guided prediction form for up to 5 open fixtures. try predict_form',
        'Prediction confirmations now follow user visibility settings.',
        'Prediction form now supports updating existing predictions before kickoff.',
        'Improved help command with ordered sections and usage examples.',
    ],
    '0.0.5': [
        'Added Premier League 2026/27 fixtures under tournament code PL26.',
        'Added optional red-card-given prediction for rulesets that enable it.',
        'Added red-card-given scoring with positive and negative point outcomes.',
        'Fixtures now show your predicted score, goalscorer, and red-card-given prediction directly.',
        'Prediction form without a fixture id now starts from the next open fixture you have not predicted.',
    ],
    '0.0.6': [
        'Score point announcements now include the fixture teams and scoreline.',
        'Tournament code fields now suggest active tournaments where supported.',
    ],
}
