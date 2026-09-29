from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
PAYLOAD = {
    "story_prompt": "A brave fox explores an enchanted forest.",
    "character_name": "Lumi",
    "setting": "Enchanted forest",
    "tone": "funny",
    "art_style": "comic book",
}


def test_health_and_index():
    assert client.get("/health").json()["mock_ai"] is True
    r = client.get("/")
    assert r.status_code == 200 and "Create My Comic" in r.text
    assert client.get("/favicon.ico").status_code == 204


def test_form_generation_and_pdf():
    r = client.post("/generate-comic", data=PAYLOAD)
    assert r.status_code == 200 and "Download Your Comic as PDF" in r.text
    comic_id = r.text.split("/export-pdf/")[1].split('"')[0]
    assert client.post(f"/export-pdf/{comic_id}").status_code == 200
    pdf = client.get(f"/download/{comic_id}")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_json_api():
    r = client.post("/generate-comic/json", json=PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert len(data["panels"]) == get_settings().comic_panels
    assert "image_path" not in data["panels"][0]


def test_empty_story_is_a_friendly_400_not_a_500():
    r = client.post("/generate-comic", data={"story_prompt": ""})
    assert r.status_code == 400 and "story idea" in r.text


def test_unknown_comic_is_404_page():
    assert client.get("/comic/doesnotexist").status_code == 404
    assert client.get("/comic/../../etc/passwd").status_code == 404
