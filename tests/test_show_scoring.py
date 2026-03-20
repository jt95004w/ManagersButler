from datetime import datetime, timedelta, timezone

from venue_matcher.models import ArtistProfile, Event, ShowOpportunity, Venue, VenueProfile
from venue_matcher.show_scoring import (
    _bill_openness,
    _capacity_fit,
    _timing_score,
    rank_opportunities,
    score_show_opportunity,
)


def _make_venue(**overrides):
    defaults = dict(venue_id="test-venue", name="Test Venue", capacity_estimate=500, capacity_confidence=0.8)
    defaults.update(overrides)
    return Venue(**defaults)


def _make_artist(**overrides):
    defaults = dict(name="Test Artist", target_capacity=400)
    defaults.update(overrides)
    return ArtistProfile(**defaults)


def _make_event(weeks_out=4, artists=None, title="Some Headliner", description=None, **overrides):
    dt = datetime.now(timezone.utc) + timedelta(weeks=weeks_out)
    defaults = dict(venue_id="test-venue", source_url="https://example.com", title=title, start_dt=dt, artists=artists or [], description=description)
    defaults.update(overrides)
    return Event(**defaults)


class TestBillOpenness:
    def test_single_headliner_high(self):
        event = _make_event(artists=["Headliner"])
        assert _bill_openness(event) == 0.85

    def test_no_artists_moderate(self):
        event = _make_event(artists=[])
        assert _bill_openness(event) == 0.7

    def test_full_bill_low(self):
        event = _make_event(artists=["A", "B", "C", "D"])
        assert _bill_openness(event) == 0.15

    def test_tba_boosts_score(self):
        event = _make_event(artists=["Headliner"], title="Headliner w/ TBA")
        score = _bill_openness(event)
        assert score > 0.85

    def test_sold_out_kills_score(self):
        event = _make_event(artists=["Headliner"], description="This show is SOLD OUT")
        score = _bill_openness(event)
        assert score < 0.5

    def test_festival_penalized(self):
        event = _make_event(artists=["A"], title="Summer Festival Day 1")
        score = _bill_openness(event)
        assert score < 0.85


class TestTimingScore:
    def test_sweet_spot(self):
        now = datetime.now(timezone.utc)
        event_dt = now + timedelta(weeks=5)
        assert _timing_score(event_dt, now) == 1.0

    def test_too_soon(self):
        now = datetime.now(timezone.utc)
        event_dt = now + timedelta(days=3)
        assert _timing_score(event_dt, now) == 0.15

    def test_past_is_zero(self):
        now = datetime.now(timezone.utc)
        event_dt = now - timedelta(days=1)
        assert _timing_score(event_dt, now) == 0.0

    def test_far_out(self):
        now = datetime.now(timezone.utc)
        event_dt = now + timedelta(weeks=20)
        assert _timing_score(event_dt, now) == 0.3

    def test_available_date_boost(self):
        now = datetime.now(timezone.utc)
        event_dt = now + timedelta(weeks=14)  # Outside sweet spot so boost is visible
        date_str = event_dt.strftime("%Y-%m-%d")
        boosted = _timing_score(event_dt, now, [date_str])
        normal = _timing_score(event_dt, now)
        assert boosted > normal


class TestCapacityFit:
    def test_perfect_match(self):
        score = _capacity_fit(500, 500, 0.9)
        assert score > 0.8

    def test_too_big(self):
        score = _capacity_fit(2000, 200, 0.9)
        assert score < 0.5

    def test_no_data_moderate(self):
        score = _capacity_fit(None, 500, 0.5)
        assert 0.2 < score < 0.6


class TestScoreShowOpportunity:
    def test_past_event_returns_none(self):
        venue = _make_venue()
        artist = _make_artist()
        event = _make_event(weeks_out=-1)
        assert score_show_opportunity(event, venue, artist) is None

    def test_good_opportunity_scores_high(self):
        venue = _make_venue(capacity_estimate=500, capacity_confidence=0.9)
        artist = _make_artist(target_capacity=450)
        event = _make_event(weeks_out=4, artists=["Headliner"])
        opp = score_show_opportunity(event, venue, artist)
        assert opp is not None
        assert opp.opportunity_score > 0.6
        assert opp.headliner == "Headliner"

    def test_capacity_dominates(self):
        artist = _make_artist(target_capacity=400)
        good_cap = _make_venue(venue_id="good", capacity_estimate=400, capacity_confidence=0.9)
        bad_cap = _make_venue(venue_id="bad", capacity_estimate=5000, capacity_confidence=0.9)
        event_good = _make_event(weeks_out=4, artists=["A"])
        event_good.venue_id = "good"
        event_bad = _make_event(weeks_out=4, artists=["A"])
        event_bad.venue_id = "bad"
        opp_good = score_show_opportunity(event_good, good_cap, artist)
        opp_bad = score_show_opportunity(event_bad, bad_cap, artist)
        assert opp_good.opportunity_score > opp_bad.opportunity_score

    def test_no_capacity_still_produces_result(self):
        venue = _make_venue(capacity_estimate=None, capacity_confidence=0.0)
        artist = _make_artist(target_capacity=400)
        event = _make_event(weeks_out=4, artists=["Headliner"])
        opp = score_show_opportunity(event, venue, artist)
        assert opp is not None
        assert opp.opportunity_score > 0.0

    def test_with_venue_profile(self):
        venue = _make_venue()
        artist = _make_artist()
        profile = VenueProfile(venue_id="test-venue", support_friendliness=0.9)
        event = _make_event(weeks_out=4, artists=["Headliner"])
        opp = score_show_opportunity(event, venue, artist, profile)
        assert opp is not None
        assert opp.venue_support_friendliness == 0.9


class TestRankOpportunities:
    def test_sorts_by_score_desc(self):
        opps = [
            ShowOpportunity(event_id="a", venue_id="v", venue_name="V", event_title="Low", opportunity_score=0.3),
            ShowOpportunity(event_id="b", venue_id="v", venue_name="V", event_title="High", opportunity_score=0.9),
            ShowOpportunity(event_id="c", venue_id="v", venue_name="V", event_title="Mid", opportunity_score=0.6),
        ]
        ranked = rank_opportunities(opps)
        assert [o.event_title for o in ranked] == ["High", "Mid", "Low"]
