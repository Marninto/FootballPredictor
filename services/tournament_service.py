class TournamentService:
    def list_active_tournaments(self):
        return 'Active tournaments are not configured yet.'

    def show_rules(self, tournament_code=None):
        if tournament_code:
            return f'Scoring rules for {tournament_code} are not configured yet.'
        return 'Tournament scoring rules are not configured yet.'

    def add_tournament(self, name, code, ruleset_name=None):
        return f'Tournament creation is not implemented yet: {name} ({code}).'
