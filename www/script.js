function levenshteinDistance(a, b) {
    const matrix = [];

    // Increment along the first column of each row
    for (let i = 0; i <= b.length; i++) {
        matrix[i] = [i];
    }

    // Increment each column in the first row
    for (let j = 0; j <= a.length; j++) {
        matrix[0][j] = j;
    }

    // Fill in the rest of the matrix
    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            if (b.charAt(i - 1) === a.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1, // substitution
                    matrix[i][j - 1] + 1,     // insertion
                    matrix[i - 1][j] + 1      // deletion
                );
            }
        }
    }

    return matrix[b.length][a.length];
}

function convertFormDataToQuery(formData) {
    const json = {
        title: formData.get("title"),
        year: formData.get("year"),
        plot: formData.get("plot"),
        genre: formData.get("genre"),
        director: formData.get("director"),
        actor: formData.get("actor")
    };

    let query = Object.entries(json).reduce((query, [key, value]) => {
        if (value) { // Only include fields that have a value
            query[key] = value;
        }
        return query;
    }, {});

    // Convert to a string that we can pass as a query parameter
    query = Object.entries(query).map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join("&");

    return query;
}

function performSearch(query) {
    return new Promise((resolve, reject) => {
        fetch(`/api/movies?${query}`)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then((data) => resolve(data))
            .catch((error) => reject(error));
    });
}

function resolutionToQuality(resolution) {
    let tolerance = 0.1; // 10% tolerance for aspect ratio differences

    if (!resolution) {
        return "";
    }
    if (resolution.width >= (3840 - 3840 * tolerance) || resolution.height >= (2160 - 2160 * tolerance)) {
        return "UHD";
    } else if (resolution.width >= (1920 - 1920 * tolerance) || resolution.height >= (1080 - 1080 * tolerance)) {
        return "Blu-ray";
    } else {
        return "DVD";
    }
}

function createFeatureElement(feature) {
    const featureElement = document.createElement("li");
    featureElement.classList.add("feature");
    // Strip the file extension from the feature name if it has one
    feature = feature.replace(/\.[^/.]+$/, "");
    featureElement.textContent = feature;
    return featureElement;
}

function getSavedThemePreference() {
    const savedPreference = localStorage.getItem("themePreference");
    if (savedPreference === "light" || savedPreference === "dark" || savedPreference === "system") {
        return savedPreference;
    }
    return "system";
}

function applyThemePreference(preference) {
    const themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) {
        themeToggle.setAttribute("data-theme-selection", preference);
        themeToggle.querySelectorAll(".theme-toggle-option").forEach((button) => {
            button.setAttribute("aria-checked", String(button.dataset.themeOption === preference));
        });
    }

    if (preference === "system") {
        document.body.removeAttribute("data-theme");
        return;
    }

    document.body.setAttribute("data-theme", preference);
}

function initializeThemeToggle() {
    const themeToggle = document.getElementById("theme-toggle");
    if (!themeToggle) {
        return;
    }

    const savedPreference = getSavedThemePreference();
    applyThemePreference(savedPreference);

    themeToggle.querySelectorAll(".theme-toggle-option").forEach((button) => {
        button.addEventListener("click", () => {
            const nextPreference = button.dataset.themeOption;
            localStorage.setItem("themePreference", nextPreference);
            applyThemePreference(nextPreference);
        });
    });

    const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
    systemThemeQuery.addEventListener("change", () => {
        if (getSavedThemePreference() === "system") {
            applyThemePreference("system");
        }
    });
}

