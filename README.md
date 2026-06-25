# ovos-media-provider-spotify

OVOS **MediaProvider** plugin for [Spotify](https://spotify.com). Replaces the
search half of the deprecated OCP search skill
[`ovos-skill-spotify`](https://github.com/OpenVoiceOS/ovos-skill-spotify).

Instead of broadcasting `ovos.common_play.query` over the bus and waiting for
skills to answer, the OCP pipeline loads MediaProvider plugins in-process, gates
them by routing, and calls `search()` directly. This plugin queries the Spotify
Web API (via [`spotipy`](https://spotipy.readthedocs.io)) for tracks, artists
and albums, then bridges each track into a
[`mediavocab.Release`](https://github.com/TigreGotico/mediavocab) carrying the
`spotify:` URI.

Playback is handled separately by the
[`ovos-media-plugin-spotify`](https://github.com/OpenVoiceOS/ovos-media-plugin-spotify)
backend — this repo only does **search/catalog**. Both share the `ocp_spotify`
OAuth credentials, so no extra configuration is required when Spotify is already
set up.

## Install

```bash
pip install ovos-media-provider-spotify
```

## Routing

| Axis | Value |
|------|-------|
| `media` | `MUSIC` |
| `playback_type` | `AUDIO` |
| `genre_filter` | *(none)* |

## Entry point

```toml
[project.entry-points."opm.media.provider"]
spotify = "ovos_media_provider_spotify:SpotifyMediaProvider"
```

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `max_tracks` | `25` | Maximum tracks returned per matched album/artist. |

## License

Apache-2.0
