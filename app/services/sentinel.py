"""Sentinel-2 imagery service for vegetation health analysis.

Downloads Sentinel-2 L2A bands from Copernicus Data Space Ecosystem (CDSE)
and computes vegetation indices (NDVI, NBR) for areas around climbing crags.

Requires a free CDSE account: https://dataspace.copernicus.eu
"""

import io
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

from app.config import settings

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
CDSE_DOWNLOAD_URL = "https://zipper.dataspace.copernicus.eu/odata/v1"

# Sentinel-2 bands at 60m resolution
# B04 = Red (665nm), B8A = NIR (865nm) → NDVI
# B8A = NIR (865nm), B12 = SWIR (2190nm) → NBR
# Note: B08 only exists at 10m; B8A is the NIR equivalent at 20m/60m
BANDS_NDVI = ["B04", "B8A"]
BANDS_NBR = ["B8A", "B12"]
BAND_RESOLUTION = "R60m"  # ~3.6MB per band, good enough for area monitoring


async def _get_cdse_token() -> str | None:
    """Get an access token from Copernicus Data Space."""
    if not settings.cdse_username or not settings.cdse_password:
        logger.warning("CDSE credentials not configured")
        return None

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            CDSE_TOKEN_URL,
            data={
                "client_id": "cdse-public",
                "username": settings.cdse_username,
                "password": settings.cdse_password,
                "grant_type": "password",
            },
        )
        if response.status_code != 200:
            logger.error("CDSE auth failed: %d %s", response.status_code, response.text[:200])
            return None

        return response.json().get("access_token")


def _bbox_from_center(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) bounding box."""
    km_per_deg_lat = 111.0
    km_per_deg_lng = 111.0 * math.cos(math.radians(lat))
    delta_lat = radius_km / km_per_deg_lat
    delta_lng = radius_km / km_per_deg_lng
    return (lng - delta_lng, lat - delta_lat, lng + delta_lng, lat + delta_lat)


async def search_sentinel2_products(
    lat: float,
    lng: float,
    radius_km: float,
    start_date: str,
    end_date: str,
    max_cloud: int = 30,
    limit: int = 5,
) -> list[dict]:
    """Search for Sentinel-2 L2A products covering an area.

    Returns list of product metadata dicts sorted by cloud cover.
    """
    west, south, east, north = _bbox_from_center(lat, lng, radius_km)
    bbox_wkt = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"

    # Note: cloud cover filter combined with polygon intersection causes OData
    # parse errors on CDSE, so we fetch more results and filter client-side.
    filter_str = (
        f"Collection/Name eq 'SENTINEL-2' "
        f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
        f"and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_wkt}') "
        f"and ContentDate/Start gt {start_date}T00:00:00.000Z "
        f"and ContentDate/Start lt {end_date}T23:59:59.999Z"
    )

    url = f"{CDSE_ODATA_URL}/Products"
    params = {
        "$filter": filter_str,
        "$orderby": "ContentDate/Start desc",
        "$top": limit * 3,  # fetch extra to allow for cloud filtering
        "$expand": "Attributes",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url, params=params)
        if response.status_code != 200:
            logger.error("CDSE search failed: %d %s", response.status_code, response.text[:300])
            return []

    products = response.json().get("value", [])
    logger.info("Found %d Sentinel-2 products (pre-filter)", len(products))

    results = []
    for p in products:
        attrs = {a["Name"]: a.get("Value") for a in p.get("Attributes", [])}
        cloud = attrs.get("cloudCover")
        if cloud is not None and cloud > max_cloud:
            continue
        results.append({
            "id": p["Id"],
            "name": p["Name"],
            "date": p["ContentDate"]["Start"],
            "cloud_cover": cloud,
            "size_mb": round(p.get("ContentLength", 0) / 1024 / 1024, 1),
            "footprint": p.get("GeoFootprint"),
        })

    # Sort by cloud cover ascending, return top N
    results.sort(key=lambda x: x["cloud_cover"] or 999)
    return results[:limit]


async def get_quicklook(product_id: str) -> bytes | None:
    """Fetch the quicklook JPEG thumbnail for a Sentinel-2 product.

    Uses the CDSE OData Assets endpoint (no auth required).
    """
    # First get the asset ID for this product's quicklook
    url = f"{CDSE_ODATA_URL}/Products({product_id})"
    params = {"$expand": "Assets"}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.error("Failed to get product assets: %d", resp.status_code)
            return None

        assets = resp.json().get("Assets", [])
        quicklook_asset = next((a for a in assets if a["Type"] == "QUICKLOOK"), None)
        if not quicklook_asset:
            return None

        # Download the quicklook image
        img_resp = await client.get(quicklook_asset["DownloadLink"], follow_redirects=True)
        if img_resp.status_code == 200:
            return img_resp.content
        return None


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute NDVI from Red (B04) and NIR (B08) bands.

    NDVI = (NIR - Red) / (NIR + Red)
    Range: -1 to 1. Healthy vegetation: 0.3-0.8
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir.astype(float) - red.astype(float)) / (nir.astype(float) + red.astype(float))
        ndvi = np.where(np.isfinite(ndvi), ndvi, 0)
    return ndvi


def compute_nbr(nir: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """Compute NBR from NIR (B08) and SWIR (B12) bands.

    NBR = (NIR - SWIR) / (NIR + SWIR)
    Used for burn severity mapping. Lower values indicate burned areas.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        nbr = (nir.astype(float) - swir.astype(float)) / (nir.astype(float) + swir.astype(float))
        nbr = np.where(np.isfinite(nbr), nbr, 0)
    return nbr


