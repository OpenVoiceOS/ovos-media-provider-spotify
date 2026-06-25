"""Unit tests for SpotifyMediaProvider (Spotify Web API mocked)."""
from unittest.mock import MagicMock

from mediavocab import MediaType, Release, Signals

from ovos_media_provider_spotify import SpotifyMediaProvider


def _track(name, uri, artist="Some Artist", popularity=50):
    return {
        "name": name,
        "uri": uri,
        "popularity": popularity,
        "duration_ms": 200000,
        "artists": [{"name": artist}],
        "album": {"images": [{"url": "http://img/sm.jpg"},
                             {"url": "http://img/lg.jpg"}]},
    }


def _fake_client(tracks=None, artists=None, albums=None,
                 artist_top=None, album_tracks=None):
    """Build a SpotifyClient stub whose query_* methods return canned data."""
    client = MagicMock()
    client.query_song.return_value = (
        (90, {"data": {"tracks": {"items": tracks}}, "type": "track"})
        if tracks else (0.0, None))
    client.query_artist.return_value = (
        (80, {"data": {"artists": {"items": artists}}, "type": "artist"})
        if artists else (0.0, None))
    client.query_album.return_value = (
        (70, {"data": {"albums": {"items": albums}}, "type": "album"})
        if albums else (0.0, None))
    client.tracks_from_artist.return_value = artist_top or []
    client.tracks_from_album.return_value = album_tracks or []
    return client


def test_instantiation():
    prov = SpotifyMediaProvider()
    assert prov.name == "spotify"


def test_search_accepts_context_kwargs():
    """The provider accepts the pipeline's request-context kwargs."""
    prov = SpotifyMediaProvider()
    prov._client = _fake_client(tracks=[_track("Song A", "spotify:track:a")])
    results = prov.search(
        Signals(medium=MediaType.MUSIC, title="song a"),
        lang="en-us",
        supported_playback_types={"audio"},
        blocked_genres={"adult"},
        region="US",
        session_id="sess-1",
    )
    assert len(results) >= 1
    assert all(isinstance(r, Release) for r in results)


def test_search_track_returns_release_with_spotify_uri():
    prov = SpotifyMediaProvider()
    prov._client = _fake_client(
        tracks=[_track("Heavy Metal", "spotify:track:xyz", artist="Sabaton")])
    results = prov.search(Signals(medium=MediaType.MUSIC, title="heavy metal"))
    assert results
    r = results[0]
    assert isinstance(r, Release)
    assert r.uri == "spotify:track:xyz"
    assert r.work.title == "Heavy Metal"
    assert r.work.media_type == MediaType.MUSIC
    assert r.platform == "spotify"
    assert r.extra.get("artist") == "Sabaton"
    assert r.image == "http://img/lg.jpg"


def test_search_artist_expands_to_top_tracks():
    prov = SpotifyMediaProvider({"max_tracks": 2})
    artist = {"uri": "spotify:artist:1", "name": "Metallica",
              "images": [{"url": "http://a/sm.jpg"}]}
    top = [_track("One", "spotify:track:1"),
           _track("Two", "spotify:track:2"),
           _track("Three", "spotify:track:3")]
    prov._client = _fake_client(artists=[artist], artist_top=top)
    results = prov.search(Signals(medium=MediaType.MUSIC, title="metallica"))
    # capped at max_tracks
    assert len(results) == 2
    assert all(r.uri.startswith("spotify:track:") for r in results)


def test_search_combines_title_and_artist_signal():
    prov = SpotifyMediaProvider()
    prov._client = _fake_client(tracks=[_track("Song", "spotify:track:s")])
    prov.search(Signals(medium=MediaType.MUSIC, title="song", artist="band"))
    prov._client.query_song.assert_called_with("song band")


def test_search_empty_query_returns_empty():
    prov = SpotifyMediaProvider()
    prov._client = _fake_client()
    assert prov.search(Signals(medium=MediaType.MUSIC)) == []


def test_search_swallows_errors():
    prov = SpotifyMediaProvider()
    client = MagicMock()
    client.query_song.side_effect = RuntimeError("boom")
    client.query_artist.side_effect = RuntimeError("boom")
    client.query_album.side_effect = RuntimeError("boom")
    prov._client = client
    assert prov.search(Signals(medium=MediaType.MUSIC, title="x")) == []
