"""Spotify MediaProvider plugin for OVOS.

Wraps the Spotify Web API search endpoints and exposes Spotify's music catalog
to the OCP pipeline as a
:class:`~ovos_plugin_manager.templates.media_provider.MediaProvider`. Replaces
the search half of the deprecated OCP search skill ``ovos-skill-spotify``.

The skill ran four parallel ``@ocp_search`` handlers (artist / album / track /
user-playlist), each querying Spotify and yielding ``MediaEntry``/``Playlist``
objects keyed by ``spotify:`` URIs for the companion
``ovos-media-plugin-spotify`` backend to play. This provider ports that search
behaviour: it queries the same endpoints via :class:`SpotifyClient` and bridges
each track into one :class:`mediavocab.Release` carrying the ``spotify:`` URI
(one Release per playable track — a track is the playable unit; albums/artists
expand to their tracks).

Note: a Spotify *playback backend* (``ovos-media-plugin-spotify``) already
exists separately; this is the *search/catalog* provider. Both share the
``ocp_spotify`` OAuth credentials, so no extra configuration is needed when
Spotify is already set up.
"""
from typing import ClassVar, Dict, List, Optional, Set

from ovos_utils.log import LOG

from mediavocab import MediaType, Release, Signals, Work

from ovos_plugin_manager.templates.media_provider import MediaProvider

from ovos_media_provider_spotify.spotify_client import SpotifyClient
from ovos_media_provider_spotify.version import __version__  # noqa: F401


class SpotifyMediaProvider(MediaProvider):
    """Search the Spotify catalog and return playable music releases."""

    name: ClassVar[str] = "spotify"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        # max tracks to return per matched album/artist/playlist
        self.max_tracks: int = int(self.config.get("max_tracks", 25))
        self._client: Optional[SpotifyClient] = None

    @property
    def client(self) -> SpotifyClient:
        if self._client is None:
            self._client = SpotifyClient()
        return self._client

    @staticmethod
    def _track_to_release(track: Dict, score: int,
                          image: str = "") -> Optional[Release]:
        """Bridge a Spotify track dict to a :class:`mediavocab.Release`.

        The Spotify ``track:`` URI is the playable handle the
        ``ovos-media-plugin-spotify`` backend consumes.
        """
        uri = track.get("uri")
        if not uri:
            return None
        artists = track.get("artists") or []
        artist = artists[0]["name"] if artists else None
        work = Work(title=track.get("name") or "",
                    media_type=MediaType.MUSIC)
        runtime = track.get("duration_ms")
        # mediavocab match_confidence is a 0.0-1.0 ratio; the ported Spotify
        # client scores 0-100, so normalise.
        return Release(
            work=work,
            uri=uri,
            platform="spotify",
            image=image,
            match_confidence=min(100, score) / 100.0,
            extra={k: v for k, v in {
                "artist": artist,
                "runtime_ms": runtime,
            }.items() if v is not None},
        )

    @staticmethod
    def _track_image(track: Dict) -> str:
        images = (track.get("album") or {}).get("images") or []
        return images[-1]["url"] if images else ""

    def _search_tracks(self, query: str) -> List[Release]:
        score, data = self.client.query_song(query)
        if not data:
            return []
        out = []
        for track in data["data"]["tracks"]["items"]:
            rel = self._track_to_release(track, score,
                                         self._track_image(track))
            if rel:
                out.append(rel)
        return out

    def _search_artists(self, query: str) -> List[Release]:
        score, data = self.client.query_artist(query)
        if not data:
            return []
        out = []
        for artist in data["data"]["artists"]["items"]:
            image = artist["images"][-1]["url"] if artist.get("images") else ""
            for t in self.client.tracks_from_artist(artist["uri"]):
                rel = self._track_to_release(t, score, image)
                if rel:
                    out.append(rel)
                if len(out) >= self.max_tracks:
                    break
        return out

    def _search_albums(self, query: str) -> List[Release]:
        score, data = self.client.query_album(query)
        if not data:
            return []
        out = []
        for album in data["data"]["albums"]["items"]:
            image = album["images"][-1]["url"] if album.get("images") else ""
            for t in self.client.tracks_from_album(album["uri"]):
                rel = self._track_to_release(t, score, image)
                if rel:
                    out.append(rel)
                if len(out) >= self.max_tracks:
                    break
        return out

    def search(self, signals: Signals, lang: str = "en-us", *,
               supported_playback_types: Optional[Set[str]] = None,
               blocked_genres: Optional[Set[str]] = None,
               region: Optional[str] = None,
               session_id: Optional[str] = None) -> List[Release]:
        """Query Spotify (track, then artist, then album) for
        ``signals.title``/``signals.artist`` and return one
        :class:`Release` per matching track.

        Returns ``[]`` on any failure (no credentials, network error, no
        results) — mirroring the deprecated skill's "stay silent when Spotify
        is unavailable" behaviour.
        """
        query = " ".join(p for p in (signals.title, signals.artist) if p).strip()
        if not query:
            return []

        releases: List[Release] = []
        for fn in (self._search_tracks, self._search_artists,
                   self._search_albums):
            try:
                releases.extend(fn(query))
            except Exception:
                LOG.exception(f"Spotify search step failed: {fn.__name__}")
        return releases
