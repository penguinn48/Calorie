from flask import Flask, request, render_template, url_for, jsonify
from clarifai_grpc.channel.clarifai_channel import ClarifaiChannel
from clarifai_grpc.grpc.api import resources_pb2, service_pb2, service_pb2_grpc
from clarifai_grpc.grpc.api.status import status_code_pb2
import os
import requests
from werkzeug.utils import secure_filename
import random

# Flask App Configuration
app = Flask(__name__, static_url_path='/static')
UPLOAD_FOLDER = os.path.join('static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB limit

# API Keys and Constants
CLARIFAI_PAT = '121b7bb4375e4687b300bf1556e195ab'
CLARIFAI_USER_ID = 'clarifai'
CLARIFAI_APP_ID = 'main'
CLARIFAI_MODEL_ID = 'food-item-recognition'
CLARIFAI_MODEL_VERSION_ID = '1d5fd481e0cf4826aa72ec3ff049e044'

USDA_API_KEY = '5kubQnilaWsMtNgE26708OMyYpxBibvzS5zBJntN'
USDA_BASE_URL = 'https://api.nal.usda.gov/fdc/v1'

PEXELS_API_KEY = '4gMtichtbSZQfE7Vv2pcnX9Hgmna1GOuksNzTjHl8qupy1Wg9jUbtNr9'
PEXELS_API_URL = 'https://api.pexels.com/v1/search'

# File Upload Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Global Variables
nutrition_history = []
daily_totals = {
    'Energy': 0,
    'Protein': 0,
    'Total lipid (fat)': 0,
    'Carbohydrate, by difference': 0,
    'Fiber, total dietary': 0
}

# Helper Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_food_image(food_name):
    """Fetch a relevant food image from Pexels"""
    try:
        params = {
            'query': f'{food_name} food',
            'per_page': 10,
            'orientation': 'landscape',
            'size': 'medium'
        }
        headers = {
            'Authorization': PEXELS_API_KEY
        }
        
        response = requests.get(PEXELS_API_URL, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if data.get('photos'):
            random_image = random.choice(data['photos'])
            return {
                'url': random_image['src']['large'],
                'credit': {
                    'name': random_image['photographer'],
                    'link': random_image['photographer_url']
                }
            }
    except Exception as e:
        print(f"Error fetching image: {str(e)}")
    return None

# Nutrition Analysis Functions
def analyze_nutrition(nutrients, food_name):
    """Provide detailed nutritional analysis with specific comments"""
    try:
        protein = nutrients.get('Protein', {}).get('value', 0)
        fat = nutrients.get('Total lipid (fat)', {}).get('value', 0)
        carbs = nutrients.get('Carbohydrate, by difference', {}).get('value', 0)
        energy = nutrients.get('Energy', {}).get('value', 0)
        fiber = nutrients.get('Fiber, total dietary', {}).get('value', 0)

        insights = []
        
        # Protein analysis with recommendations
        if protein > 20:
            insights.append("✅ Protein: Excellent! ({:.1f}g) - Great for muscle building and recovery".format(protein))
        elif protein > 10:
            insights.append("✅ Protein: Good amount ({:.1f}g) - Helps with satiety and muscle maintenance".format(protein))
        elif protein > 5:
            insights.append("⚠️ Protein: Moderate ({:.1f}g) - Consider combining with other protein sources".format(protein))
        else:
            insights.append("❌ Protein: Low ({:.1f}g) - May need to supplement with protein-rich foods".format(protein))

        # Fat analysis with context
        if fat > 20:
            insights.append("❌ Fat: High ({:.1f}g) - Consider portion control, especially if eating multiple times per day".format(fat))
        elif fat > 10:
            insights.append("⚠️ Fat: Moderate ({:.1f}g) - Within reasonable range for a meal, but monitor total daily intake".format(fat))
        elif fat > 5:
            insights.append("✅ Fat: Good amount ({:.1f}g) - Healthy level for most meals".format(fat))
        else:
            insights.append("✅ Fat: Low ({:.1f}g) - Good for low-fat diets".format(fat))

        # Carbohydrate analysis with meal timing suggestions
        if carbs > 50:
            insights.append("⚠️ Carbs: High ({:.1f}g) - Best consumed around exercise or as main meal".format(carbs))
        elif carbs > 30:
            insights.append("⚠️ Carbs: Moderate-high ({:.1f}g) - Consider timing around physical activity".format(carbs))
        elif carbs > 15:
            insights.append("✅ Carbs: Moderate ({:.1f}g) - Good for sustained energy".format(carbs))
        else:
            insights.append("✅ Carbs: Low ({:.1f}g) - Good for low-carb diets".format(carbs))

        # Fiber analysis with health benefits
        if fiber > 7:
            insights.append("✅ Fiber: Excellent ({:.1f}g) - Great for digestive health and sustained energy".format(fiber))
        elif fiber > 4:
            insights.append("✅ Fiber: Good ({:.1f}g) - Helps with digestion and feeling full".format(fiber))
        elif fiber > 2:
            insights.append("⚠️ Fiber: Moderate ({:.1f}g) - Could benefit from more fiber-rich foods".format(fiber))
        else:
            insights.append("❌ Fiber: Low ({:.1f}g) - Consider adding more high-fiber foods to your diet".format(fiber))

        # Calorie analysis with meal sizing context
        if energy > 600:
            insights.append("❌ Calories: High ({:.0f} kcal) - Consider as a large or main meal of the day".format(energy))
        elif energy > 400:
            insights.append("⚠️ Calories: Moderate-high ({:.0f} kcal) - Suitable for a full meal".format(energy))
        elif energy > 200:
            insights.append("✅ Calories: Moderate ({:.0f} kcal) - Good for a light meal".format(energy))
        else:
            insights.append("✅ Calories: Low ({:.0f} kcal) - Suitable for a snack".format(energy))

        # Daily value context
        dv_insights = []
        if protein > 0:
            protein_dv = (protein/50)*100
            dv_insights.append(f"This provides {protein_dv:.1f}% of daily protein needs (based on 50g daily requirement)")
        if fiber > 0:
            fiber_dv = (fiber/25)*100
            dv_insights.append(f"This provides {fiber_dv:.1f}% of daily fiber needs (based on 25g daily requirement)")

        return {
            'color': '#2196F3',  # Neutral blue color
            'nutrients_analysis': insights,
            'daily_values': dv_insights,
            'details': "Nutritional Analysis:\n• " + "\n• ".join(insights) + "\n\nDaily Values:\n• " + "\n• ".join(dv_insights)
        }

    except Exception as e:
        print(f"Error analyzing nutrition: {str(e)}")
        return {
            'color': '#808080',
            'nutrients_analysis': ["Unable to analyze nutritional content"],
            'daily_values': [],
            'details': "Unable to analyze nutritional content due to insufficient information"
        }

def get_nutrition_info(food_name):
    """Get nutritional information from USDA database"""
    try:
        search_url = f"{USDA_BASE_URL}/foods/search"
        params = {
            'api_key': USDA_API_KEY,
            'query': food_name,
            'dataType': ['Survey (FNDDS)'],
            'pageSize': 1
        }
        
        response = requests.get(search_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('foods') and len(data['foods']) > 0:
            food = data['foods'][0]
            nutrients = {}
            
            # Get serving size information
            serving_size = "per 100g"  # Default serving size
            if 'servingSize' in food and 'servingSizeUnit' in food:
                serving_size = f"per {food['servingSize']}{food['servingSizeUnit']}"
            
            # Extract common nutrients
            for nutrient in food.get('foodNutrients', []):
                if nutrient.get('nutrientName') in [
                    'Energy', 'Protein', 'Total lipid (fat)', 
                    'Carbohydrate, by difference', 'Fiber, total dietary'
                ]:
                    nutrients[nutrient['nutrientName']] = {
                        'value': nutrient.get('value', 0),
                        'unit': nutrient.get('unitName', 'g')
                    }
            
            # Get nutritional analysis
            analysis = analyze_nutrition(nutrients, food_name)
            
            return {
                'name': food['description'],
                'nutrients': nutrients,
                'serving_size': serving_size,  # Add serving size to the return data
                'analysis': analysis
            }
    except Exception as e:
        print(f"Error fetching nutrition data: {str(e)}")
    return None

# Food Recognition Functions
def get_food_predictions(image_path):
    channel = ClarifaiChannel.get_grpc_channel()
    stub = service_pb2_grpc.V2Stub(channel)

    metadata = (('authorization', 'Key ' + CLARIFAI_PAT),)

    with open(image_path, 'rb') as f:
        file_bytes = f.read()

    post_model_outputs_request = service_pb2.PostModelOutputsRequest(
        user_app_id=resources_pb2.UserAppIDSet(
            user_id=CLARIFAI_USER_ID,
            app_id=CLARIFAI_APP_ID
        ),
        model_id=CLARIFAI_MODEL_ID,
        version_id=CLARIFAI_MODEL_VERSION_ID,
        inputs=[
            resources_pb2.Input(
                data=resources_pb2.Data(
                    image=resources_pb2.Image(
                        base64=file_bytes
                    )
                )
            )
        ]
    )

    try:
        response = stub.PostModelOutputs(post_model_outputs_request, metadata=metadata)
        
        if response.status.code != status_code_pb2.SUCCESS:
            error_msg = response.status.description or f"Request failed, status code: {response.status.code}"
            raise Exception(error_msg)
            
        concepts = response.outputs[0].data.concepts
        food_concepts = [concept for concept in concepts if concept.value > 0.5]
        
        # Get nutrition information for each detected food
        enhanced_concepts = []
        for concept in food_concepts:
            food_info = {
                'name': concept.name,
                'confidence': concept.value,
                'nutrition': get_nutrition_info(concept.name)
            }
            enhanced_concepts.append(food_info)
            
        return enhanced_concepts

    except Exception as e:
        print(f"Error details: {str(e)}")
        raise

# Nutrition Tracking Functions
def add_to_nutrition_history(food_info):
    global nutrition_history, daily_totals
    
    if food_info.get('nutrition'):
        history_entry = {
            'name': food_info['name'],
            'nutrients': food_info['nutrition']['nutrients']
        }
        
        # Update daily totals
        for nutrient_name, data in food_info['nutrition']['nutrients'].items():
            if nutrient_name in daily_totals:
                daily_totals[nutrient_name] += data['value']
        
        # Add to history
        nutrition_history.append(history_entry)
        return {
            'status': 'success',
            'message': f'Added {food_info["name"]} to your food tracking',
            'totals': daily_totals
        }
    return None

# Route Handlers
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('upload.html', error='No file selected')
        file = request.files['file']
        if file.filename == '':
            return render_template('upload.html', error='No file selected')
        if not allowed_file(file.filename):
            return render_template('upload.html', error='Invalid file type. Please upload an image (PNG, JPG, JPEG, GIF)')
        if file:
            try:
                # Create a secure filename
                filename = secure_filename(file.filename)
                
                # Ensure the upload folder exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                # Create full file path
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Save the file
                file.save(file_path)

                # Get food predictions with nutrition info
                predictions = get_food_predictions(file_path)
                return render_template('result.html', foods=predictions, uploaded_image=filename)
                
            except Exception as e:
                print(f"Error during file upload: {str(e)}")
                return render_template('upload.html', error=f'An error occurred: {str(e)}')

    return render_template('upload.html')

@app.route('/search', methods=['POST'])
def search_food():
    """Handle food name search"""
    food_name = request.form.get('food_name', '').strip()
    if not food_name:
        return render_template('upload.html', error='Please enter a food name')
    
    try:
        # Get food image from Pexels
        image_info = get_food_image(food_name)
        
        food_info = {
            'name': food_name,
            'confidence': 1.0,
            'nutrition': get_nutrition_info(food_name),
            'image': image_info  # Add image information
        }
        return render_template('result.html', foods=[food_info], uploaded_image=None)
    except Exception as e:
        return render_template('upload.html', error=f'An error occurred: {str(e)}')

@app.route('/suggestions', methods=['GET'])
def get_suggestions():
    """Get food name suggestions"""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    
    try:
        # Search USDA database for suggestions
        search_url = f"{USDA_BASE_URL}/foods/search"
        params = {
            'api_key': USDA_API_KEY,
            'query': query,
            'dataType': ['Survey (FNDDS)'],
            'pageSize': 10  # Increased to show more suggestions
        }
        
        response = requests.get(search_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        suggestions = [food['description'] for food in data.get('foods', [])]
        return jsonify(suggestions)
    except Exception as e:
        print(f"Error fetching suggestions: {str(e)}")
        return jsonify([])

@app.route('/nutrition_summary')
def nutrition_summary():
    """Display nutrition summary page"""
    global nutrition_history, daily_totals
    return render_template('nutrition_summary.html',
                         history=nutrition_history,
                         totals=daily_totals)

@app.route('/reset_tracking', methods=['POST'])
def reset_tracking():
    """Reset nutrition tracking data"""
    global nutrition_history, daily_totals
    nutrition_history = []
    daily_totals = {
        'Energy': 0,
        'Protein': 0,
        'Total lipid (fat)': 0,
        'Carbohydrate, by difference': 0,
        'Fiber, total dietary': 0
    }
    return jsonify({'status': 'success'})

@app.route('/confirm_food', methods=['POST'])
def confirm_food():
    """Handle food confirmation and tracking"""
    try:
        food_data = request.json
        if food_data and 'confirmed' in food_data:
            if food_data['confirmed']:
                food_info = {
                    'name': food_data['name'],
                    'nutrition': food_data['nutrition']
                }
                add_to_nutrition_history(food_info)
                return jsonify({
                    'status': 'success',
                    'message': f'Added {food_info["name"]} to your food tracking',
                    'totals': daily_totals
                })
        return jsonify({'status': 'skipped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# Main
if __name__ == '__main__':
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True) 
