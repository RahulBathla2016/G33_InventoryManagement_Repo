import jwt
from flask import Flask, jsonify, request, abort
from flask_cors import CORS
from datetime import datetime
from decimal import Decimal
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from extensions import db  
from auth import token_required, generate_token, decode_token, admin_required
from werkzeug.security import check_password_hash
from models import User,Product,Category,Invoice,StockTransaction
from app import db, generate_token 
 # from PyJWT


from extensions import db
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create Flask app
app = Flask(__name__)
CORS(app)

# === CONFIGURE DATABASE TO MATCH DJANGO'S SQLITE ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'db.sqlite3')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_SORT_KEYS'] = False  # Preserve JSON key order

# Initialize SQLAlchemy with the app
db.init_app(app)

# Set up file logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/flask_api.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Flask API startup')

# Custom JSON encoder to handle Decimal and datetime
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

app.json_encoder = CustomJSONEncoder

# Import models AFTER db.init_app(app)
with app.app_context():
    from models import User, Category, Product, StockTransaction, Invoice, InvoiceItem
    db.create_all()

# Request logging middleware
@app.before_request
def log_request_info():
    app.logger.info(f'Request: {request.method} {request.path} from {request.remote_addr}')
    if request.is_json:
        app.logger.debug(f'Request JSON: {request.json}')

# Helper function to convert model to dict
def to_dict(model, exclude=None):
    exclude = exclude or []
    result = {}
    for column in model.__table__.columns:
        if column.name not in exclude:
            result[column.name] = getattr(model, column.name)
    return result

# Error handlers
@app.errorhandler(400)
def bad_request(error):
    app.logger.warning(f'Bad request: {error}')
    return jsonify({'error': 'Bad request', 'message': str(error)}), 400

@app.errorhandler(404)
def not_found(error):
    app.logger.warning(f'Not found: {error}')
    return jsonify({'error': 'Not found', 'message': str(error)}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'Server error: {error}')
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500

# -------------------- Authentication API Endpoints --------------------

