from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.routes import projects
from app.models import AssetUnit, CommodityRelationship, Project, ProjectIdentity, Stock, StockProject
from app.services.stock_identity import normalize


def test_project_asset_and_commodity_entities_are_persistent(db_session):
    project = Project(project_key="splinter-rock", name="Splinter Rock", commodity="rare_earth", region="WA")
    stock = Stock(code="OD6", name="OD6 Metals", commodity="rare_earth")
    db_session.add_all([project, stock])
    db_session.flush()
    db_session.add(ProjectIdentity(project_id=project.id, kind="name", value=project.name, normalized_value=normalize(project.name), is_current=True))
    unit = AssetUnit(project_id=project.id, name="Centre", unit_type="deposit")
    db_session.add(unit)
    db_session.flush()
    db_session.add(CommodityRelationship(project_id=project.id, commodity="NdPr", is_economic=True))
    db_session.add(CommodityRelationship(asset_unit_id=unit.id, commodity="dysprosium", is_economic=True))
    db_session.commit()
    assert project.asset_units[0].name == "Centre"
    assert len(project.commodity_relationships) == 1


def test_project_api_lists_asset_units(db_session):
    project = Project(project_key="quinn", name="Quinn Project")
    db_session.add(project)
    db_session.flush()
    db_session.add(AssetUnit(project_id=project.id, name="Mammoth", unit_type="prospect"))
    db_session.commit()
    app = FastAPI()
    app.include_router(projects.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    response = client.get("/api/projects/quinn")
    assert response.status_code == 200
    assert response.json()["asset_units"][0]["name"] == "Mammoth"


def test_stock_project_api_exposes_project_tree(db_session):
    stock = Stock(code="OD6", name="OD6 Metals", commodity="rare_earth")
    project = Project(project_key="splinter", name="Splinter Rock")
    db_session.add_all([stock, project])
    db_session.flush()
    db_session.add(StockProject(stock_id=stock.id, project_id=project.id, ownership_pct=80.0))
    db_session.add(AssetUnit(project_id=project.id, name="Centre", unit_type="deposit"))
    db_session.commit()
    app = FastAPI()
    from app.api.routes import stocks
    app.include_router(stocks.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    response = TestClient(app).get("/api/stocks/OD6/projects")
    assert response.status_code == 200
    assert response.json()[0]["asset_units"][0]["name"] == "Centre"


def test_project_and_asset_identity_history_api_crud(db_session):
    project = Project(project_key="api-project", name="API Project")
    db_session.add(project)
    db_session.flush()
    asset = AssetUnit(project_id=project.id, name="Main Zone")
    db_session.add(asset)
    db_session.commit()
    app = FastAPI()
    from app.api.routes import projects
    app.include_router(projects.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    created = client.post("/api/projects/api-project/identities", json={"kind": "alias", "value": "Old API Project"})
    assert created.status_code == 201, created.text
    identity_id = created.json()["id"]
    assert client.get("/api/projects/api-project/identities").json()[0]["value"] == "Old API Project"
    updated = client.put(f"/api/projects/api-project/identities/{identity_id}", json={"kind": "alias", "value": "Renamed API Project"})
    assert updated.status_code == 200
    assert client.delete(f"/api/projects/api-project/identities/{identity_id}").status_code == 200

    created_asset = client.post(f"/api/projects/api-project/assets/{asset.id}/identities", json={"kind": "alias", "value": "Old Main Zone"})
    assert created_asset.status_code == 201, created_asset.text
    asset_identity_id = created_asset.json()["id"]
    assert client.get(f"/api/projects/api-project/assets/{asset.id}/identities").status_code == 200
    assert client.delete(f"/api/projects/api-project/assets/{asset.id}/identities/{asset_identity_id}").status_code == 200


def test_commodity_relationship_api_supports_history_and_overlap_checks(db_session):
    project = Project(project_key="commodity-api", name="Commodity API")
    db_session.add(project)
    db_session.flush()
    asset = AssetUnit(project_id=project.id, name="Orebody")
    db_session.add(asset)
    db_session.commit()
    app = FastAPI()
    from app.api.routes import projects
    app.include_router(projects.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    payload = {"commodity": "Lithium", "effective_from": "2020-01-01", "effective_to": "2022-01-01"}
    created = client.post("/api/projects/commodity-api/commodities", json=payload)
    assert created.status_code == 201, created.text
    relationship_id = created.json()["id"]
    assert client.get("/api/projects/commodity-api/commodities", params={"as_of": "2021-01-01"}).json()[0]["commodity"] == "lithium"
    assert client.get("/api/projects/commodity-api/commodities", params={"as_of": "2023-01-01"}).json() == []
    overlap = client.post("/api/projects/commodity-api/commodities", json={"commodity": "lithium", "effective_from": "2021-01-01", "effective_to": "2023-01-01"})
    assert overlap.status_code == 409
    assert client.put(f"/api/projects/commodity-api/commodities/{relationship_id}", json={"commodity": "lithium", "effective_from": "2020-01-01", "effective_to": "2023-01-01"}).status_code == 200
    asset_created = client.post(f"/api/projects/commodity-api/assets/{asset.id}/commodities", json={"commodity": "antimony"})
    assert asset_created.status_code == 201
    assert client.delete(f"/api/projects/commodity-api/commodities/{relationship_id}").status_code == 200


def test_ownership_operator_api_supports_history_and_conflict_checks(db_session):
    stock = Stock(code="REL", name="Relationship Co", commodity="gold")
    project = Project(project_key="relationship-api", name="Relationship Project")
    db_session.add_all([stock, project])
    db_session.commit()
    app = FastAPI()
    from app.api.routes import projects
    app.include_router(projects.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    payload = {"stock_id": stock.id, "relationship_type": "owner", "ownership_pct": 60, "operator_name": "Operator A", "effective_from": "2020-01-01", "effective_to": "2022-01-01"}
    created = client.post("/api/projects/relationship-api/relationships", json=payload)
    assert created.status_code == 201, created.text
    relationship_id = created.json()["id"]
    assert client.get("/api/projects/relationship-api/relationships", params={"as_of": "2021-01-01"}).json()[0]["operator_name"] == "Operator A"
    assert client.get("/api/projects/relationship-api/relationships", params={"as_of": "2023-01-01"}).json() == []
    overlap = client.post("/api/projects/relationship-api/relationships", json={**payload, "effective_from": "2021-01-01", "effective_to": "2023-01-01"})
    assert overlap.status_code == 409
    updated = client.put(f"/api/projects/relationship-api/relationships/{relationship_id}", json={**payload, "operator_name": "Operator B", "effective_to": "2023-01-01"})
    assert updated.status_code == 200
    assert updated.json()["operator_name"] == "Operator B"
    assert client.delete(f"/api/projects/relationship-api/relationships/{relationship_id}").status_code == 200


def test_asset_unit_materiality_gate_requires_reviewed_proposal(db_session):
    project = Project(project_key="materiality", name="Materiality Project")
    db_session.add(project)
    db_session.commit()
    app = FastAPI()
    from app.api.routes import projects
    app.include_router(projects.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    blocked = client.post("/api/projects/materiality/assets", json={"name": "Temporary Target", "unit_type": "target"})
    assert blocked.status_code == 409
    proposal = client.post("/api/projects/materiality/asset-proposals", json={"proposed_name": "Central Deposit", "proposed_type": "deposit", "rationale": "Repeated in official drilling results", "source_page": 1, "source_excerpt": "Central Deposit"})
    assert proposal.status_code == 201
    proposal_id = proposal.json()["id"]
    pending = client.get("/api/projects/materiality/asset-proposals", params={"status": "pending"})
    assert pending.status_code == 200 and len(pending.json()) == 1
    reviewed = client.put(f"/api/projects/materiality/asset-proposals/{proposal_id}", params={"status": "approved"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["asset_unit_id"] is not None
    assert client.put(f"/api/projects/materiality/asset-proposals/{proposal_id}", params={"status": "approved"}).status_code == 409
