APP_VERSION = '0.0.4'

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
}