@app.route('/api/auth/token', methods=['POST'])
def get_token():
    """Generate a JWT token for a user"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        user = User.query.filter_by(username=username).first()
        if not user:
            user = User.query.filter_by(email=username).first()

        if user and check_password_hash(user.password_hash, password):
            token = generate_token(
                user.id,
                user.username,
                is_staff=user.is_staff,
                is_superuser=user.is_superuser
            )
            return jsonify({
                'token': token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'is_staff': user.is_staff,
                    'is_superuser': user.is_superuser
                }
            })

        return jsonify({'error': 'Invalid credentials'}), 401

    except Exception as e:
        app.logger.error(f"Error in token generation: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500
    
@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_token():
    """Verify a JWT token"""
    return jsonify({
        'valid': True,
        'user': request.user
    })

# -------------------- User API Endpoints --------------------
@app.route('/api/users/register', methods=['POST'])
def register_user():
    """Register a new user"""
    try:
        data = request.json
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400

        user = User(
            username=data['username'],
            email=data['email'],
            is_superuser=False,
            is_staff=False,
            date_joined=datetime.now()
        )
        user.password = data['password'] 

        db.session.add(user)
        db.session.commit()

        token = generate_token(
            user.id,
            user.username,
            is_staff=user.is_staff,
            is_superuser=user.is_superuser
        )
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'token': token
        }), 201

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in user registration: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

# -------------------- Category API Endpoints --------------------
@app.route('/api/categories', methods=['GET'])
@token_required
def get_categories():
    """Get all categories"""
    try:
        categories = Category.query.all()
        return jsonify([to_dict(category) for category in categories])
    except Exception as e:
        app.logger.error(f"Error getting categories: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/categories/<int:id>', methods=['GET'])
@token_required
def get_category(id):
    """Get a category by ID"""
    try:
        category = Category.query.get_or_404(id)
        return jsonify(to_dict(category))
    except Exception as e:
        app.logger.error(f"Error getting category {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/categories', methods=['POST'])
@token_required
def create_category():
    """Create a new category"""
    try:
        data = request.json
        if 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400
        if Category.query.filter_by(name=data['name']).first():
            return jsonify({'error': 'Category with this name already exists'}), 400

        category = Category(
            name=data['name'],
            description=data.get('description'),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.session.add(category)
        db.session.commit()
        app.logger.info(f"Category created: {category.name}")
        return jsonify(to_dict(category)), 201

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating category: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/categories/<int:id>', methods=['PUT'])
@token_required
def update_category(id):
    """Update a category"""
    try:
        category = Category.query.get_or_404(id)
        data = request.json
        if 'name' in data and data['name'] != category.name:
            if Category.query.filter_by(name=data['name']).first():
                return jsonify({'error': 'Category with this name already exists'}), 400
        category.name = data.get('name', category.name)
        category.description = data.get('description', category.description)
        category.updated_at = datetime.now()
        db.session.commit()
        app.logger.info(f"Category updated: {category.name}")
        return jsonify(to_dict(category))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating category {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/categories/<int:id>', methods=['DELETE'])
@token_required
def delete_category(id):
    """Delete a category"""
    try:
        category = Category.query.get_or_404(id)
        products = Product.query.filter_by(category_id=id).count()
        if products > 0:
            return jsonify({
                'error': 'Cannot delete category with products',
                'message': f'This category has {products} products. Remove or reassign them first.'
            }), 400
        db.session.delete(category)
        db.session.commit()
        app.logger.info(f"Category deleted: {category.name}")
        return jsonify({'message': 'Category deleted successfully'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting category {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

# -------------------- Product API Endpoints --------------------
@app.route('/api/products', methods=['GET'])
@token_required
def get_products():
    """Get all products"""
    try:
        products = Product.query.all()
        result = []
        for product in products:
            product_dict = to_dict(product)
            product_dict['is_in_stock'] = product.quantity > 0
            result.append(product_dict)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error getting products: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/products/<int:id>', methods=['GET'])
@token_required
def get_product(id):
    """Get a product by ID"""
    try:
        product = Product.query.get_or_404(id)
        product_dict = to_dict(product)
        product_dict['is_in_stock'] = product.quantity > 0
        return jsonify(product_dict)
    except Exception as e:
        app.logger.error(f"Error getting product {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

# @app.route('/api/products', methods=['POST'])
# @token_required
# def create_product():
#     """Create a new product"""
#     try:
#         data = request.json
#         required_fields = ['name', 'price', 'category_id']
#         for field in required_fields:
#             if field not in data:
#                 return jsonify({'error': f'{field} is required'}), 400
#         category = Category.query.get(data['category_id'])
#         if not category:
#             return jsonify({'error': 'Category does not exist'}), 400
#         product = Product(
#             name=data['name'],
#             description=data.get('description', ''),
#             price=data['price'],
#             quantity=data.get('quantity', 0),
#             category_id=data['category_id'],
#             image=data.get('image'),
#             created_at=datetime.now(),
#             updated_at=datetime.now()
#         )
#         db.session.add(product)
#         db.session.commit()
#         app.logger.info(f"Product created: {product.name}")
#         product_dict = to_dict(product)
#         product_dict['is_in_stock'] = product.quantity > 0
#         return jsonify(product_dict), 201
#     except Exception as e:
#         db.session.rollback()
#         app.logger.error(f"Error creating product: {str(e)}")
#         return jsonify({'error': 'Server error', 'message': str(e)}), 500


@app.route('/api/products', methods=['POST'])
@token_required
def create_product():
    print("Request Headers:")
    for header, value in request.headers.items():
        print(f"{header}: {value}")
    try:
        data = request.get_json()
        required_fields = ['name', 'price', 'category_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        category = Category.query.get(data['category_id'])
        if not category:
            return jsonify({'error': 'Category does not exist'}), 400
        product = Product(
            name=data['name'],
            description=data.get('description', ''),
            price=data['price'],
            quantity=data.get('quantity', 0),
            category_id=data['category_id'],
            image=data.get('image'),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.session.add(product)
        db.session.commit()
        app.logger.info(f"Product created: {product.name}")
        product_dict = to_dict(product)
        product_dict['is_in_stock'] = product.quantity > 0
        return jsonify(product_dict), 201
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating product: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500


@app.route('/api/products/<int:id>', methods=['PUT'])
@token_required
def update_product(id):
    """Update a product"""
    try:
        product = Product.query.get_or_404(id)
        data = request.json
        if 'category_id' in data:
            category = Category.query.get(data['category_id'])
            if not category:
                return jsonify({'error': 'Category does not exist'}), 400
        product.name = data.get('name', product.name)
        product.description = data.get('description', product.description)
        product.price = data.get('price', product.price)
        product.quantity = data.get('quantity', product.quantity)
        product.category_id = data.get('category_id', product.category_id)
        if 'image' in data:
            product.image = data['image']
        product.updated_at = datetime.now()
        db.session.commit()
        app.logger.info(f"Product updated: {product.name}")
        product_dict = to_dict(product)
        product_dict['is_in_stock'] = product.quantity > 0
        return jsonify(product_dict)
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating product {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/products/<int:id>', methods=['DELETE'])
@token_required
def delete_product(id):
    """Delete a product"""
    try:
        product = Product.query.get_or_404(id)
        transactions = StockTransaction.query.filter_by(product_id=id).count()
        invoice_items = InvoiceItem.query.filter_by(product_id=id).count()
        if transactions > 0 or invoice_items > 0:
            return jsonify({
                'error': 'Cannot delete product with transactions or invoices',
                'message': f'This product has {transactions} transactions and appears in {invoice_items} invoices.'
            }), 400
        db.session.delete(product)
        db.session.commit()
        app.logger.info(f"Product deleted: {product.name}")
        return jsonify({'message': 'Product deleted successfully'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting product {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500




# -------------------- Stock Transaction API Endpoints --------------------
@app.route('/api/stock-transactions', methods=['GET'])
@token_required
def get_stock_transactions():
    """Get all stock transactions with optional filtering"""
    try:
        transactions = StockTransaction.query.order_by(StockTransaction.transaction_date.desc()).all()
        
        # Handle filters
        product_id = request.args.get('product')
        if product_id:
            transactions = [t for t in transactions if t.product_id == int(product_id)]
        
        transaction_type = request.args.get('type')
        if transaction_type:
            transactions = [t for t in transactions if t.transaction_type == transaction_type]
        
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            transactions = [t for t in transactions if start <= t.transaction_date.date() <= end]
        
        result = []
        for transaction in transactions:
            transaction_dict = to_dict(transaction)
            # Add product name for convenience
            product = Product.query.get(transaction.product_id)
            if product:
                transaction_dict['product_name'] = product.name
            result.append(transaction_dict)
        
        return jsonify(result)
    
    except Exception as e:
        app.logger.error(f"Error getting stock transactions: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/stock-transactions/<int:id>', methods=['GET'])
@token_required
def get_stock_transaction(id):
    """Get a stock transaction by ID"""
    try:
        transaction = StockTransaction.query.get_or_404(id)
        transaction_dict = to_dict(transaction)
        
        # Add product name for convenience
        product = Product.query.get(transaction.product_id)
        if product:
            transaction_dict['product_name'] = product.name
        
        return jsonify(transaction_dict)
    
    except Exception as e:
        app.logger.error(f"Error getting stock transaction {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/stock-transactions', methods=['POST'])
@token_required
def create_stock_transaction():
    """Create a new stock transaction"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['product_id', 'quantity', 'transaction_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate transaction type
        if data['transaction_type'] not in ['IN', 'OUT']:
            return jsonify({'error': 'Transaction type must be IN or OUT'}), 400
        
        # Check if product exists
        product = Product.query.get(data['product_id'])
        if not product:
            return jsonify({'error': 'Product does not exist'}), 400
        
        # Check if we have enough stock for outgoing transactions
        if data['transaction_type'] == 'OUT':
            if product.quantity < data['quantity']:
                return jsonify({
                    'error': f'Not enough stock for {product.name}. Available: {product.quantity}'
                }), 400
        
        transaction = StockTransaction(
            product_id=data['product_id'],
            quantity=data['quantity'],
            transaction_type=data['transaction_type'],
            transaction_date=datetime.now(),
            notes=data.get('notes', ''),
            created_by_id=request.user.get('user_id')
        )
        
        # Update product quantity
        if data['transaction_type'] == 'IN':
            product.quantity += data['quantity']
        else:  # OUT
            product.quantity -= data['quantity']
        
        db.session.add(transaction)
        db.session.commit()
        
        app.logger.info(f"Stock transaction created: {transaction.transaction_type} for {product.name}")
        
        transaction_dict = to_dict(transaction)
        transaction_dict['product_name'] = product.name
        return jsonify(transaction_dict), 201
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating stock transaction: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

