"""Spotify Web API search client.

Ported from the deprecated ``ovos-skill-spotify`` (its ``spotify.py``). Keeps
only the read/search half of the original skill client — the parts needed to
turn a query string into Spotify catalog results. Playback (devices, transfer,
spotifyd) lives in the separate ``ovos-media-plugin-spotify`` backend, not here.

Credentials are resolved through the OVOS OAuth token store (the same
``ocp_spotify`` application/token the playback backend registers), so this
provider needs no extra configuration when Spotify is already set up.
"""
import os
import re
import time
from typing import Dict, Tuple

import requests
from ovos_utils.log import LOG
from ovos_utils.oauth import (OAuthApplicationDatabase, OAuthTokenDatabase,
                              get_oauth_token)
from ovos_utils.parse import MatchStrategy, fuzzy_match, match_one
from ovos_utils.xdg_utils import xdg_config_home

OAUTH_TOKEN_ID = "ocp_spotify"


class SpotifyNotAuthorizedError(Exception):
    """Raised when no usable Spotify credentials can be resolved."""


class OVOSSpotifyCredentials:
    """OAuth credentials resolved from the OVOS token store.

    Wraps :class:`spotipy.oauth2.SpotifyAuthBase` lazily so importing this
    module does not hard-require spotipy at collection time.
    """

    def __new__(cls):
        from spotipy.oauth2 import SpotifyAuthBase

        class _Creds(SpotifyAuthBase):
            def __init__(self):
                super().__init__(requests.Session())

            @staticmethod
            def is_token_expired(token_info: dict) -> bool:
                return time.time() >= token_info["expires_at"]

            @staticmethod
            def get_access_token() -> str:
                t = get_oauth_token(OAUTH_TOKEN_ID, auto_refresh=True)
                if _Creds.is_token_expired(t):
                    LOG.warning("SPOTIFY TOKEN EXPIRED")
                    t = _Creds.refresh_oauth()
                return t["access_token"]

            @staticmethod
            def refresh_oauth() -> dict:
                from spotipy import SpotifyOAuth
                auth_dir = os.environ.get(
                    "SPOTIFY_SKILL_CREDS_DIR", f"{xdg_config_home()}/spotipy")
                scope = ("user-library-read streaming playlist-read-private "
                         "user-top-read user-read-playback-state")
                with OAuthApplicationDatabase() as db:
                    app = db.get_application(OAUTH_TOKEN_ID)
                am = SpotifyOAuth(scope=scope,
                                  client_id=app["client_id"],
                                  client_secret=app["client_secret"],
                                  redirect_uri="https://localhost:8888",
                                  cache_path=f"{auth_dir}/token",
                                  open_browser=False)
                with OAuthTokenDatabase() as db:
                    token_info = db.get_token(OAUTH_TOKEN_ID)
                    token_info = am.refresh_access_token(
                        token_info["refresh_token"])
                    db.add_token(OAUTH_TOKEN_ID, token_info)
                    LOG.info(f"{OAUTH_TOKEN_ID} oauth token refreshed")
                return token_info

        return _Creds()


class SpotifyClient:
    """Thin search wrapper over the Spotify Web API (via spotipy)."""

    NOTHING_FOUND = (0.0, None)

    def __init__(self):
        self._spotify = None

    @property
    def spotify(self):
        if self._spotify is None:
            self.load_credentials()
        return self._spotify

    def load_credentials(self) -> None:
        """Connect to Spotify using OVOS-managed OAuth credentials."""
        try:
            import spotipy
            self._spotify = spotipy.Spotify(
                auth_manager=OVOSSpotifyCredentials())
        except Exception:
            LOG.error("Couldn't fetch spotify credentials")
            self._spotify = None

    @staticmethod
    def best_confidence(title: str, query: str) -> int:
        """Confidence (0-100) of ``title`` vs ``query``, robust to titles that
        carry trailing ``(Remastered ...)`` / ``- ...`` cruft."""
        best = title.lower()
        best_stripped = re.sub(r"(\(.+\)|-.+)$", "", best).strip()
        return int(max(
            fuzzy_match(best, query,
                        strategy=MatchStrategy.DAMERAU_LEVENSHTEIN_SIMILARITY),
            fuzzy_match(best_stripped, query,
                        strategy=MatchStrategy.DAMERAU_LEVENSHTEIN_SIMILARITY),
        ) * 100)

    def query_artist(self, artist: str) -> Tuple[int, Dict]:
        """Find an artist; returns (confidence, payload) or NOTHING_FOUND."""
        data = self.spotify.search(artist, type="artist")
        if data and data["artists"]["items"]:
            best = data["artists"]["items"][0]["name"]
            confidence = min(100, fuzzy_match(
                best, artist.lower(),
                strategy=MatchStrategy.DAMERAU_LEVENSHTEIN_SIMILARITY) * 100)
            return int(confidence), {"data": data, "type": "artist"}
        return SpotifyClient.NOTHING_FOUND

    def query_album(self, album: str) -> Tuple[int, Dict]:
        """Find an album, honouring an optional ``<album> by <artist>``."""
        by_word = " by "
        bonus = 0
        if len(album.split(by_word)) > 1:
            album, artist = album.split(by_word)
            album_search = f"*{album}* artist:{artist}"
            bonus = 10
        else:
            album_search = album
        data = self.spotify.search(album_search, type="album")
        if data and data["albums"]["items"]:
            best = data["albums"]["items"][0]["name"].lower()
            confidence = min(self.best_confidence(best, album) + bonus, 100)
            return confidence, {"data": data, "type": "album"}
        return SpotifyClient.NOTHING_FOUND

    def query_song(self, song: str) -> Tuple[int, Dict]:
        """Find the best matching track, honouring ``<song> by <artist>``."""
        by_word = " by "
        if len(song.split(by_word)) > 1:
            song, artist = song.split(by_word)
            song_search = f"*{song}* artist:{artist}"
        else:
            song_search = song
        data = self.spotify.search(song_search, type="track")
        if data and data["tracks"]["items"]:
            tracks = [(self.best_confidence(d["name"], song), d)
                      for d in data["tracks"]["items"]]
            tracks.sort(key=lambda x: x[0], reverse=True)
            tracks = [t for t in tracks if t[0] > tracks[0][0] - 0.1]
            tracks.sort(key=lambda x: x[1]["popularity"])
            bonus = int(fuzzy_match(
                song_search, tracks[-1][1]["artists"][0]["name"],
                strategy=MatchStrategy.TOKEN_SET_RATIO) * 100)
            data["tracks"]["items"] = [tracks[-1][1]]
            return (min(100, tracks[-1][0] + bonus),
                    {"data": data, "type": "track"})
        return SpotifyClient.NOTHING_FOUND

    def tracks_from_artist(self, artist_id):
        return list(self.spotify.artist_top_tracks(artist_id)["tracks"])

    def tracks_from_album(self, album_id):
        return list(self.spotify.album_tracks(album_id)["items"])
