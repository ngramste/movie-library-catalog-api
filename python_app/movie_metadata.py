from datetime import datetime as dt
import json
import subprocess
import tempfile
from xml.sax.saxutils import escape
from mutagen.mp4 import MP4
import re

# Function that takes the path to a video file and updates the metadata using mkvpropedit
def update_metadata_mkv(video_path, data):
    resolution = get_resolution(video_path)

    date_value = f"{data['Year']}-01-01T00:00:00Z"
    try:
        date_value = dt.strptime(data['Released'], "%d %b %Y").strftime("%Y-%m-%dT00:00:00Z")
    except (KeyError, ValueError):
        pass

    tags_xml = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<Tags>
    <Tag>
        <Targets>
            <TargetTypeValue>50</TargetTypeValue>
        </Targets>
"""
    
    for key, value in data.items():
        tags_xml += f"<Simple><Name>{escape(key.upper())}</Name><String>{escape(str(value))}</String></Simple>"

    tags_xml += f"<Simple><Name>WIDTH</Name><String>{escape(str(resolution['width']))}</String></Simple>"
    tags_xml += f"<Simple><Name>HEIGHT</Name><String>{escape(str(resolution['height']))}</String></Simple>"
    tags_xml += f"<Simple><Name>DATE_RELEASED</Name><String>{escape(date_value)}</String></Simple>"

    tags_xml += f"""\
    </Tag>
</Tags>
"""

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".xml", encoding="utf-8", newline="\n") as f:
        f.write(tags_xml)
        tagfile = f.name

    # Construct the mkvpropedit command to update the metadata
    command = [
        "mkvpropedit", video_path,
        "--edit", "info",
        "--set", f"title={data['imdb_title']}",
        "--set", f"date={date_value}",
        "--tags", f"all:{tagfile}"
    ]

    # Run the mkvpropedit command
    output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(output.stdout.decode('utf-8'))

def update_metadata_mp4(video_path, data):
    resolution = get_resolution(video_path)
    video = MP4(video_path)

    date = f"date={data['Year']}-01-01T00:00:00Z"
    try:
        date = dt.strptime(data['Released'], "%d %b %Y").strftime("date=%Y-%m-%dT00:00:00Z")
    except Exception as e:
        pass

    video["\xa9nam"] = data['imdb_title']
    video["\xa9day"] = date
    
    for key, value in data.items():
        video[f"----:com.apple.iTunes:{key.upper()}"] = f"{value}".encode('utf-8')
    
    video["----:com.apple.iTunes:WIDTH"] = resolution['width'].encode('utf-8')
    video["----:com.apple.iTunes:HEIGHT"] = resolution['height'].encode('utf-8')
    video.save()


# Function that takes the path to a video file and updates the metadata using mkvpropedit
def update_metadata(video_path, data):
    data['IMDB'] = data['imdbID']
    data['imdb_title'] = f"{data['Title']} ({data['Year']})"
    if video_path.endswith('.mkv') or video_path.endswith('.avi'):
        update_metadata_mkv(video_path, data)
    elif video_path.endswith('.mp4') or video_path.endswith('.m4v'):
        update_metadata_mp4(video_path, data)


# Function to get the metadata of a video file using ffprobe
def get_metadata_mkv(video_path):
    command = [
        "ffprobe", 
        "-v", "error",
        "-probesize", "32K",      # Reduce the amount of data ffprobe reads for faster results
        "-analyzeduration", "0",  # Reduce the amount of data ffprobe reads for faster results
        "-of", "json",
        '-select_streams', 'v:0',
        "-show_entries", "format:stream=width,height",
        video_path
    ]

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8')
    metadata = json.loads(output)

    # If we didn't pull any metadata from omdb, return None
    if not 'format' in metadata and 'tags' in metadata['format'] and 'IMDB' in metadata['format']['tags']:
        return None

    return metadata

def get_metadata_mp4(video_path):
    video = MP4(video_path)

    if "\xa9nam" not in video or "\xa9day" not in video or "----:com.apple.iTunes:IMDB" not in video:
        return None
    
    metadata = {
        'format': {
            'tags': {
                'title': video.get("\xa9nam", [""])[0],
                'YEAR': video.get("\xa9day", [""])[0]
            }
        },
        'streams': [{
            'width': video.get("----:com.apple.iTunes:WIDTH", [b""])[0].decode('utf-8'),
            'height': video.get("----:com.apple.iTunes:HEIGHT", [b""])[0].decode('utf-8')
        }]
    }

    for tag, value in video.tags.items():
        if "com.apple.iTunes" in tag:
            metadata['format']['tags'][tag.split(":")[-1].upper()] = value[0].decode('utf-8')

    return metadata

def get_resolution(video_path):
    delimiter = ","

    # Run ffprobe on the command line to get the resolution of the video file
    resolution = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                    'stream=width,height', '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    resolution = resolution.stdout.decode('ascii').strip().replace('\r\n', delimiter).replace('\n', delimiter).split(delimiter)

    return {
        'width': resolution[0] if len(resolution) >= 1 else "error",
        'height': resolution[1] if len(resolution) >= 2 else "error"
    }

def omdb_to_metadata(video_path, omdb_data):
    resolution = get_resolution(video_path)

    if not omdb_data:
        return None

    metadata = {
        'format': {
            'tags': {}
        },
        'streams': [{
            'width': resolution['width'],
            'height': resolution['height']
        }]
    }
    
    for key, value in omdb_data.items():
        metadata['format']['tags'][key.upper()] = value

    return metadata


def get_metadata(video_path):
    metadada = None

    if video_path.endswith('.mkv') or video_path.endswith('.avi'):
        metadada = get_metadata_mkv(video_path)
    elif video_path.endswith('.mp4') or video_path.endswith('.m4v'):
        metadada = get_metadata_mp4(video_path)

    # If we didn't pull any metadata, get the resolution and return that we do have
    if None == metadada:
        resolution = get_resolution(video_path)
        
        # Store the title which should be the filename without the year, edition, and extension
        # For example, if the filename is "Movie Title (2023) {edition-xyz}.mkv", we want "Movie Title"
        filename = ".".join(video_path.split("\\")[-1].split(".")[:-1])
        result = re.search(r"^(?P<title>.+?)\s*\(\d{4}\)(?:\s*\{.+?\})?$", filename)
        title = result.group("title").strip() if result else filename

        metadada = {
            'format': {
                'tags': {
                    'IMDB': "error",
                    'TITLE': title,
                    # Best guess is the filename without the extension, but this is just a guess and may not be correct.
                    'IMDB_TITLE': filename,
                    'WIDTH': resolution['width'],
                    'HEIGHT': resolution['height']
                }
            }
        }

    return metadada
