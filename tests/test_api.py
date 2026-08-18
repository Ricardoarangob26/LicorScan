"""Tests HTTP de la API.

Corren contra la base configurada en .env. Se saltan solos si no hay
conexión, para que la suite siga siendo utilizable sin credenciales.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from apiserver.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    try:
        with TestClient(app) as c:
            if c.get("/health").json().get("database") != "ok":
                pytest.skip("Base de datos no disponible")
            yield c
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No se pudo levantar la API: {exc!r}")


@pytest.fixture(scope="module")
def multi_store_product(client):
    """Un producto que exista en más de una tienda."""
    res = client.get("/api/v1/products", params={"multi_store": "true", "limit": 1})
    data = res.json()["data"]
    if not data:
        pytest.skip("Todavía no hay productos en varias tiendas")
    return data[0]


class TestSistema:
    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"

    def test_openapi_se_genera(self, client):
        res = client.get("/openapi.json")
        assert res.status_code == 200
        assert "/api/v1/products" in res.json()["paths"]

    def test_docs_disponibles(self, client):
        assert client.get("/docs").status_code == 200


class TestTiendas:
    def test_listar(self, client):
        res = client.get("/api/v1/stores")
        assert res.status_code == 200
        slugs = [s["slug"] for s in res.json()["data"]]
        assert "exito" in slugs

    def test_detalle(self, client):
        res = client.get("/api/v1/stores/exito")
        assert res.status_code == 200
        assert res.json()["data"]["slug"] == "exito"

    def test_inexistente(self, client):
        res = client.get("/api/v1/stores/no-existe")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "STORE_NOT_FOUND"


class TestProductos:
    def test_listar_con_paginacion(self, client):
        res = client.get("/api/v1/products", params={"limit": 5})
        assert res.status_code == 200
        body = res.json()
        assert len(body["data"]) <= 5
        assert body["meta"]["limit"] == 5
        assert body["meta"]["total"] >= len(body["data"])

    def test_limite_maximo_se_respeta(self, client):
        assert client.get("/api/v1/products", params={"limit": 9999}).status_code == 422

    def test_filtro_por_tienda(self, client):
        res = client.get("/api/v1/products", params={"store": "d1", "limit": 5})
        assert res.status_code == 200

    def test_filtro_por_precio(self, client):
        res = client.get("/api/v1/products", params={"min_price": 50000, "limit": 10})
        assert res.status_code == 200
        for p in res.json()["data"]:
            assert p["max_price"] >= 50000

    def test_detalle_incluye_precios(self, client, multi_store_product):
        res = client.get(f"/api/v1/products/{multi_store_product['id']}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["prices"]
        assert data["cheapest"]["price"] == min(p["price"] for p in data["prices"])

    def test_inexistente(self, client):
        res = client.get("/api/v1/products/99999999")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


class TestBusqueda:
    def test_encuentra_por_texto(self, client):
        res = client.get("/api/v1/products/search", params={"q": "whisky", "limit": 5})
        assert res.status_code == 200
        assert res.json()["meta"]["total"] >= 0

    def test_tolera_diferencias_de_escritura(self, client):
        """El punto de usar trigramas: minúsculas y sin tildes igual encuentran."""
        con_tilde = client.get("/api/v1/products/search", params={"q": "aguardiente antioqueño"})
        sin_tilde = client.get("/api/v1/products/search", params={"q": "AGUARDIENTE ANTIOQUENO"})
        assert con_tilde.status_code == sin_tilde.status_code == 200
        if con_tilde.json()["meta"]["total"]:
            assert sin_tilde.json()["meta"]["total"] > 0

    def test_query_muy_corta_es_invalida(self, client):
        res = client.get("/api/v1/products/search", params={"q": "a"})
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


class TestPrecios:
    def test_precios_ordenados_de_menor_a_mayor(self, client, multi_store_product):
        res = client.get(f"/api/v1/products/{multi_store_product['id']}/prices")
        assert res.status_code == 200
        precios = [p["price"] for p in res.json()["data"]["prices"]]
        assert precios == sorted(precios)

    def test_descuento_se_calcula_desde_list_price(self, client, multi_store_product):
        res = client.get(f"/api/v1/products/{multi_store_product['id']}/prices")
        for p in res.json()["data"]["prices"]:
            if p["list_price"]:
                assert p["list_price"] > p["price"]
                assert p["discount_pct"] > 0
            else:
                assert p["discount_pct"] is None

    def test_historial(self, client, multi_store_product):
        res = client.get(f"/api/v1/products/{multi_store_product['id']}/history")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["product_id"] == multi_store_product["id"]
        if data["points"]:
            assert data["min_price"] <= data["avg_price"] <= data["max_price"]

    def test_historial_de_producto_inexistente(self, client):
        assert client.get("/api/v1/products/99999999/history").status_code == 404


class TestComparacion:
    def test_comparar_producto(self, client, multi_store_product):
        res = client.get(f"/api/v1/compare/product/{multi_store_product['id']}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["stores_compared"] >= 2
        assert data["cheapest"]["price"] <= data["most_expensive"]["price"]

    def test_carrito(self, client, multi_store_product):
        payload = {"items": [{"product_id": multi_store_product["id"], "quantity": 2}]}
        res = client.post("/api/v1/compare/cart", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["results"]
        assert data["best_store"]
        # El total debe ser el precio unitario por la cantidad.
        mejor = next(r for r in data["results"] if r["store"]["slug"] == data["best_store"])
        assert mejor["total"] == pytest.approx(mejor["lines"][0]["unit_price"] * 2)

    def test_carrito_elige_la_tienda_mas_barata(self, client, multi_store_product):
        payload = {"items": [{"product_id": multi_store_product["id"], "quantity": 1}]}
        data = client.post("/api/v1/compare/cart", json=payload).json()["data"]
        completos = [r for r in data["results"] if r["items_missing"] == 0]
        if completos:
            assert data["best_total"] == min(r["total"] for r in completos)

    def test_cherry_pick_nunca_es_peor_que_la_mejor_tienda(self, client, multi_store_product):
        payload = {"items": [{"product_id": multi_store_product["id"], "quantity": 1}]}
        data = client.post("/api/v1/compare/cart", json=payload).json()["data"]
        if data["cherry_pick_total"] and data["best_total"]:
            assert data["cherry_pick_total"] <= data["best_total"]

    def test_carrito_vacio_es_invalido(self, client):
        res = client.post("/api/v1/compare/cart", json={"items": []})
        assert res.status_code == 422

    def test_producto_duplicado_en_el_carrito(self, client):
        payload = {"items": [{"product_id": 1}, {"product_id": 1}]}
        res = client.post("/api/v1/compare/cart", json=payload)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "DUPLICATE_PRODUCT"

    def test_producto_sin_precio(self, client):
        res = client.post("/api/v1/compare/cart", json={"items": [{"product_id": 99999999}]})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "NO_PRICES_FOUND"


class TestAdministracion:
    def test_corridas(self, client):
        res = client.get("/api/v1/admin/scrapes", params={"limit": 5})
        assert res.status_code == 200

    def test_corrida_inexistente(self, client):
        res = client.get("/api/v1/admin/scrapes/99999999")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "SCRAPE_RUN_NOT_FOUND"

    def test_estadisticas(self, client):
        res = client.get("/api/v1/admin/stats")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["stores"] >= 1
        assert data["products_multi_store"] <= data["products"]


class TestCatalogo:
    def test_marcas(self, client):
        assert client.get("/api/v1/brands", params={"limit": 5}).status_code == 200

    def test_categorias(self, client):
        assert client.get("/api/v1/categories").status_code == 200
