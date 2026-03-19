from venue_matcher.models import ArtistProfile, Venue, VenueProfile
from venue_matcher.scoring import score_venue_for_artist


def test_capacity_fit_is_one_at_target_capacity():
    venue = Venue(venue_id='v1', name='Room', capacity_estimate=300, capacity_confidence=1.0)
    profile = VenueProfile(venue_id='v1', inferred_genres=['indie'], audience_traits=['local'], booking_tier='emerging', typical_bill_style='showcase', support_friendliness=0.8, confidence=0.9, reasoning_summary='ok', evidence=['https://example.com'])
    artist = ArtistProfile(name='Band', target_genres=['indie'], audience_traits=['local'], target_capacity=300)
    score = score_venue_for_artist(venue, profile, artist)
    assert score.capacity_fit == 1.0


def test_capacity_fit_drops_when_double_or_half():
    profile = VenueProfile(venue_id='v1', inferred_genres=['indie'], audience_traits=['local'], booking_tier='emerging', typical_bill_style='showcase', support_friendliness=0.8, confidence=0.9, reasoning_summary='ok', evidence=['https://example.com'])
    artist = ArtistProfile(name='Band', target_genres=['indie'], audience_traits=['local'], target_capacity=300)
    hi = score_venue_for_artist(Venue(venue_id='hi', name='Big', capacity_estimate=600, capacity_confidence=1.0), profile.model_copy(update={'venue_id': 'hi'}), artist)
    lo = score_venue_for_artist(Venue(venue_id='lo', name='Small', capacity_estimate=150, capacity_confidence=1.0), profile.model_copy(update={'venue_id': 'lo'}), artist)
    assert hi.capacity_fit < 1.0
    assert lo.capacity_fit < 1.0
    assert hi.capacity_fit == lo.capacity_fit


def test_missing_capacity_penalizes_fit_and_quality():
    venue = Venue(venue_id='v1', name='Unknown', capacity_confidence=0.0)
    profile = VenueProfile(venue_id='v1', inferred_genres=['indie'], audience_traits=['local'], booking_tier='emerging', typical_bill_style='showcase', support_friendliness=0.8, confidence=0.9, reasoning_summary='ok', evidence=['https://example.com'])
    artist = ArtistProfile(name='Band', target_genres=['indie'], audience_traits=['local'], target_capacity=300)
    score = score_venue_for_artist(venue, profile, artist)
    assert score.capacity_fit < 0.7
    assert score.data_quality < 0.7
