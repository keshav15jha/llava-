from flask import Flask, render_template, request, jsonify, session, redirect
from utils.amazon_scraper import AmazonScraper
import os
from dotenv import load_dotenv
import anthropic
from os import environ
import json
from utils.ad_config import AD_PLATFORMS
import re
import requests
import base64
import time
import imghdr
from services.recommendation_service import generate_recommendations
from services.banner_service import (
    generate_banner_config,
)
from services.random_banner_service import (
    generate_random_banner,
)


# loading sample banners
sample_banners = []
for file in os.listdir('sample-banners'):
    if file.endswith('.json'):
        with open('sample-banners', 'r', encoding='latin-1') as f:
                 sample_banners.append(f.read())
            
# Load environment variables
load_dotenv()

# Initialize Anthropic client with API key
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-default-secret-key')

@app.route('/')
def home():
    return render_template('index.html', platforms=AD_PLATFORMS)

@app.route('/results', methods=['GET'])
def results():
    product_details = session.get('product_details')
    print("\nDebug: Product Details in results route:", product_details)
    
    if not product_details:
        return redirect('/')
        
    return render_template('results.html', 
                         product_details=product_details,
                         debug_info={
                             "keys_available": list(product_details.keys()),
                             "product_name": product_details.get('product_name', 'NOT FOUND'),
                             "session_data": bool(session.get('product_details'))
                         })

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                'success': False,
                'error': 'URL is required'
            }), 400

        url = data['url']
        platform = data.get('platform', 'custom')
        dimensions = data.get('dimensions', 'custom_1:1080x1080')
        
        # Parse dimensions string (format: "dimension_name:1080 x 1080")
        dimension_name, dimension_value = dimensions.split(':')
        width, height = map(int, dimension_value.split('x'))
        
        scraper = AmazonScraper()
        product_details = scraper.extract_product_details(url)
        
        if not product_details:
            return jsonify({
                'success': False,
                'error': 'Failed to scrape product details'
            }), 500

        # Store in session
        session['product_details'] = product_details
        session['ad_config'] = {
            'platform': platform,
            'dimension_name': dimension_name,
            'width': width,
            'height': height
        }
        
        return jsonify({
            'success': True,
            'product_details': product_details
        })

    except Exception as e:
        print(f"Error in generate route: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/recommendations', methods=['GET', 'POST'])
def recommendations():
    try:
        if request.method == 'POST':
            product_details = request.get_json()
            if not product_details:
                return jsonify({'error': 'No product details provided'}), 400
            
            session['product_details'] = product_details
            return jsonify({'success': True})
            
        # GET request - generate recommendations
        product_details = session.get('product_details')
        if not product_details:
            return redirect('/')

        # Initialize Claude client
        client = anthropic.Client(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
        # Generate recommendations
        recommendations = generate_recommendations(client, product_details)
        
        # Store in session
        session['recommendations'] = recommendations
        
        return render_template('recommendations.html',
                             recommendations=recommendations,
                             product=product_details)

    except Exception as e:
        print(f"Route Error: {str(e)}")
        return jsonify({
            "error": str(e),
            "success": False
        }), 500

@app.route('/generate-banner', methods=['POST'])
def generate_banner():
    try:
        data = request.get_json()
        recommendations = data.get('recommendations')
        product = data.get('product')
        
        # Get ad_config from session
        ad_config = session.get('ad_config', {})
        if not ad_config:
            return jsonify({
                "success": False,
                "error": "No ad configuration found. Please select dimensions first."
            }), 400

        # Initialize Claude client
        client = anthropic.Client(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
        # Generate banner configuration
        canvas_config = generate_banner_config(
            client,
            ad_config.get('width', 1080),
            ad_config.get('height', 1080),
            ad_config.get('platform', 'custom'),
            recommendations,
            product
        )
        
        # Store in session
        session['banner_config'] = canvas_config
        return jsonify({"success": True})

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/ai-banner')
def ai_banner():
    banner_config = session.get('banner_config')
    original_response = session.get('original_response')
    
    if not banner_config:
        return redirect('/recommendations')
    
    # Get ad_config from session, with default values if not present
    ad_config = session.get('ad_config', {
        'platform': 'custom',
        'width': 1080,
        'height': 1080
    })
        
    return render_template('banner.html', 
                         banner_config=banner_config,
                         original_response=original_response,
                         ad_config=ad_config)

def get_font_urls_content():
    try:
        font_file_path = 'utils/font_urls_450.txt'
        if not os.path.exists(font_file_path):
            print(f"Error: Font URLs file not found at {font_file_path}")
            return ""
            
        with open(font_file_path, 'r') as file:
            content = file.read()
            print(f"Successfully loaded {len(content.splitlines())} font URLs")
            return content
            
    except Exception as e:
        print(f"Error reading font URLs file: {str(e)}")
        return ""

@app.route('/generate-random-banner', methods=['POST'])
def generate_random_banner_route():
    try:
        # Get product details from request
        product_details = request.json
        
        # Get ad_config from session
        ad_config = session.get('ad_config', {
            'width': 1080,
            'height': 1080,
            'platform': 'meta'
        })
        
        # Initialize Claude client
        client = anthropic.Client(api_key=os.getenv('ANTHROPIC_API_KEY'))
        
        # Generate banner configuration directly
        banner_config = generate_random_banner(
            client=client,
            width=ad_config['width'],
            height=ad_config['height'],
            platform=ad_config['platform'],
            product=product_details
        )
        
        # Store both the banner config and original response
        session['banner_config'] = banner_config
        session['original_response'] = banner_config  # Store original separately
        
        return jsonify({
            'success': True,
            'message': 'Banner configuration generated successfully'
        })
        
    except Exception as e:
        print(f"Error generating random banner: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(environ.get('PORT', 8000))
    debug = environ.get('FLASK_ENV', 'development') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)