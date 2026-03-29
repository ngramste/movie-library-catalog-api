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

When enabled, a background cron thread can also run scheduled partial rebuilds and poster refreshes.

---

## Web UI

The web interface is served at `http://<host>/` and provides a searchable, card-based view of your movie collection.

### Features

- **Live search** — results update as you type.
- **Movie cards** showing:
  - Poster image (cached locally, falls back to a placeholder)
  - Quality badge (**UHD**, **Blu-ray**, or **DVD**) derived from the video resolution
  - Title and edition
  - Year, MPA rating, runtime, director, actors, and genres
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

# Movies folder
MOVIES_PATH=/movies

# Python app
PYTHON_APP_IMAGE=movies_metadata_app
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

TIMEZONE=America/Chicago

# Open movie database API key
OMDB_API_KEY=your_omdb_api_key_here
```

### 2. Organise your movie files

Place your movie folders inside `media/Movies/`. Each folder must follow this naming convention:

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
  Behind The Scenes/
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
docker compose restart python_app
```

Or do a full rebuild (drops and recreates the database):

```bash
docker compose up --build --force-recreate python_app
```

Rebuild modes:

- `FULL_REBUILD_DB=True`: drops and recreates the `movies` table, then rescans everything.
- `FULL_REBUILD_DB=False`: performs a partial rebuild by rescanning disk, updating existing rows, adding new rows, and removing rows whose files no longer exist.
- `QUICK_LAUNCH_DEV=True`: skips startup rebuild and poster download entirely (useful for fast API/UI iteration).

When `ENABLE_CRON_DB_REBUILD=True`, the app uses `CRON_DB_REBUILD_SCHEDULE` and timezone (`TIMEZONE`, mapped to `TZ`) to run scheduled partial rebuilds and poster downloads in the background.

### Updating the frontend only

Because the `www/` directory is mounted directly into the Nginx container, changes to HTML, CSS, and JS files are reflected immediately without a restart.

---

## Project structure

```
.
├── docker-compose.yaml
├── .env                    # Environment variables (not committed)
├── nginx/
│   └── default.conf        # Nginx routing config
├── python_app/
│   ├── app.py              # Flask API + startup logic
│   ├── movie_metadata.py   # ffprobe metadata helpers
│   ├── requirements.txt
│   └── Dockerfile
├── www/
│   ├── index.html          # Web UI
│   ├── script.js
│   ├── style.css
│   └── posters/            # Cached poster images
└── media/
    └── Movies/             # Your movie collection
```
