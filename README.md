# ovos-media-provider-spotify

This is an OVOS **MediaProvider** plugin for [Spotify](https://spotify.com). It replaces the search half of the deprecated OCP search skill [`ovos-skill-spotify`](https://github.com/OpenVoiceOS/ovos-skill-spotify).

The OCP pipeline loads MediaProvider plugins in-process and calls `search()` directly, instead of broadcasting `ovos.common_play.query` over the bus and waiting for skills to answer. This plugin queries the Spotify Web API (through [`spotipy`](https://spotipy.readthedocs.io)) for tracks, artists, and albums, then converts each track into a [`mediavocab.Release`](https://github.com/TigreGotico/mediavocab) that carries the `spotify:` URI.

The [`ovos-media-plugin-spotify`](https://github.com/OpenVoiceOS/ovos-media-plugin-spotify) backend handles playback separately. This plugin only does search and catalog lookup. Both plugins share the `ocp_spotify` OAuth credentials, so no extra configuration is needed when Spotify is already set up.

## Install

```bash
pip install ovos-media-provider-spotify
```

The plugin registers itself through the `opm.media.provider` entry point, so OCP picks it up automatically after install.

```toml
[project.entry-points."opm.media.provider"]
spotify = "ovos_media_provider_spotify:SpotifyMediaProvider"
```

## Routing

There is no declarative routing table. OCP calls every installed provider's `search()`
method for each query; a provider that cannot serve the query (wrong media type, no
matching results, missing API credentials, …) just returns an empty list. This plugin
only ever returns music tracks, so it naturally contributes nothing to a query for
another media type.

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `max_tracks` | `25` | Maximum tracks returned per matched album/artist. |

## Related projects

- [`ovos-media-plugin-spotify`](https://github.com/OpenVoiceOS/ovos-media-plugin-spotify): the Spotify playback backend
- [`ovos-skill-spotify`](https://github.com/OpenVoiceOS/ovos-skill-spotify): the deprecated OCP search skill this plugin replaces
- [`mediavocab`](https://github.com/TigreGotico/mediavocab): the media metadata vocabulary this plugin returns results in

## License

Apache-2.0
