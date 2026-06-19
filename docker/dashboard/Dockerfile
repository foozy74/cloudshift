FROM nginx:alpine

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy dashboard files
COPY index.html /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY style.css /usr/share/nginx/html/

# Copy Swagger UI files
COPY swagger.html /usr/share/nginx/html/
COPY swagger.json /usr/share/nginx/html/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]