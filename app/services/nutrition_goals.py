"""Shared interpretation of legacy and combined nutrition settings."""
DEFAULT_PROTEIN = 75
MIN_PROTEIN, MAX_PROTEIN = 20, 300
MIN_CALORIES, MAX_CALORIES = 1200, 4500


def selected_goals(goal):
    return {
        'high_protein': ['high_protein'],
        'calorie_target': ['calorie_target'],
        'protein_calorie': ['high_protein', 'calorie_target'],
    }.get(goal, [])


def protein_target(ctx):
    if 'high_protein' not in selected_goals(ctx.goal):
        return None
    return ctx.protein_target if ctx.protein_target is not None else DEFAULT_PROTEIN
