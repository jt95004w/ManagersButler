from pathlib import Path

from venue_matcher.scraping.extract_jsonld import extract_events_from_jsonld


def test_jsonld_event_extraction_fixture():
    html = Path('tests/fixtures/jsonld_events.html').read_text()
    events = extract_events_from_jsonld(html, 'https://venue.example.com/calendar')
    assert len(events) == 2
    assert events[0].title == 'The Midnight Hour'
    assert events[0].artists == ['The Midnight Hour']
    assert events[0].url == 'https://venue.example.com/events/midnight-hour'
    assert events[1].title == 'Jazz Brunch'