# -------------------- Invoice API Endpoints --------------------
@app.route('/api/invoices', methods=['GET'])
@token_required
def get_invoices():
    """Get all invoices with optional filtering"""
    try:
        invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
        
        # Handle filters
        status = request.args.get('status')
        if status:
            invoices = [i for i in invoices if i.status == status]
        
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            invoices = [i for i in invoices if start <= i.issue_date <= end]
        
        result = []
        for invoice in invoices:
            invoice_dict = to_dict(invoice)
            # Add items count for convenience
            items_count = InvoiceItem.query.filter_by(invoice_id=invoice.id).count()
            invoice_dict['items_count'] = items_count
            result.append(invoice_dict)
        
        return jsonify(result)
    
    except Exception as e:
        app.logger.error(f"Error getting invoices: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/invoices/<int:id>', methods=['GET'])
@token_required
def get_invoice(id):
    """Get an invoice by ID with its items"""
    try:
        invoice = Invoice.query.get_or_404(id)
        invoice_dict = to_dict(invoice)
        
        # Add items
        items = InvoiceItem.query.filter_by(invoice_id=id).all()
        invoice_dict['items'] = []
        
        for item in items:
            item_dict = to_dict(item)
            # Add product name for convenience
            product = Product.query.get(item.product_id)
            if product:
                item_dict['product_name'] = product.name
            invoice_dict['items'].append(item_dict)
        
        return jsonify(invoice_dict)
    
    except Exception as e:
        app.logger.error(f"Error getting invoice {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/invoices', methods=['POST'])
@token_required
def create_invoice():
    """Create a new invoice with items"""
    try:
        data = request.json

        # Validate required fields
        required_fields = ['customer_name', 'issue_date', 'due_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        # Validate items
        if 'items' not in data or not data['items']:
            return jsonify({'error': 'At least one item is required'}), 400

        # Generate invoice number
        last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
        last_id = last_invoice.id if last_invoice else 0
        invoice_number = f"INV-{datetime.now().strftime('%Y%m')}-{last_id + 1:04d}"

        # Create invoice
        invoice = Invoice(
            invoice_number=invoice_number,
            customer_name=data['customer_name'],
            customer_email=data.get('customer_email'),
            customer_phone=data.get('customer_phone'),
            customer_address=data.get('customer_address'),
            issue_date=datetime.strptime(data['issue_date'], '%Y-%m-%d').date(),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date(),
            tax_rate=data.get('tax_rate', 0),
            discount=data.get('discount', 0),
            status=data.get('status', 'DRAFT'),
            notes=data.get('notes', ''),
            created_by_id=request.user.get('user_id'),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(invoice)
        db.session.commit()  # Commit invoice to get its ID

        # Add invoice items
        items_data = data.get('items', [])
        subtotal = 0

        for item_data in items_data:
            # Validate item data
            if 'product_id' not in item_data or 'quantity' not in item_data or 'unit_price' not in item_data:
                db.session.rollback()
                return jsonify({'error': 'Each item must have product_id, quantity, and unit_price'}), 400

            # Check if product exists
            product = Product.query.get(item_data['product_id'])
            if not product:
                db.session.rollback()
                return jsonify({'error': f'Product with ID {item_data["product_id"]} does not exist'}), 400

            # Check stock availability
            if product.quantity < item_data['quantity']:
                db.session.rollback()
                return jsonify({'error': f'Not enough stock for {product.name}. Available: {product.quantity}'}), 400

            # Create invoice item
            item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total=item_data['quantity'] * item_data['unit_price']
            )
            db.session.add(item)

            # Record stock transaction
            transaction = StockTransaction(
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                transaction_type='OUT',
                transaction_date=datetime.now(),
                notes=f'Invoice #{invoice_number}',
                created_by_id=request.user.get('user_id')
            )
            db.session.add(transaction)

            # Update product stock
            product.quantity -= item_data['quantity']

            # Accumulate subtotal
            subtotal += item.total

        # Update invoice totals
        invoice.subtotal = subtotal
        invoice.tax_amount = subtotal * (invoice.tax_rate / 100)
        invoice.total = invoice.subtotal + invoice.tax_amount - invoice.discount

        db.session.commit()

        app.logger.info(f"Invoice created: {invoice.invoice_number}")
        return jsonify(to_dict(invoice)), 201

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating invoice: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500


@app.route('/api/invoices/<int:id>', methods=['PUT'])
@token_required
def update_invoice(id):
    """Update an existing invoice"""
    try:
        invoice = Invoice.query.get_or_404(id)
        
        # Don't allow editing paid invoices
        if invoice.status == 'PAID':
            return jsonify({'error': 'Cannot edit a paid invoice'}), 400
        
        data = request.json
        
        # Update invoice fields
        if 'customer_name' in data:
            invoice.customer_name = data['customer_name']
        if 'customer_email' in data:
            invoice.customer_email = data['customer_email']
        if 'customer_phone' in data:
            invoice.customer_phone = data['customer_phone']
        if 'customer_address' in data:
            invoice.customer_address = data['customer_address']
        if 'issue_date' in data:
            invoice.issue_date = datetime.strptime(data['issue_date'], '%Y-%m-%d').date()
        if 'due_date' in data:
            invoice.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
        if 'tax_rate' in data:
            invoice.tax_rate = data['tax_rate']
        if 'discount' in data:
            invoice.discount = data['discount']
        if 'notes' in data:
            invoice.notes = data['notes']
        
        invoice.updated_at = datetime.now()
        
        # Handle items if provided
        if 'items' in data:
            # Get existing items to restore stock
            existing_items = InvoiceItem.query.filter_by(invoice_id=id).all()
            for item in existing_items:
                # Add the quantities back to inventory
                product = Product.query.get(item.product_id)
                if product:
                    product.quantity += item.quantity
                
                # Create a stock in transaction to log this
                transaction = StockTransaction(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    transaction_type='IN',
                    transaction_date=datetime.now(),
                    notes=f'Invoice #{invoice.invoice_number} item removed',
                    created_by_id=request.user.get('user_id')
                )
                db.session.add(transaction)
            
            # Delete existing items
            InvoiceItem.query.filter_by(invoice_id=id).delete()
            
            # Add new items
            subtotal = 0
            for item_data in data['items']:
                # Validate item data
                if 'product_id' not in item_data or 'quantity' not in item_data or 'unit_price' not in item_data:
                    db.session.rollback()
                    return jsonify({'error': 'Each item must have product_id, quantity, and unit_price'}), 400
                
                # Check if product exists and has enough stock
                product = Product.query.get(item_data['product_id'])
                if not product:
                    db.session.rollback()
                    return jsonify({'error': f'Product with ID {item_data["product_id"]} does not exist'}), 400
                
                if product.quantity < item_data['quantity']:
                    db.session.rollback()
                    return jsonify({
                        'error': f'Not enough stock for {product.name}. Available: {product.quantity}'
                    }), 400
                
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=item_data['product_id'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    total=item_data['quantity'] * item_data['unit_price']
                )
                db.session.add(item)
                
                # Create stock out transaction
                transaction = StockTransaction(
                    product_id=item_data['product_id'],
                    quantity=item_data['quantity'],
                    transaction_type='OUT',
                    transaction_date=datetime.now(),
                    notes=f'Invoice #{invoice.invoice_number} updated',
                    created_by_id=request.user.get('user_id')
                )
                db.session.add(transaction)
                
                # Update product quantity
                product.quantity -= item_data['quantity']
                
                subtotal += item.total
            
            # Update invoice totals
            invoice.subtotal = subtotal
            invoice.tax_amount = subtotal * (invoice.tax_rate / 100)
            invoice.total = subtotal + invoice.tax_amount - invoice.discount
        
        db.session.commit()
        
        app.logger.info(f"Invoice updated: {invoice.invoice_number}")
        
        return jsonify(to_dict(invoice))
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating invoice {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/invoices/<int:id>/status', methods=['PUT'])
@token_required
def update_invoice_status(id):
    """Update invoice status"""
    try:
        invoice = Invoice.query.get_or_404(id)
        data = request.json
        
        if 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400
        
        if data['status'] not in ['DRAFT', 'PAID', 'UNPAID', 'CANCELED']:
            return jsonify({'error': 'Invalid status. Must be DRAFT, PAID, UNPAID, or CANCELED'}), 400
        
        old_status = invoice.status
        invoice.status = data['status']
        invoice.updated_at = datetime.now()
        db.session.commit()
        
        app.logger.info(f"Invoice status updated: {invoice.invoice_number} from {old_status} to {data['status']}")
        
        return jsonify({
            'message': f'Invoice status updated from {old_status} to {data["status"]}',
            'invoice': to_dict(invoice)
        })
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating invoice status {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/invoices/<int:id>', methods=['DELETE'])
@token_required
def delete_invoice(id):
    """Delete an invoice"""
    try:
        invoice = Invoice.query.get_or_404(id)
        
        # Restore stock quantities if the invoice was not canceled
        if invoice.status != 'CANCELED':
            items = InvoiceItem.query.filter_by(invoice_id=id).all()
            for item in items:
                # Add the quantities back to inventory
                product = Product.query.get(item.product_id)
                if product:
                    product.quantity += item.quantity
                
                # Create a stock in transaction to log this
                transaction = StockTransaction(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    transaction_type='IN',
                    transaction_date=datetime.now(),
                    notes=f'Invoice #{invoice.invoice_number} deleted',
                    created_by_id=request.user.get('user_id')
                )
                db.session.add(transaction)
        
        # Delete invoice items first
        InvoiceItem.query.filter_by(invoice_id=id).delete()
        
        # Then delete the invoice
        db.session.delete(invoice)
        db.session.commit()
        
        app.logger.info(f"Invoice deleted: {invoice.invoice_number}")
        
        return jsonify({'message': 'Invoice deleted successfully'})
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting invoice {id}: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

# -------------------- Product Info API Endpoint --------------------
@app.route('/api/product-info', methods=['GET'])
@token_required
def get_product_info():
    """Get product info for invoice creation"""
    try:
        product_id = request.args.get('product_id')
        if not product_id:
            return jsonify({'success': False, 'error': 'Product ID is required'}), 400
        
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        return jsonify({
            'success': True,
            'price': float(product.price),
            'available': product.quantity
        })
    
    except Exception as e:
        app.logger.error(f"Error getting product info: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# -------------------- Dashboard Data API Endpoint --------------------
@app.route('/api/dashboard-data', methods=['GET'])
@token_required
def get_dashboard_data():
    """Get dashboard data for charts and stats"""
    try:
        # Basic stats
        products_count = Product.query.count()
        categories_count = Category.query.count()
        low_stock_products = Product.query.filter(Product.quantity < 10).count()
        
        # Product quantity by category for pie chart
        category_data = []
        categories = Category.query.all()
        for category in categories:
            products = Product.query.filter_by(category_id=category.id).all()
            total_quantity = sum(p.quantity for p in products)
            category_data.append({
                'name': category.name,
                'total_quantity': total_quantity
            })
        
        # Stock transactions for the last 7 days
        today = datetime.now().date()
        seven_days_ago = today - timedelta(days=7)
        
        dates = []
        stock_in = []
        stock_out = []
        
        for i in range(7):
            date = seven_days_ago + timedelta(days=i)
            dates.append(date.strftime('%Y-%m-%d'))
            
            # Find stock in for this date
            in_transactions = StockTransaction.query.filter(
                StockTransaction.transaction_date >= datetime.combine(date, datetime.min.time()),
                StockTransaction.transaction_date < datetime.combine(date + timedelta(days=1), datetime.min.time()),
                StockTransaction.transaction_type == 'IN'
            ).all()
            in_value = sum(t.quantity for t in in_transactions)
            stock_in.append(in_value)
            
            # Find stock out for this date
            out_transactions = StockTransaction.query.filter(
                StockTransaction.transaction_date >= datetime.combine(date, datetime.min.time()),
                StockTransaction.transaction_date < datetime.combine(date + timedelta(days=1), datetime.min.time()),
                StockTransaction.transaction_type == 'OUT'
            ).all()
            out_value = sum(t.quantity for t in out_transactions)
            stock_out.append(out_value)
        
        # Recent transactions
        recent_transactions = StockTransaction.query.order_by(StockTransaction.transaction_date.desc()).limit(5).all()
        recent_transactions_data = []
        for transaction in recent_transactions:
            transaction_dict = to_dict(transaction)
            product = Product.query.get(transaction.product_id)
            if product:
                transaction_dict['product_name'] = product.name
            recent_transactions_data.append(transaction_dict)
        
        # Recent invoices
        recent_invoices = Invoice.query.order_by(Invoice.created_at.desc()).limit(5).all()
        recent_invoices_data = [to_dict(invoice) for invoice in recent_invoices]
        
        return jsonify({
            'products_count': products_count,
            'categories_count': categories_count,
            'low_stock_products': low_stock_products,
            'category_data': category_data,
            'dates': dates,
            'stock_in': stock_in,
            'stock_out': stock_out,
            'recent_transactions': recent_transactions_data,
            'recent_invoices': recent_invoices_data
        })
    
    except Exception as e:
        app.logger.error(f"Error getting dashboard data: {str(e)}")
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
    app.run(debug=True, port=5000)