function displayResults(results) {
    // Get the title from form data
    const titleInput = document.getElementById("title");
    if (titleInput) {
        title = titleInput.value;

        // Sort the results by Levenshtein distance to the title
        results.sort((a, b) => {
            const distanceA = levenshteinDistance(a.title.toLowerCase(), title.toLowerCase());
            const distanceB = levenshteinDistance(b.title.toLowerCase(), title.toLowerCase());
            return distanceA - distanceB;
        });
    }

    const resultCount = document.getElementById("result-count");
    const resultsContainer = document.getElementById("results");

    // Clear previous results
    resultCount.textContent = `Found ${results.length} results`;
    resultsContainer.innerHTML = "";

    // Get the template element
    const template = document.getElementById("movie-panel");

    // Iterate over the results and create a new element for each movie
    results.forEach(movie => {
        const clone = template.content.cloneNode(true);
        let posterUrl = movie.metadata.format.tags.POSTER;

        // Covert the poster URL to point to my posters cache
        if (posterUrl) {
            const url = new URL(posterUrl);
            const filename = url.pathname.split("/").pop();
            posterUrl = `/posters/${filename}`;
        }

        clone.querySelector(".movie-poster").addEventListener("error", function() {
            // If the image fails to load, set the src to a placeholder image
            this.src = "/imgs/placeholder-poster.png";
        });

        clone.querySelector(".movie-poster").src = posterUrl;
        clone.querySelector(".title").textContent = movie.metadata.format.tags.TITLE;
        if (movie.edition) {
            clone.querySelector(".edition").textContent = movie.edition;
        } else {
            clone.querySelector(".edition").style.display = "none";
        }

        // Convert runtime from minutes, to hours and minutes
        const runtimeMinutes = parseInt(movie.metadata.format.tags.RUNTIME);
        if (!isNaN(runtimeMinutes)) {
            const hours = Math.floor(runtimeMinutes / 60);
            const minutes = runtimeMinutes % 60;
            clone.querySelector(".movie-runtime").textContent = `${hours}h ${minutes}m`;
        } else {
            clone.querySelector(".movie-runtime").textContent = `${movie.metadata.format.tags.RUNTIME}`;
        }

        clone.querySelector(".movie-rating").textContent = `${movie.metadata.format.tags.RATED}`;
        clone.querySelector(".movie-year").textContent = `${movie.year}`;
        clone.querySelector(".movie-quality").textContent = `${resolutionToQuality(movie.metadata.streams[0])}`;
        clone.querySelector(".movie-quality").setAttribute("class", `movie-quality ${resolutionToQuality(movie.metadata.streams[0])}`);
        clone.querySelector(".movie-actors").textContent = `Actors: ${movie.metadata.format.tags.ACTORS}`;
        clone.querySelector(".movie-director").textContent = `Director: ${movie.metadata.format.tags.DIRECTOR}`;
        clone.querySelector(".movie-genre").textContent = `Genres: ${movie.metadata.format.tags.GENRE}`;
        clone.querySelector(".movie-plot").textContent = `${movie.metadata.format.tags.PLOT}`;

        // Check if the movie has special features and display them if they exist
        if (movie.special_features) {
            clone.querySelector(".movie-special-features").style.display = "block";

            const featureTypes = [
                { name: "Behind The Scenes", className: "behind-the-scenes" },
                { name: "Deleted Scenes", className: "deleted-scenes" },
                { name: "Featurettes", className: "featurettes" },
                { name: "Interviews", className: "interviews" },
                { name: "Scenes", className: "scenes" },
                { name: "Shorts", className: "shorts" },
                { name: "Trailers", className: "trailers" },
                { name: "Other", className: "other" }
            ];

            // Check for each type of special feature and display them if they exist
            featureTypes.forEach(featureType => {
                if (Array.from(Object.keys(movie.special_features)).includes(featureType.name)) {
                    clone.querySelector(`.${featureType.className}`).style.display = "block";

                    // Create a header for the feature type
                    const header = document.createElement("h4");
                    header.textContent = featureType.name;
                    clone.querySelector(`.${featureType.className}`).appendChild(header);

                    movie.special_features[featureType.name].forEach(feature => {
                        clone.querySelector(`.${featureType.className}`).appendChild(createFeatureElement(feature));
                    });
                } else {
                    clone.querySelector(`.${featureType.className}`).style.display = "none";
                }
            });
        } else {
            clone.querySelector(".movie-special-features").style.display = "none";
        }

        resultsContainer.appendChild(clone);
    });
}

function validSearch(searchForm) {
    let formData = new FormData(searchForm);
    const entries = Object.fromEntries(formData.entries());

    return entries.title.length >= 2 || 
            entries.year.length == 4 ||
            entries.plot.length >= 3 ||
            entries.genre.length >= 2 ||
            entries.director.length >= 2 ||
            entries.actor.length >= 2;
}

function handleInput (searchForm) {
    if (validSearch(searchForm)) {
        performSearch(convertFormDataToQuery(new FormData(searchForm)))
            .then((results) => displayResults(results))
            .catch((error) => console.error("Error performing search:", error));
    } else {
        // Clear the results if the input length is less than 2
        const resultCount = document.getElementById("result-count");
        const resultsContainer = document.getElementById("results");
        resultCount.textContent = "";
        resultsContainer.innerHTML = "";
    }
}

// Onload entry point for the script
window.onload = function() {
    initializeThemeToggle();

    // Get the search form and add an event listener for the submit event
    const searchForm = document.getElementById("search-form");
    searchForm.addEventListener("submit", function(event) {
        event.preventDefault(); // Prevent the default form submission behavior
        performSearch(convertFormDataToQuery(new FormData(searchForm)))
            .then((results) => displayResults(results))
            .catch((error) => console.error("Error performing search:", error));
    });

    const titleInput = document.getElementById("title");
    titleInput.addEventListener("input", () => handleInput(searchForm));

    const yearInput = document.getElementById("year");
    yearInput.addEventListener("input", () => handleInput(searchForm));

    const detailedToggle = document.getElementById("detailed-search");
    detailedToggle.addEventListener("toggle", function() {
        if (!detailedToggle.open) {
            plotInput.value = "";
            genreInput.value = "";
            directorInput.value = "";
            actorInput.value = "";
        }
            
        handleInput(searchForm);
    });
    
    const plotInput = document.getElementById("plot");
    plotInput.addEventListener("input", () => handleInput(searchForm));

    const genreInput = document.getElementById("genre");
    genreInput.addEventListener("input", () => handleInput(searchForm));

    const directorInput = document.getElementById("director");
    directorInput.addEventListener("input", () => handleInput(searchForm));

    const actorInput = document.getElementById("actor");
    actorInput.addEventListener("input", () => handleInput(searchForm));
}
