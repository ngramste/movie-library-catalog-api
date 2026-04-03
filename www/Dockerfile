FROM nginx:stable-alpine

# Nginx config includes API proxying to the catalog_api service.
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# Bake static frontend assets into the image for image-only deployments.
COPY www/ /usr/share/nginx/html/
