from fastapi.testclient import TestClient

from .main import create_app


def test_create_order_through_fastapi_and_clean_ioc():
    with TestClient(create_app()) as client:
        response = client.post(
            "/orders",
            json={"customer_id": "customer-123", "total_pence": 2500},
        )

    assert response.status_code == 200
    assert response.json()["order_id"].startswith("order-payment-")
    assert response.json()["payment_id"].startswith("payment-")
