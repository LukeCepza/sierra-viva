# 🏔️ SierraViva

**Open platform that protects and connects the Monterrey climbing community.**

SierraViva combines satellite environmental monitoring of climbing areas with community tools and a local ecosystem directory — all focused on the Sierra Madre Oriental.

## Three Pillars

### 🛰️ Environmental Watch
Real-time fire alerts (NASA FIRMS), land use change detection, and conservation evidence for climbing areas in the Sierra Madre Oriental.

### 🧗 Community Hub
Find climbing partners, share conditions, organize carpools to crags, and post events.

### ☕ Local Ecosystem
Crags, indoor gyms, and specialty coffee spots on an interactive map.

## Climbing Areas

- **La Huasteca** — Sport climbing in Parque La Huasteca, Santa Catarina
- **Potrero Chico** — World-class multi-pitch sport climbing in Hidalgo, NL
- **El Salto** — Ciénega de González, Santiago, NL
- **Pico Norte** — Indoor climbing gym, Monterrey
- **Adamanta** — Indoor climbing gym, Monterrey

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/sierra-viva.git
cd sierra-viva

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your database URL and NASA API key

# Run database migrations
uv run alembic upgrade head

# Seed initial data
uv run python -m scripts.seed

# Start the server
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000 to see the map.

## API

All data is available as GeoJSON via the REST API:

- `GET /api/crags` — All climbing areas
- `GET /api/gyms` — Indoor climbing gyms
- `GET /api/cafes` — Specialty coffee spots
- `GET /api/alerts` — Active satellite alerts
- `GET /api/alerts/{crag_id}` — Alerts for a specific crag

API docs at http://localhost:8000/docs

## Tech Stack

- **Python** + **FastAPI** — API and backend
- **PostgreSQL** + **PostGIS** — Spatial database
- **NASA FIRMS** — Fire detection satellite data
- **Leaflet** — Interactive maps
- **SQLAlchemy** + **GeoAlchemy2** — ORM with spatial support

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- **Non-technical?** Use the web forms on the site to submit new locations or report conditions.
- **Developer?** Check the open issues and submit a PR.

## License

- Code: [MIT](LICENSE)
- Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

---

*SierraViva — La sierra está viva. Protejámosla juntos.*
