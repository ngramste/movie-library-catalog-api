# Movie Library

A self-hosted movie library that scans a local collection of movie files, enriches them with metadata from the [OMDb API](https://www.omdbapi.com/), stores everything in a MySQL database, and exposes a search API and responsive web UI — all running via Docker Compose.

---

## How it works

On startup the Python application:

1. Scans the configured movies directory for folders matching the pattern `Movie Title (Year)` or `Movie Title (Year) {edition-name}`.
2. Reads embedded metadata (title, IMDb ID, plot, etc.) from each video file using `ffprobe`.
3. For any movie missing IMDb data, queries the OMDb API to fetch and write it back to the file.
4. Populates a MySQL database with title, year, edition, filetype, file metadata, and a list of any special-feature subfolders.
5. Downloads poster images from IMDb into a local cache served by Nginx.
6. Starts a Flask REST API for querying the library.

---

## Web UI

The web interface is served at `http://<host>/` and provides a searchable, card-based view of your movie collection.

### Features

- **Live search** — results update as you type.
- **Movie cards** showing:
  - Poster image (cached locally, falls back to a placeholder)
  - Quality badge (**UHD**, **Blu-ray**, or **DVD**) derived from the video resolution
  - Title and edition
  - Year, director, actors, and genres
  - Plot summary
  - Collapsible **Special Features** panel listing available bonus content subfolders
- **Dark/light mode** support via `prefers-color-scheme`.
- **Responsive layout** — optimised for both desktop and mobile.

### Search fields

| Field | Behaviour |
|-------|-----------|
| Title | Partial, case & accent insensitive match against the movie title |
| Year  | Exact 4-digit year match |
| Plot  | Partial, case & accent insensitive match within the plot text |

---

## API

The REST API is available at `http://<host>/api/`.

### `GET /api/movies`

Returns a JSON array of movie objects. All parameters are optional and can be combined.

| Parameter | Type   | Description |
|-----------|--------|-------------|
| `title`   | string | Partial, case & accent insensitive match against the movie title |
| `year`    | number | Exact year match |
| `imdb_id` | string | Exact IMDb ID match (e.g. `tt0816692`) |
| `edition` | string | Partial, case insensitive match against the edition string |
| `plot`    | string | Partial, case & accent insensitive match within the plot |
| `actor`   | string | Partial, case & accent insensitive match within the actors list |
| `director`| string | Partial, case & accent insensitive match against the director name |
| `genre`   | string | Partial, case & accent insensitive match within genres |
| `filetype`| string | Exact, case insensitive match against the file extension (e.g. `mkv`) |
| `has_sf`  | boolean | `true` returns only movies with special features; `false` returns movies without |
| `metadata`| string | Partial match against the raw metadata JSON blob |
| `help`    | any    | Returns a description of all available query parameters |

#### Example requests

```
GET /api/movies?title=terminator
GET /api/movies?actor=keanu&genre=action
GET /api/movies?year=1994&has_sf=true
GET /api/movies?imdb_id=tt0110912
GET /api/movies?help
```

#### Example response

```json
[
  {
    "id": 42,
    "imdb_id": "tt0816692",
    "title": "Interstellar",
    "year": 2014,
    "edition": null,
    "filetype": "mkv",
    "metadata": {
      "format": {
        "tags": {
          "TITLE": "Interstellar",
          "PLOT": "A team of explorers travel through a wormhole...",
          "POSTER": "https://...",
          ...
        }
      },
      "streams": [{ "width": 1920, "height": 1080 }]
    },
    "special_features": {
      "Behind the Scenes": ["featurette.mkv"],
      "Trailers": ["trailer.mkv"]
    }
  }
]
```

---

## Getting started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- An [OMDb API key](https://www.omdbapi.com/apikey.aspx) (free tier available)

### 1. Configure environment variables

Copy the example below into a `.env` file in the project root and fill in your values:

```env
MYSQL_ROOT_PASSWORD=changeme
MYSQL_DATABASE=movies
MYSQL_USER=moviesuser
MYSQL_PASSWORD=changeme


# Ports for services
UI_PORT=80
PHPMYADMIN_PORT=8080

# Python app
CATALOG_API_IMAGE=movies_metadata_app
# Allow writing to the media files to add metadata
ENABLE_WRITE=False
# Drop the entire database and recreate it from scratch
FULL_REBUILD_DB=False
# Skip touching the database and just launch the app quickly for development.
# A True value supersedes both ENABLE_WRITE and FULL_REBUILD_DB skipping both actions
QUICK_LAUNCH_DEV=False
ENABLE_CRON_DB_REBUILD=True
# Cron schedule for rebuilding the database
CRON_DB_REBUILD_SCHEDULE=0 4 * * *

TZ=America/Chicago

# Open movie database API key
OMDB_API_KEY=your_omdb_api_key_here
```

### 2. Organise your movie files

Place your movie folders inside `media/Movies/` or wherever MOVIES_PATH points to. Each folder must follow this naming convention:

```
Movie Title (Year)/
Movie Title (Year) {edition-director}/
```

Examples:
```
media/Movies/
  Interstellar (2014)/
  The Dark Knight (2008)/
  Blade Runner 2049 (2017) {edition-final cut}/
```

Optional special-feature subfolders are detected automatically:
```
Jaws (1975)/
  Behind the Scenes/
  Trailers/
  Jaws (1975).mkv
```

### 3. Build and start

```bash
docker compose up --build
```

On first run the Python container will scan your movies directory, fetch missing metadata from OMDb, download poster images, and populate the database. This may take several minutes depending on collection size.

### 4. Access the services

| Service      | URL |
|--------------|-----|
| Web UI       | http://localhost/ |
| REST API     | http://localhost/api/movies |
| phpMyAdmin   | http://localhost:8080 |

### Rebuilding the database

To rescan your movie collection after adding or removing files, restart the Python container:

```bash
docker compose restart catalog_api
```

Or do a full rebuild (drops and recreates the database):

```bash
docker compose up --build --force-recreate catalog_api
```

### Updating the frontend only

Because the `www/` directory is mounted directly into the Nginx container, changes to HTML, CSS, and JS files are reflected immediately without a restart.

---

## Publishing release images (API + Web)

For production-style deployments, publish two images with the same tag:

- `movie-library-catalog-api` (Flask API + metadata processing)
- `movie-library-web` (Nginx + baked `www/` frontend files)

Use [docker-compose.publish.yml](docker-compose.publish.yml) to build and push both in one flow.

### Option A: Push both images to GHCR

```bash
export CATALOG_API_IMAGE=ghcr.io/<github-username>/movie-library-catalog-api:1.0.0
export WEB_IMAGE=ghcr.io/<github-username>/movie-library-web:1.0.0

# Use a GitHub PAT with write:packages and read:packages
echo <github_pat> | docker login ghcr.io -u <github-username> --password-stdin

docker compose -f docker-compose.publish.yml build
docker compose -f docker-compose.publish.yml push
```

Users can download with:

```bash
docker pull ghcr.io/<github-username>/movie-library-catalog-api:1.0.0
docker pull ghcr.io/<github-username>/movie-library-web:1.0.0
```

### Option B: Push both images to a self-hosted registry

```bash
export CATALOG_API_IMAGE=registry.<your-domain>/movie-library/catalog-api:1.0.0
export WEB_IMAGE=registry.<your-domain>/movie-library/web:1.0.0

docker login registry.<your-domain>
docker compose -f docker-compose.publish.yml build
docker compose -f docker-compose.publish.yml push
```

For self-hosting, use TLS and authentication on the registry before sharing images.

### Option C: Local registry via Docker Compose profile

This project includes an optional local registry service in [docker-compose.yaml](docker-compose.yaml) under the `registry` profile.

Start the local registry:

```bash
docker compose --profile registry up -d registry
```

Publish both images to the local registry:

```bash
export CATALOG_API_IMAGE=localhost:5000/movie-library/catalog-api:1.0.0
export WEB_IMAGE=localhost:5000/movie-library/web:1.0.0

docker compose -f docker-compose.publish.yml build
docker compose -f docker-compose.publish.yml push
```

Pull to verify:

```bash
docker pull localhost:5000/movie-library/catalog-api:1.0.0
docker pull localhost:5000/movie-library/web:1.0.0
```

If you want to expose it on your LAN, set a host port in `.env`:

```env
REGISTRY_PORT=5000
```

Then tag/push using your host IP or DNS name instead of `localhost`, for example `192.168.1.10:5000/...`.
Remote Docker clients may require an `insecure-registries` daemon setting unless you configure TLS.

## Deploying from published images

Use [docker-compose.example.yml](docker-compose.example.yml) for image-only deployment (no local code mounts required for frontend/API images).

```bash
docker compose -f docker-compose.example.yml up -d
```

Override image tags as needed:

```bash
export CATALOG_API_IMAGE=ghcr.io/<github-username>/movie-library-catalog-api:1.0.0
export WEB_IMAGE=ghcr.io/<github-username>/movie-library-web:1.0.0
docker compose -f docker-compose.example.yml up -d
```

---

## Project structure

```
.
├── docker-compose.yaml
├── docker-compose.publish.yml
├── docker-compose.example.yml
├── .env                    # Environment variables (not committed)
├── nginx/
│   └── default.conf        # Nginx routing config
├── catalog_api/
│   ├── app.py              # Flask API + startup logic
│   ├── movie_metadata.py   # ffprobe metadata helpers
│   ├── requirements.txt
│   └── Dockerfile
├── www/
│   ├── Dockerfile          # Web image build (Nginx + static UI)
│   ├── index.html          # Web UI
│   ├── script.js
│   ├── style.css
│   └── posters/            # Cached poster images
└── media/
    └── Movies/             # Your movie collection
```
