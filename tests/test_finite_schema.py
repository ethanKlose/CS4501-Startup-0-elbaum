import pytest
from pydantic import ValidationError
from app.services.schema import IngredientIn


@pytest.mark.parametrize('field', ['quantity', 'cost'])
@pytest.mark.parametrize('value', [float('inf'), float('nan')])
def test_ingredient_rejects_nonfinite_values(field, value):
    payload = dict(name='rice', quantity=1, cost=1)
    payload[field] = value
    with pytest.raises(ValidationError):
        IngredientIn.model_validate(payload)
