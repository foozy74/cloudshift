ARG BASE_IMAGE=nginx:alpine
FROM ${BASE_IMAGE}

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy dashboard files
COPY index.html /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY style.css /usr/share/nginx/html/

# Copy Swagger UI files
COPY swagger.html /usr/share/nginx/html/
COPY swagger.json /usr/share/nginx/html/

# SSL certificates are not baked into the image.
# Mount them at runtime: ./docker/dashboard/ssl:/etc/nginx/ssl:ro

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]