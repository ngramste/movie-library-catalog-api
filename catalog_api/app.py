import os
from os import listdir
from os.path import isfile, join
import mysql.connector
from pymediainfo import MediaInfo
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from mysql.connector import Error
import time
from datetime import datetime
import requests
import threading
from urllib.parse import quote
from zoneinfo import ZoneInfo

import re

import json
from croniter import croniter

import movie_metadata as metadata

load_dotenv()  # Load .env

MYSQL_HOST = os.getenv("MYSQL_HOST", "mysql")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DATABASE")
MOVIES_PATH = "/movies"
TIMEZONE = os.getenv("TZ", "America/Chicago")

app = Flask(__name__)

def current_time_in_timezone():
    return datetime.now(ZoneInfo(TIMEZONE))

def find_roman_numeral(title):
    words = title.split(' ')
    for word in words:
        try:
            val = roman.fromRoman(word)
            return word
        except roman.InvalidRomanNumeralError:
            continue
    return None

def replace_roman_numeral(title):
    roman_numeral = find_roman_numeral(title)
    if roman_numeral:
        integer_value = roman.fromRoman(roman_numeral)
        title = title.replace(roman_numeral, str(integer_value))

    return title

def get_imdb_info(title, year, api_key):
    title = str(title)
    year = str(year)

    # The ideal search is for an exact match
    print(f"Searching OMDB for exact match: title='{title}', year='{year}'")
    url = f"http://www.omdbapi.com/?apikey={api_key}&t={quote(title)}&y={quote(year)}"

    response = requests.get(url)
    data = response.json()
    imdb_id = data['imdbID'] if 'imdbID' in data else "error"

    if 'Error' in data:
        url = f"http://www.omdbapi.com/?apikey={api_key}&s={quote(title)}&y={quote(year)}"

        response = requests.get(url)
        data = response.json()

    if 'Error' in data:
        title = title.replace('  ', ' ')
        url = f"http://www.omdbapi.com/?apikey={api_key}&s={quote(title)}&y={quote(year)}"

        response = requests.get(url)
        data = response.json()

    if 'Error' in data:
        title = title.replace(' - ', ' ').replace('  ', ' ')
        url = f"http://www.omdbapi.com/?apikey={api_key}&s={quote(title)}&y={quote(year)}"

        response = requests.get(url)
        data = response.json()

    if 'Error' in data:
        title = replace_roman_numeral(title)
        url = f"http://www.omdbapi.com/?apikey={api_key}&s={quote(title)}&y={quote(year)}"

        response = requests.get(url)
        data = response.json()

    if 'Error' in data:
        title = title.replace(' and ', ' & ')
        url = f"http://www.omdbapi.com/?apikey={api_key}&s={quote(title)}&y={quote(year)}"

        response = requests.get(url)
        data = response.json()
    
    # TODO: Find the closest match
    if 'Search' in data:
        imdb_id = data['Search'][0]['imdbID']

        # The ideal search is for an exact match
        url = f"http://www.omdbapi.com/?apikey={api_key}&i={imdb_id}"

        response = requests.get(url)
        data = response.json()

    if 'Error' not in data:
        print(f"Found OMDB match for title='{title}', year='{year}': imdb_id='{data.get('imdbID', 'N/A')}'")
        return data
    else:
        print(f"No OMDB match found for title='{title}', year='{year}'")
        return None

def connect_db(retries=10, delay=5):
    for i in range(retries):
        try:
            conn = mysql.connector.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DB
            )
            print("Connected to MySQL")
            return conn
        except Error as e:
            print(f"MySQL connection failed ({i+1}/{retries}): {e}")
            time.sleep(delay)
    raise Exception("Could not connect to MySQL after multiple retries")


