# Stage 1: Build
FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_DASHBOARD_API_BASE=/api
ENV VITE_DASHBOARD_API_BASE=${VITE_DASHBOARD_API_BASE}

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci --ignore-scripts

# Copy only the files needed to build the frontend
COPY index.html ./
COPY vite.config.js ./
COPY public ./public
COPY src ./src

# Build the application
RUN npm run build

# Stage 2: Serve (non-root nginx on unprivileged port 8080)
FROM nginx:stable-alpine

# Remove the 'user' directive so nginx doesn't try to setuid when already non-root
RUN sed -i 's/^user\s/#user /' /etc/nginx/nginx.conf

# Copy the build output to Nginx's html directory
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration (listens on 8080)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Grant the nginx user ownership of all required directories
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && chown -R nginx:nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

# Switch to non-root user
USER nginx

# Expose non-privileged port
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
