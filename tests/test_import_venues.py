import tempfile
from pathlib import Path

import yaml

from venue_matcher.db import Database
from venue_matcher.import_venues import import_from_yaml


def _make_db():
    tmp = tempfile.mktemp(suffix=".db")
    return Database(tmp)


class TestImportFromYaml:
    def test_import_old_format(self, tmp_path):
        yaml_data = [
            {
                "name": "9:30 Club",
                "url": "https://www.930.com/calendar",
                "list_selector": "div.event-item",
                "title_selector": ".event-name",
                "date_selector": "time",
                "artist_selector": ".supporting-acts",
                "detail_url_selector": "a",
                "timezone": "America/New_York",
                "location": "Washington, DC",
            }
        ]
        yaml_file = tmp_path / "venues.yaml"
        yaml_file.write_text(yaml.safe_dump(yaml_data))

        db = _make_db()
        venues = import_from_yaml(yaml_file, db)

        assert len(venues) == 1
        v = venues[0]
        assert v.name == "9:30 Club"
        assert v.venue_id == "930-club"
        assert v.calendar_urls == ["https://www.930.com/calendar"]
        assert v.city == "Washington"
        assert v.region == "DC"
        assert v.timezone == "America/New_York"
        assert v.css_rules["list_selector"] == "div.event-item"
        assert v.css_rules["title_selector"] == ".event-name"

    def test_import_with_capacity(self, tmp_path):
        yaml_data = [
            {
                "name": "Small Club",
                "url": "https://smallclub.com/shows",
                "list_selector": ".event",
                "title_selector": "h2",
                "date_selector": "time",
                "capacity_estimate": 200,
                "capacity_min": 150,
                "capacity_max": 250,
                "location": "Austin, TX",
            }
        ]
        yaml_file = tmp_path / "venues.yaml"
        yaml_file.write_text(yaml.safe_dump(yaml_data))

        db = _make_db()
        venues = import_from_yaml(yaml_file, db)

        v = venues[0]
        assert v.capacity_estimate == 200
        assert v.capacity_min == 150
        assert v.capacity_max == 250

    def test_css_rules_persisted_in_db(self, tmp_path):
        yaml_data = [
            {
                "name": "Test Venue",
                "url": "https://test.com/events",
                "list_selector": ".show",
                "title_selector": ".title",
                "date_selector": ".date",
            }
        ]
        yaml_file = tmp_path / "venues.yaml"
        yaml_file.write_text(yaml.safe_dump(yaml_data))

        db = _make_db()
        import_from_yaml(yaml_file, db)

        loaded = db.load_venue("test-venue")
        assert loaded is not None
        assert loaded.css_rules["list_selector"] == ".show"
        assert loaded.css_rules["title_selector"] == ".title"

    def test_import_extended_format(self, tmp_path):
        yaml_data = [
            {
                "name": "Extended Venue",
                "venue_id": "custom-id",
                "calendar_urls": ["https://ext.com/calendar", "https://ext.com/shows"],
                "website_url": "https://ext.com",
                "city": "Nashville",
                "region": "TN",
                "timezone": "America/Chicago",
                "genres_hint": ["country", "americana"],
                "list_selector": ".event",
                "title_selector": "h3",
                "date_selector": "time",
            }
        ]
        yaml_file = tmp_path / "venues.yaml"
        yaml_file.write_text(yaml.safe_dump(yaml_data))

        db = _make_db()
        venues = import_from_yaml(yaml_file, db)

        v = venues[0]
        assert v.venue_id == "custom-id"
        assert v.calendar_urls == ["https://ext.com/calendar", "https://ext.com/shows"]
        assert v.city == "Nashville"
        assert v.genres_hint == ["country", "americana"]