def ensure_movies_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(255),
            filesize BIGINT,
            file_exists BOOLEAN,
            imdb_id VARCHAR(20),
            title VARCHAR(255),
            year INT,
            edition VARCHAR(255),
            metadata JSON,
            filetype VARCHAR(50),
            missing_featurettes BOOLEAN,
            special_features JSON
        )
    """)

def initialize_db():
    db = connect_db()
    cursor = db.cursor()
    # Simple schema
    cursor.execute("DROP TABLE IF EXISTS movies")
    db.commit()
    ensure_movies_table(cursor)
    db.commit()
    cursor.close()
    db.close()

def rebuild_db(full_rebuild):
    db = connect_db()
    cursor = db.cursor()

    # Fresh deployments may not have the movies table yet.
    ensure_movies_table(cursor)
    db.commit()

    # If we are not doing a full rebuild, mark all existing rows as file_exists = FALSE so that we spot missing files when we scan the folders
    if not full_rebuild:
        # Set the file_exists flag to false for all rows in the movies table
        cursor.execute("UPDATE movies SET file_exists = FALSE")
        db.commit()

    folders = [f for f in listdir(MOVIES_PATH) if not isfile(join(MOVIES_PATH, f))]
    number_of_folders = len(folders)

    print(f"Found {number_of_folders} folders in {MOVIES_PATH}")

    for index, folder in enumerate(folders):
        folder_path = f"{MOVIES_PATH}/{folder}"

        # Filenames are in the format "Movie Title (Year) {edition-xyz}", parse the title, year and edition from the folder name using regex
        result = re.search(r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)(?:\s*\{(?P<edition>.+?)\})?$", folder)
        if None == result:
            print(f"Skipping folder '{folder}' - does not match expected format")
            continue
        
        title = result.group("title").strip()
        year = int(result.group("year").strip())
        edition = result.group("edition").replace("edition-", "").strip() if result.group("edition") else None

        # Get the list of files in this folder
        files = [f for f in listdir(folder_path) if isfile(join(folder_path, f))]

        # Find the largest file in this folder
        file = max(files, key=lambda f: os.path.getsize(join(folder_path, f)))

        # Build a json object of all subfolders and files in those subfolders
        subfolders = [f for f in listdir(folder_path) if not isfile(join(folder_path, f))]

        # Filter out common hidden folders like __MACOSX, .DS_Store, etc.
        subfolders = [f for f in subfolders if not f.startswith(".") and not f.startswith("__") and not f.startswith("@eaDir")]

        subfolder_data = {}
        missing_featurettes = True
        
        for subfolder in subfolders:
            subfolder_path = join(folder_path, subfolder)
            subfolder_files = [f for f in listdir(subfolder_path) if isfile(join(subfolder_path, f))]
            subfolder_data[subfolder] = subfolder_files
            if subfolder_files:
                missing_featurettes = False

        if subfolder_data == {}:
            # If there is a file in the folder_path titled no_featurettes, the mark missing_featurettes as false
            if "no_featurettes" in files:
                missing_featurettes = False

            subfolder_data = None

        # If we are doing a partial rebuild, check if this file already exists in the database and mark it as file_exists = TRUE if it does
        if not full_rebuild:
            cursor.execute("SELECT id FROM movies WHERE filename = %s AND filesize = %s", (file, os.path.getsize(join(folder_path, file))))
            row = cursor.fetchone()
            if row:
                # Set the file_exists flag to TRUE for this row since the file exists on disk
                cursor.execute("UPDATE movies SET file_exists = TRUE WHERE id = %s", (row[0],))

                # Update the subfolder_data column for this row in the database
                cursor.execute("UPDATE movies SET special_features = %s, missing_featurettes = %s WHERE id = %s", (json.dumps(subfolder_data), missing_featurettes, row[0]))

                db.commit()
                continue

        # File is either missing from the database or we are doing a full rebuild and need to insert it as a new row

        # Get the filetype of the file
        filetype = os.path.splitext(file)[1][1:].lower()

        path = join(f"{folder_path}", file)

        # Check the file for existing imdb data within the metadata of the file
        data = metadata.get_metadata(path)
        
        # If the file is missing imdb data, try to get it from the filename and the OMDB API
        if not data or 'format' not in data or 'tags' not in data['format'] or 'IMDB' not in data['format']['tags'] or "error" == data['format']['tags'].get('IMDB', ''):
            print(f"Metadata for '{title}' ({year}) is missing IMDb data. Attempting to fetch from OMDB API...")
            api_key = os.getenv("OMDB_API_KEY")
            if api_key:
                imdb_data = get_imdb_info(title, year, api_key)
                if imdb_data:
                    if os.getenv("ENABLE_WRITE", "False").lower() == "true":
                        # Write the metadata to file
                        metadata.update_metadata(path, imdb_data)
                        
                    data = metadata.omdb_to_metadata(path, imdb_data)

                else:
                    print(f"Could not fetch IMDb data for '{title}' ({year}) from OMDB API.")

        # Insert the data into the database
        try:
            cursor.execute(
                "INSERT INTO movies (filename, filesize, file_exists, imdb_id, title, year, edition, metadata, filetype, missing_featurettes, special_features) \
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    file, 
                    os.path.getsize(path), 
                    True, 
                    data['format']['tags'].get('IMDB', ''), 
                    title, 
                    year, 
                    edition, 
                    json.dumps(data), 
                    filetype, 
                    missing_featurettes,
                    json.dumps(subfolder_data)
                )
            )
        except Exception as e:
            print(f"Error inserting data for {title} ({year}): {e}")
            continue
    
    db.commit()

    # Check for any movies that were in the database but whose files no longer exist on disk
    cursor.execute("SELECT id, filename FROM movies WHERE file_exists = FALSE")
    missing_files = cursor.fetchall()
    if missing_files:
        # Remove the rows for missing files from the database
        cursor.execute("DELETE FROM movies WHERE file_exists = FALSE")
        db.commit()

    cursor.close()
    db.close()

@app.route("/movies", methods=["GET"])
def list_movies():
    # Parse the optional get parameters
    if "help" in request.args:
        return jsonify({
            "imdb_id": "Filter by IMDb ID (exact match)",
            "title": "Filter by title (partial match, case insensitive)",
            "year": "Filter by year (exact match)",
            "edition": "Filter by edition (partial match, case insensitive)",
            "metadata": "Filter by metadata (partial match, case insensitive)",
            "filetype": "Filter by filetype (exact match, case insensitive)",
            "has_sf": "Filter by whether the movie has special features or not (true/false)",
            "plot": "Filter by plot (partial match, case insensitive)",
            "actor": "Filter by actor (partial match, case insensitive)",
            "director": "Filter by director (partial match, case insensitive)",
            "genre": "Filter by genre (partial match, case insensitive)",
            "missing_featurettes": "Filter by whether the movie is missing featurettes or not (true/false)"
        })

    imdb_id = request.args.get("imdb_id")
    title = request.args.get("title")
    year = request.args.get("year")
    edition = request.args.get("edition")
    metadata = request.args.get("metadata")
    filetype = request.args.get("filetype")
    has_special_features = request.args.get("has_sf")
    plot = request.args.get("plot")
    actor = request.args.get("actor")
    director = request.args.get("director")
    genre = request.args.get("genre")
    missing_featurettes = request.args.get("missing_featurettes")

    db = connect_db()
    cursor = db.cursor(dictionary=True)
    
    # Build the query based on the provided parameters
    query = "SELECT * FROM movies WHERE 1=1"
    params = []
    if imdb_id:
        query += " AND imdb_id = %s"
        params.append(imdb_id)
    if title:
        query += " AND metadata->>'$.format.tags.TITLE' LIKE %s COLLATE utf8mb4_0900_ai_ci"
        params.append(f"%{title}%")
    if year:
        query += " AND year = %s"
        params.append(year)
    if edition:
        query += " AND LOWER(edition) LIKE LOWER(%s)"
        params.append(f"%{edition}%")
    if metadata:
        query += " AND LOWER(metadata) LIKE LOWER(%s)"
        params.append(f"%{metadata}%")
    if filetype:
        query += " AND LOWER(filetype) = LOWER(%s)"
        params.append(filetype)
    # If has_special_features is true, we want to find all movies that have special features (i.e. the special_features column is not null and not an empty object)
    if has_special_features and has_special_features.lower() == "true":
        query += " AND JSON_TYPE(special_features) != 'NULL' AND COALESCE(JSON_LENGTH(special_features), 0) > 0"
    # If has_special_features is false, we want to find all movies that do not have special features (i.e. the special_features column is null or an empty object)
    if has_special_features and has_special_features.lower() == "false":
        query += " AND (JSON_TYPE(special_features) = 'NULL' OR COALESCE(JSON_LENGTH(special_features), 0) = 0)"
    if plot:
        # Plot is stored in the metadata JSON column. It is in metadata->'$.format.tags.PLOT'
        query += " AND metadata->>'$.format.tags.PLOT' LIKE %s COLLATE utf8mb4_0900_ai_ci"
        params.append(f"%{plot}%")
    if actor:
        # Actor is stored in the metadata JSON column. It is in metadata->'$.format.tags.ACTORS'
        query += " AND metadata->>'$.format.tags.ACTORS' LIKE %s COLLATE utf8mb4_0900_ai_ci"
        params.append(f"%{actor}%")
    if director:
        # Director is stored in the metadata JSON column. It is in metadata->'$.format.tags.DIRECTOR'
        query += " AND metadata->>'$.format.tags.DIRECTOR' LIKE %s COLLATE utf8mb4_0900_ai_ci"
        params.append(f"%{director}%")
    if genre:
        # Genre is stored in the metadata JSON column. It is in metadata->'$.format.tags.GENRE'
        query += " AND metadata->>'$.format.tags.GENRE' LIKE %s COLLATE utf8mb4_0900_ai_ci"
        params.append(f"%{genre}%")
    if missing_featurettes:
        if missing_featurettes.lower() == "true":
            query += " AND missing_featurettes = TRUE"
        elif missing_featurettes.lower() == "false":
            query += " AND missing_featurettes = FALSE"


    cursor.execute(query, params)
    result = cursor.fetchall()
    cursor.close()
    db.close()
    for row in result:
        if isinstance(row.get("metadata"), str):
            row["metadata"] = json.loads(row["metadata"])
        if isinstance(row.get("special_features"), str):
            row["special_features"] = json.loads(row["special_features"])
    return jsonify(result)

def download_posters():
    db = connect_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `movies`")
    movies = cursor.fetchall()

    requests_throttled = False

    for movie in movies:
        if requests_throttled:
            print("Requests are being throttled. Skipping poster downloads.")
            break

        if isinstance(movie.get("metadata"), str):
            try:
                poster_url = json.loads(movie["metadata"])["format"]["tags"]["POSTER"]
            except Exception as e:
                print(f"Error parsing metadata for {movie['title']} ({movie['year']}): {e}")
                continue

            if poster_url:
                output_path = f"/posters/{poster_url.split('/')[-1]}"
                # Check if the poster already exists
                if os.path.exists(output_path):
                    continue

                try:
                    print(f"Downloading poster for {movie['title']} ({movie['year']}) to {output_path}")
                    response = requests.get(poster_url)
                    if response.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(response.content)
                    elif response.status_code == 202 or response.status_code == 429:
                        requests_throttled = True
                    else:
                        print(f"Failed to download poster for {movie['title']} ({movie['year']}), status code: {response.status_code}")
                except Exception as e:
                    print(f"Error downloading poster for {movie['title']} ({movie['year']}): {e}")

    cursor.close()
    db.close()

# Set up a thread that runs the database rebuild on a schedule defined by the cron schedule environment variable
def update_db_thread():
    if os.getenv("ENABLE_CRON_DB_REBUILD", "False").lower() != "true":
        print("Cron-based database rebuild is disabled.")
        return

    cron_schedule = os.getenv("CRON_DB_REBUILD_SCHEDULE", "0 4 * * *").strip()

    try:
        cron = croniter(cron_schedule, current_time_in_timezone())
    except Exception as error:
        print(f"Invalid CRON_DB_REBUILD_SCHEDULE '{cron_schedule}': {error}")
        return

    print(f"Cron-based database rebuild enabled with schedule '{cron_schedule}' in timezone '{TIMEZONE}'")

    while True:
        next_run = cron.get_next(datetime)
        sleep_seconds = max(1, int((next_run - current_time_in_timezone()).total_seconds()))
        print(f"Current system time is {current_time_in_timezone().isoformat()}")
        print(f"Next scheduled database rebuild at {next_run.isoformat()}")
        print(f"Sleeping for {sleep_seconds} seconds until next scheduled database rebuild...")
        time.sleep(sleep_seconds)

        try:
            print("Starting scheduled database rebuild...")
            rebuild_db(False)
            print("Starting scheduled poster download...")
            download_posters()
            print("Scheduled database rebuild completed.")
        except Exception as error:
            print(f"Scheduled database rebuild failed: {error}")

if __name__ == "__main__":
    if os.getenv("QUICK_LAUNCH_DEV", "False").lower() == "false":
        if os.getenv("FULL_REBUILD_DB", "False").lower() == "true":
            print("Initializing database...")
            initialize_db()
        print("Rebuilding database with movie metadata...")
        rebuild_db(os.getenv("FULL_REBUILD_DB", "False").lower() == "true")
        print("Download poster images for movies...")
        download_posters()

    rebuild_thread = threading.Thread(target=update_db_thread, daemon=True)
    rebuild_thread.start()

    print("Starting Flask app...")
    app.run(host="0.0.0.0", port=5000)