def compute_dnbr(pre_nbr: np.ndarray, post_nbr: np.ndarray) -> np.ndarray:
    """Compute delta NBR (burn severity).

    dNBR = pre_fire_NBR - post_fire_NBR
    Higher values = more severe burn.
    """
    return pre_nbr - post_nbr


def analyze_index(index_array: np.ndarray) -> dict:
    """Compute summary statistics for a vegetation index array."""
    valid = index_array[np.isfinite(index_array) & (index_array != 0)]
    if len(valid) == 0:
        return {"mean": 0, "min": 0, "max": 0, "std": 0, "pixel_count": 0}
    return {
        "mean": round(float(np.mean(valid)), 4),
        "min": round(float(np.min(valid)), 4),
        "max": round(float(np.max(valid)), 4),
        "std": round(float(np.std(valid)), 4),
        "pixel_count": int(len(valid)),
    }


async def _get_granule_name(product_id: str, safe_name: str) -> str | None:
    """Discover the granule directory name inside a Sentinel-2 product."""
    base = f"{CDSE_DOWNLOAD_URL}/Products({product_id})/Nodes({safe_name})/Nodes(GRANULE)/Nodes"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(base)
        if resp.status_code != 200:
            logger.error("Failed to list granules: %d", resp.status_code)
            return None
        nodes = resp.json().get("result", resp.json().get("value", []))
        if not nodes:
            return None
        return nodes[0]["Name"]


async def _download_band(
    product_id: str,
    safe_name: str,
    granule_name: str,
    band_name: str,
    token: str,
) -> bytes | None:
    """Download a single band file from CDSE at 60m resolution."""
    # Extract tile ID and datetime from product name
    # e.g. S2A_MSIL2A_20260326T171721_N0512_R112_T14RLP_20260327T034455.SAFE
    parts = safe_name.replace(".SAFE", "").split("_")
    tile_id = parts[5]  # T14RLP
    acq_datetime = parts[2]  # 20260326T171721

    band_file = f"{tile_id}_{acq_datetime}_{band_name}_{BAND_RESOLUTION[1:]}.jp2"
    node_path = f"{safe_name}/GRANULE/{granule_name}/IMG_DATA/{BAND_RESOLUTION}/{band_file}"
    nodes_path = "/".join(f"Nodes({p})" for p in node_path.split("/"))
    url = f"{CDSE_DOWNLOAD_URL}/Products({product_id})/{nodes_path}/$value"

    logger.info("Downloading %s...", band_file)
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            logger.error("Band download failed: %d %s", resp.status_code, resp.text[:200])
            return None
        logger.info("Downloaded %s (%.1f MB)", band_name, len(resp.content) / 1024 / 1024)
        return resp.content


def _read_band_cropped(
    band_bytes: bytes,
    west: float, south: float, east: float, north: float,
) -> np.ndarray:
    """Read a JP2 band and crop to a WGS84 bounding box."""
    with rasterio.open(io.BytesIO(band_bytes)) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        proj_west, proj_south = transformer.transform(west, south)
        proj_east, proj_north = transformer.transform(east, north)
        window = from_bounds(proj_west, proj_south, proj_east, proj_north, src.transform)
        return src.read(1, window=window).astype(float)


async def process_vegetation_index(
    crag_id: int,
    lat: float,
    lng: float,
    radius_km: float,
    target_date: str,
    index_type: str = "ndvi",
) -> dict | None:
    """Download Sentinel-2 bands and compute a vegetation index for a crag.

    index_type: "ndvi" or "nbr"
    Returns dict with index statistics or None if no imagery/credentials.
    """
    from datetime import timedelta

    token = await _get_cdse_token()
    if not token:
        return {
            "crag_id": crag_id,
            "status": "error",
            "note": "CDSE credentials not configured — add CDSE_USERNAME and CDSE_PASSWORD to .env",
        }

    target = datetime.strptime(target_date, "%Y-%m-%d")
    start = (target - timedelta(days=15)).strftime("%Y-%m-%d")
    end = (target + timedelta(days=15)).strftime("%Y-%m-%d")

    products = await search_sentinel2_products(
        lat, lng, radius_km, start, end, max_cloud=20, limit=1
    )
    if not products:
        logger.warning("No Sentinel-2 imagery for crag %s around %s", crag_id, target_date)
        return None

    product = products[0]
    logger.info("Best product: %s (cloud: %.1f%%)", product["name"], product["cloud_cover"] or 0)

    # Discover granule name
    granule_name = await _get_granule_name(product["id"], product["name"])
    if not granule_name:
        return {"crag_id": crag_id, "status": "error", "note": "Could not read product structure"}

    # Pick bands based on index type
    band_names = BANDS_NDVI if index_type == "ndvi" else BANDS_NBR

    # Download bands
    band_data = {}
    for bname in band_names:
        raw = await _download_band(product["id"], product["name"], granule_name, bname, token)
        if raw is None:
            return {"crag_id": crag_id, "status": "error", "note": f"Failed to download band {bname}"}
        band_data[bname] = raw

    # Crop to crag bounding box
    west, south, east, north = _bbox_from_center(lat, lng, radius_km)
    arrays = {}
    for bname, raw in band_data.items():
        arrays[bname] = _read_band_cropped(raw, west, south, east, north)

    # Compute index
    if index_type == "ndvi":
        index_array = compute_ndvi(arrays["B04"], arrays["B8A"])
    else:
        index_array = compute_nbr(arrays["B8A"], arrays["B12"])

    stats = analyze_index(index_array)

    return {
        "crag_id": crag_id,
        "product": product,
        "index_type": index_type,
        "status": "computed",
        "stats": stats,
    }
