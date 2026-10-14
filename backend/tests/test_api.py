def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_ready_checks_database(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "READY"}


def test_root_identifies_service(client):
    assert client.get("/").json()["service"] == "StockPilot API"


def test_metrics_endpoint_exposes_prometheus_format(client):
    client.get("/api/products")
    body = client.get("/metrics").text
    assert "http_requests_total" in body
    assert "stockpilot_stock_adjustments_total" in body


def test_create_product_normalises_sku_and_computes_status(make_product):
    product = make_product(sku="abc-123", quantity=3, reorder_level=5)
    assert product["sku"] == "ABC-123"
    assert product["stock_status"] == "LOW_STOCK"


def test_create_product_rejects_invalid_payload(client):
    response = client.post("/api/products", json={"sku": "X", "name": "", "quantity": -1})
    assert response.status_code == 422


def test_duplicate_sku_returns_conflict(client, make_product):
    make_product(sku="DUP-1")
    response = client.post("/api/products", json={"sku": "dup-1", "name": "Another"})
    assert response.status_code == 409


def test_list_products_with_search_and_status_filter(client, make_product):
    make_product(sku="A-1", name="Alpha Scanner", quantity=50)
    make_product(sku="B-1", name="Beta Printer", quantity=0)
    make_product(sku="C-1", name="Gamma Scanner", quantity=2, reorder_level=10)

    assert len(client.get("/api/products").json()) == 3
    assert [p["sku"] for p in client.get("/api/products", params={"search": "scanner"}).json()] == ["A-1", "C-1"]
    assert [p["sku"] for p in client.get("/api/products", params={"stock_status": "OUT_OF_STOCK"}).json()] == ["B-1"]
    assert [p["sku"] for p in client.get("/api/products", params={"stock_status": "LOW_STOCK"}).json()] == ["C-1"]


def test_get_product_and_404(client, make_product):
    product = make_product()
    assert client.get(f"/api/products/{product['id']}").json()["name"] == "Test Widget"
    assert client.get("/api/products/9999").status_code == 404


def test_update_product_is_partial(client, make_product):
    product = make_product()
    response = client.put(f"/api/products/{product['id']}", json={"unit_price": "99.99", "location": "Bay Z9"})
    assert response.status_code == 200
    body = response.json()
    assert body["unit_price"] == "99.99"
    assert body["location"] == "Bay Z9"
    assert body["name"] == "Test Widget"
    assert body["quantity"] == product["quantity"]


def test_delete_product(client, make_product):
    product = make_product()
    assert client.delete(f"/api/products/{product['id']}").status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404
    assert client.delete(f"/api/products/{product['id']}").status_code == 404


def test_adjust_stock_records_movement(client, make_product):
    product = make_product(quantity=10)
    response = client.post(f"/api/products/{product['id']}/adjust", json={"change": -4, "reason": "SALE", "note": "Order #42"})
    assert response.status_code == 200
    assert response.json()["quantity"] == 6

    movements = client.get("/api/movements").json()
    assert movements[0]["change"] == -4
    assert movements[0]["quantity_after"] == 6
    assert movements[0]["reason"] == "SALE"
    assert movements[1]["note"] == "Initial stock"


def test_adjust_stock_cannot_go_negative(client, make_product):
    product = make_product(quantity=2)
    response = client.post(f"/api/products/{product['id']}/adjust", json={"change": -5, "reason": "SALE"})
    assert response.status_code == 409
    assert client.get(f"/api/products/{product['id']}").json()["quantity"] == 2


def test_stats_aggregate_inventory(client, make_product):
    make_product(sku="S-1", category="A", quantity=10, unit_price="2.50", reorder_level=1)
    make_product(sku="S-2", category="B", quantity=0, unit_price="100.00")
    make_product(sku="S-3", category="B", quantity=3, unit_price="1.00", reorder_level=5)

    stats = client.get("/api/products/stats").json()
    assert stats == {
        "totalProducts": 3,
        "totalUnits": 13,
        "inventoryValue": "28.00",
        "lowStock": 1,
        "outOfStock": 1,
        "categories": 2,
    }


def test_deleting_product_removes_its_movements(client, make_product):
    product = make_product(quantity=5)
    client.delete(f"/api/products/{product['id']}")
    assert client.get("/api/movements").json() == []
