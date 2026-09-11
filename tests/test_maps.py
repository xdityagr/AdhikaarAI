"""
Static map rendering tests.

No network: tile fetches are mocked. A test suite that depends on
tile.openstreetmap.org being reachable is a flaky test suite, for the same
reason a demo that depends on it is a flaky demo.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.main import MEDIA_NAME_RE
from src.maps import (
    MapPin,
    choose_zoom,
    deg2num,
    maps_link,
    num2deg,
    render_map,
)

DELHI = (28.6139, 77.2090)
GURUGRAM = (28.4595, 77.0266)


def _blank_tile_bytes() -> bytes:
    """A valid 256x256 PNG, standing in for an OSM tile."""
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (200, 210, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Slippy-tile maths
# ---------------------------------------------------------------------------

class TestTileMath:
    def test_deg2num_num2deg_round_trip(self):
        for zoom in (3, 8, 13, 16):
            x, y = deg2num(*DELHI, zoom)
            lat, lon = num2deg(x, y, zoom)
            assert lat == pytest.approx(DELHI[0], abs=1e-6)
            assert lon == pytest.approx(DELHI[1], abs=1e-6)

    def test_higher_zoom_gives_more_tiles(self):
        x8, _ = deg2num(*DELHI, 8)
        x12, _ = deg2num(*DELHI, 12)
        assert x12 > x8


class TestZoomSelection:
    def test_single_pin_uses_a_close_zoom(self):
        assert choose_zoom([MapPin(*DELHI)], 640, 480) == 13

    def test_widely_spread_pins_zoom_out_further_than_close_ones(self):
        close = choose_zoom([MapPin(*DELHI), MapPin(28.62, 77.22)], 640, 480)
        wide = choose_zoom([MapPin(*DELHI), MapPin(19.07, 72.87)], 640, 480)
        assert wide < close, "Delhi-Mumbai must zoom out further than two Delhi points"

    def test_all_pins_fit_in_the_image(self):
        pins = [MapPin(*DELHI), MapPin(*GURUGRAM)]
        zoom = choose_zoom(pins, 640, 480)
        xs, ys = zip(*(deg2num(p.latitude, p.longitude, zoom) for p in pins))
        assert (max(xs) - min(xs)) * 256 < 640
        assert (max(ys) - min(ys)) * 256 < 480


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class TestRendering:
    def test_renders_a_png_of_the_requested_size(self, tmp_path):
        from PIL import Image
        with patch("src.maps._fetch_tile", new_callable=AsyncMock) as fetch:
            fetch.return_value = _blank_tile_bytes()
            path = asyncio.run(render_map(
                [MapPin(*DELHI, "1"), MapPin(*GURUGRAM, "2")],
                output_dir=tmp_path, cache_dir=None, width=640, height=480,
            ))
        assert path.exists()
        assert Image.open(path).size == (640, 480)

    def test_filename_matches_the_media_route_pattern(self, tmp_path):
        """Rendered maps are served on a route with a strict filename regex."""
        with patch("src.maps._fetch_tile", new_callable=AsyncMock) as fetch:
            fetch.return_value = _blank_tile_bytes()
            path = asyncio.run(render_map([MapPin(*DELHI)], output_dir=tmp_path, cache_dir=None))
        assert MEDIA_NAME_RE.match(path.name), f"{path.name} would 404 on /media/"

    def test_filenames_are_unguessable(self, tmp_path):
        """A map URL is public and encodes an approximate location."""
        with patch("src.maps._fetch_tile", new_callable=AsyncMock) as fetch:
            fetch.return_value = _blank_tile_bytes()
            names = {
                asyncio.run(render_map([MapPin(*DELHI)], output_dir=tmp_path, cache_dir=None)).name
                for _ in range(3)
            }
        assert len(names) == 3

    def test_still_produces_a_map_when_every_tile_fails(self, tmp_path):
        """Degrade, don't fail — pins on a plain background beat nothing at all."""
        from PIL import Image
        with patch("src.maps._fetch_tile", new_callable=AsyncMock) as fetch:
            fetch.return_value = None
            path = asyncio.run(render_map(
                [MapPin(*DELHI, "1")], output_dir=tmp_path, cache_dir=None,
            ))
        assert path.exists()
        assert Image.open(path).size == (640, 480)

    def test_empty_pin_list_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="at least one pin"):
            asyncio.run(render_map([], output_dir=tmp_path))


# ---------------------------------------------------------------------------
# Tile cache — what makes the demo offline-proof
# ---------------------------------------------------------------------------

class TestTileCache:
    def test_tiles_are_written_to_the_cache(self, tmp_path):
        cache = tmp_path / "tiles"
        with patch("src.maps._fetch_tile", wraps=None) as _:
            pass
        # Exercise the real _fetch_tile cache path with a stubbed HTTP client.
        from src.maps import _fetch_tile

        class _Response:
            content = _blank_tile_bytes()
            def raise_for_status(self): return None

        class _Client:
            async def get(self, url): return _Response()

        payload = asyncio.run(_fetch_tile(_Client(), 13, 100, 200, cache))
        assert payload is not None
        assert (cache / "13" / "100" / "200.png").exists()

    def test_cached_tile_is_served_without_a_request(self, tmp_path):
        from src.maps import _fetch_tile
        cache = tmp_path / "tiles"
        target = cache / "13" / "100" / "200.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"cached-bytes")

        class _ExplodingClient:
            async def get(self, url):
                raise AssertionError("cache miss — should not have hit the network")

        assert asyncio.run(_fetch_tile(_ExplodingClient(), 13, 100, 200, cache)) == b"cached-bytes"


# ---------------------------------------------------------------------------
# Location fallback
# ---------------------------------------------------------------------------

class TestMapsLink:
    """The always-works fallback, since a native location pin needs an approved
    Twilio Content Template and approval turnaround isn't ours to control."""

    def test_contains_the_coordinates(self):
        link = maps_link(28.6139, 77.2090)
        assert "28.6139" in link and "77.209" in link
        assert link.startswith("https://")
