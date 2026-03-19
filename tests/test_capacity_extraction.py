from venue_matcher.capacity import infer_capacity
from venue_matcher.models import Venue


def test_capacity_regex_extraction_prefers_detected_numbers():
    venue = Venue(venue_id='v1', name='Test Room', website_url='https://example.com')
    html_pages = {'https://example.com/about': '<html><body><p>Our room has a capacity of 250 guests.</p></body></html>'}
    updated = infer_capacity(venue, html_pages, [])
    assert updated.capacity_estimate == 250
    assert updated.capacity_min == 250
    assert updated.capacity_confidence > 0.4
    assert updated.capacity_sources[0].method == 'regex'


def test_capacity_llm_fallback(monkeypatch):
    venue = Venue(venue_id='v2', name='Fallback Room', website_url='https://example.com')
    html_pages = {'https://example.com/about': '<html><body><p>Intimate listening room.</p></body></html>'}

    def fake_capacity_llm(_venue, _pages):
        return [180, 200], 190, 0.72

    monkeypatch.setattr('venue_matcher.capacity._capacity_from_llm', fake_capacity_llm)
    updated = infer_capacity(venue, html_pages, [])
    assert updated.capacity_estimate == 190
    assert updated.capacity_min == 180
    assert updated.capacity_max == 200
    assert updated.capacity_sources[0].method == 'llm'
