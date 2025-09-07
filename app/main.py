import json
import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Define the path to your seed_data directory
SEED_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'seed_data')
ADMIN_STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'admin_static')

def load_json_data(filename):
    """Helper function to load JSON data from a file."""
    filepath = os.path.join(SEED_DATA_DIR, filename)
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {filepath} not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {filepath}.")
        return None

# --- API Endpoints for Frontend Data ---

@app.route('/api/services', methods=['GET'])
def get_services():
    data = load_json_data('services.json')
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "Services data not found or invalid"}), 404

@app.route('/api/counties', methods=['GET'])
def get_counties():
    data = load_json_data('counties.json')
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "Counties data not found or invalid"}), 404

@app.route('/api/blog-posts', methods=['GET'])
def get_blog_posts():
    data = load_json_data('blog_posts.json')
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "Blog posts data not found or invalid"}), 404

@app.route('/api/homepage-data', methods=['GET'])
def get_homepage_data():
    data = load_json_data('homepage_data.json')
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "Homepage data not found or invalid"}), 404

@app.route('/api/about-page-data', methods=['GET'])
def get_about_page_data():
    data = load_json_data('about_page_data.json')
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "About page data not found or invalid"}), 404

@app.route('/api/gallery-images', methods=['GET'])
def get_gallery_images():
    data = load_json_data('gallery_images.json')
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "Gallery images data not found or invalid"}), 404

# Example for a single service detail (you'd need to pass slug/id)
@app.route('/api/services/<string:service_slug>', methods=['GET'])
def get_service_detail(service_slug):
    all_services = load_json_data('services.json')
    if all_services:
        service = next((s for s in all_services if s.get('slug') == service_slug), None)
        if service:
            return jsonify(service)
    return jsonify({"error": "Service not found"}), 404

@app.route('/api/blog-posts/<string:blog_slug>', methods=['GET'])
def get_blog_post_detail(blog_slug):
    all_blog_posts = load_json_data('blog_posts.json')
    if all_blog_posts:
        blog_post = next((p for p in all_blog_posts if p.get('slug') == blog_slug), None)
        if blog_post:
            return jsonify(blog_post)
    return jsonify({"error": "Blog post not found"}), 404

# --- Admin Dashboard Static Files ---

@app.route('/admin')
def admin_index():
    return send_from_directory(ADMIN_STATIC_DIR, 'index.html')

@app.route('/admin/<path:filename>')
def admin_static(filename):
    return send_from_directory(ADMIN_STATIC_DIR, filename)

# Basic health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Backend is running"}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
