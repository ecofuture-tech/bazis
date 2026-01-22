
import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.django_db(transaction=True)
def test_context_errors(sample_app, dynamic_vehicle_data):
    """Test to check for the absence of the declared context."""

    with pytest.raises(KeyError, match="Missing keys in the request context: {'_user'}"):
        get_api_client(sample_app).get('/api/v1/errors_context/dynamic/division/')

        pytest.fail('A KeyError was expected, but the request completed successfully.')


@pytest.mark.django_db(transaction=True)
def test_field_warning_logged(sample_app, dynamic_vehicle_data, caplog):
    """Check that a warning about the missing relation is written to the log."""

    with caplog.at_level('WARNING'):
        response = get_api_client(sample_app).get('/api/v1/errors_related_table/dynamic/division/')

    assert response.status_code == 200
    assert any(
        'Error in calculated field drivers_list1: model Division does not have related table drivers1'
        in message
        for message in caplog.messages
    )
