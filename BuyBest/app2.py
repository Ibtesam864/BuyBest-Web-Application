
from flask import Flask, json, render_template, request, jsonify, send_file, session, redirect, url_for
from PIL import Image, ImageDraw, ImageFont
import mysql.connector
import cv2
from pyzbar.pyzbar import decode
import requests
import io
import os
import uuid
from flask_session import Session
from urllib.parse import quote

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Required for session management
app.config['SESSION_TYPE'] = 'filesystem'
app.config['TEMPLATES_AUTO_RELOAD'] = True  
Session(app)

# Database 
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'Buy_Right'
}

# Connect to MySQL server
def connect_to_mysql():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        raise

# Initialize database
def initialize_database():
    try:
        conn = connect_to_mysql()
        cursor = conn.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS Buy_Right")
        cursor.execute("USE Buy_Right")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100) UNIQUE,
            password VARCHAR(100)
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            cuisine VARCHAR(50),
            rating FLOAT,
            status VARCHAR(50)
        )
        """)
       
        cursor.execute("SELECT COUNT(*) FROM restaurants")
        if cursor.fetchone()[0] == 0:
            sample_restaurants = [
                ('Karachi Biryani House', 'Pakistani', 4.5, 'Safe to visit'),
                ('Lahore Grill', 'BBQ', 4.2, 'Safe to visit'),
                ('Islamabad Desi Kitchen', 'Traditional', 4.8, 'Safe to visit')
            ]
            cursor.executemany("""
            INSERT INTO restaurants (name, cuisine, rating, status)
            VALUES (%s, %s, %s, %s)
            """, sample_restaurants)
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Database initialization error: {err}")
        raise
    finally:
        if conn.is_connected():
            conn.close()

# product info snapshot
def save_product_info_snapshot(product_info_text, filename="product_info_snapshot.png"):
    width, height = 800, 400
    background_color = (255, 255, 255)
    text_color = (0, 0, 0)
    font_size = 20

    img = Image.new("RGB", (width, height), color=background_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    lines = []
    words = product_info_text.split()
    line = ""
    for word in words:
        if draw.textbbox((0, 0), line + " " + word, font=font)[2] <= width - 40:
            line += " " + word
        else:
            lines.append(line)
            line = word
    lines.append(line)

    y_text = 20
    for line in lines:
        draw.text((20, y_text), line.strip(), font=font, fill=text_color)
        y_text += font_size + 10

    os.makedirs('static/snapshots', exist_ok=True)  
    filepath = os.path.join('static', 'snapshots', filename)
    img.save(filepath)
    return filename


# Suggest alternatives
def suggest_alternatives(product_name):
    pname = product_name.lower()
    boycott_map = {
        ("fanta", "pepsi", "miranda", "sprite", "coke","coca-cola can","coca-cola classic","coca-cola zero"): [
            {"name": "ColaNext", "brand": "Mezan Beverages", "price": "Rs. 150"},
            {"name": "FizzUp", "brand": "Mezan Fizz Up", "price": "Rs. 150"},
            {"name": "Gourmet Cola", "brand": "Gourmet Foods", "price": "Rs. 140"}
        ],
        ("nescafe", "milkpak"): [
            {"name": "National Foods Tea", "brand": "National Foods", "price": "Rs. 250"},
            {"name": "Tapal Tea", "brand": "Tapal", "price": "Rs. 220"},
            {"name": "Nurpur Milk", "brand": "Nurpur", "price": "Rs. 300"}
        ],
        ("kitkat",): [
            {"name": "Candyland Wafers", "brand": "Candyland", "price": "Rs. 100"}
        ],
        ("snicker", "snickers"): [
            {"name": "Candyland ChocoFills", "brand": "Candyland", "price": "Rs. 120"}
        ],
        ("mars", "m&m", "m and m", "m&m's"): [
            {"name": "Candyland Chocolates", "brand": "Candyland", "price": "Rs. 150"}
        ],
    }

    for banned_products, alternatives in boycott_map.items():
        if any(bp in pname for bp in banned_products):
            return True, alternatives
    return False, []

# Fetch product info
def fetch_product_info(barcode_number):
    try:
        api_url = f"https://world.openfoodfacts.org/api/v0/product/{barcode_number}.json"
        response = requests.get(api_url, timeout=5)
        product_data = response.json()

        if product_data.get("status") == 1:
            product_info = product_data["product"]
            product_name = product_info.get("product_name", "N/A")
            brand_name = product_info.get("brands", "N/A")
            return product_name, brand_name
        return None, None
    except requests.RequestException as e:
        print(f"API request error: {e}")
        return None, None

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            conn = connect_to_mysql()
            cursor = conn.cursor()
            
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            confirm_password = request.form['confirm_password']

            if password != confirm_password:
                return jsonify({'error': 'Passwords do not match.'}), 400

            cursor.execute("""
            INSERT INTO users (name, email, password)
            VALUES (%s, %s, %s)
            """, (name, email, password))

            conn.commit()
            return jsonify({'message': 'User registered successfully!'})
        except mysql.connector.IntegrityError:
            return jsonify({'error': 'This email is already registered.'}), 400
        except mysql.connector.Error as e:
            return jsonify({'error': f'Database error: {str(e)}'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn.is_connected():
                conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            conn = connect_to_mysql()
            cursor = conn.cursor()

            email = request.form.get('email', '')
            password = request.form.get('password', '')

            cursor.execute("""
            SELECT id, name FROM users WHERE email = %s AND password = %s
            """, (email, password))

            result = cursor.fetchone()

            if result:
                session['user_id'] = result[0]
                session['user_name'] = result[1]
                return jsonify({'message': f'Login successful! Welcome, {result[1]}'})
            return jsonify({'error': 'Invalid email or password.'}), 401
        except mysql.connector.Error as e:
            return jsonify({'error': f'Database error: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    return redirect(url_for('index'))

@app.route('/scan', methods=['GET'])
def scan():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('scan_initial.html')


@app.route('/scan_barcode', methods=['POST'])
def scan_barcode():
    if 'user_id' not in session:
        return jsonify({'error': 'Please login.'}), 401

    barcode = request.form.get('barcode', '')
    print(f"Received barcode: {barcode}")  # Debug log
    if not barcode:
        return jsonify({'error': 'No barcode provided.'}), 400

    product_name, brand_name = fetch_product_info(barcode)
    
    if product_name and brand_name:
        is_boycotted, alternatives = suggest_alternatives(product_name)
        product_info = f"Product Name: {product_name}\nBrand: {brand_name}"
        filename = f"product_info_snapshot_{uuid.uuid4()}.png"
        save_product_info_snapshot(product_info, filename)
        return jsonify({
            'success': True,
            'product_name': product_name,
            'brand_name': brand_name,
            'is_boycotted': is_boycotted,
            'alternatives': alternatives,
            'snapshot_filename': filename
        })
    return jsonify({'error': 'Product not found in database.'}), 404

@app.route('/suggest_alternative', methods=['POST'])
def suggest_alternative():
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first.'}), 401

    product_name = request.form.get('product_name', '')
    if not product_name:
        return jsonify({'error': 'No product name provided.'}), 400

    is_boycotted, alternatives = suggest_alternatives(product_name)
    return jsonify({'is_boycotted': is_boycotted, 'alternatives': alternatives})

@app.route('/search_restaurants', methods=['GET'])
def search_restaurants():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        conn = connect_to_mysql()
        cursor = conn.cursor()
        cursor.execute("SELECT name, cuisine, rating, status FROM restaurants")
        restaurants = cursor.fetchall()
        return render_template('search_restaurants.html', restaurants=restaurants)
    except mysql.connector.Error as e:
        print(f"Database error: {str(e)}")
        return jsonify({'error': 'Failed to fetch restaurants.'}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Serve snapshot images
@app.route('/static/snapshots/<filename>')
def serve_snapshot(filename):
    return send_file(os.path.join('static', 'snapshots', filename))

@app.route('/navbar_content')
def navbar():
    return render_template('navbar.html')

@app.route('/scan_result.html')
def scan_result():
    product_name = request.args.get('product_name', 'Unknown Product')
    brand_name = request.args.get('brand_name', 'Unknown Brand')
    is_boycotted = request.args.get('is_boycotted', 'false') == 'true'
    snapshot_filename = request.args.get('snapshot_filename')
    alternatives = request.args.get('alternatives', '[]')
    try:
        alternatives = json.loads(alternatives) if alternatives else []
    except json.JSONDecodeError:
        alternatives = []
    return render_template('scan_result.html', 
                          product_name=product_name,
                          brand_name=brand_name,
                          is_boycotted=is_boycotted,
                          snapshot_filename=snapshot_filename,
                          alternatives=alternatives)

# Initialize database on startup
if __name__ == '__main__':
    try:
        initialize_database()
        app.run(debug=True, host='0.0.0.0', port=5001)
    except Exception as e:
        print(f"Application startup failed: {e}")