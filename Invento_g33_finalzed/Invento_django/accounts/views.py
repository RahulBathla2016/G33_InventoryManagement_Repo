from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
import json
import datetime
import logging
from django.contrib.auth.models import User 
from .forms import (
    SignUpForm, LoginForm, ProductForm, CategoryForm,
    StockTransactionForm, InvoiceForm, InvoiceItemFormSet
)
from .models import Product, Category, StockTransaction, Invoice, InvoiceItem
from .api_client import api_request, generate_token

# Configure logging
logger = logging.getLogger(__name__)

def signup(request):
    """Register a new user"""
    # Redirect to dashboard if already logged in
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                # Create user in Django for authentication
                user = form.save(commit=False)
                user.is_superuser = False
                user.is_staff = False
                user.save()
                
                # Register user in Flask API
                api_data = {
                    'username': user.username,
                    'email': user.email,
                    'password': form.cleaned_data.get('password1')  # In real app, use secure method
                }
                response, status_code = api_request('POST', 'users/register', api_data)
                
                if status_code >= 400:
                    logger.error(f"API Error during signup: {response.get('error', 'Unknown error')}")
                    messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                    user.delete()  # Rollback Django user creation
                    return render(request, 'accounts/signup.html', {'form': form})
                
                # Log the user in
                login(request, user)
                logger.info(f"User {user.username} registered successfully")
                messages.success(request, "Account created successfully!")
                return redirect('dashboard')
            except Exception as e:
                logger.error(f"Error during signup: {str(e)}")
                messages.error(request, f"An error occurred: {str(e)}")
        else:
            logger.warning(f"Invalid signup form: {form.errors}")
            messages.error(request, "Error creating account. Please check the form.")
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})

def login_view(request):
    """Log in a user by authenticating against the Flask API."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')

            try:
                # Authenticate with Flask API
                api_data = {'username': username, 'password': password}
                response, status_code = api_request('POST', 'auth/token', data=api_data)

                if status_code >= 400:
                    logger.warning(f"Failed login attempt for user {username} (API error: {response.get('error', 'Unknown error')})")
                    messages.error(request, "Invalid username/email or password.")
                    return render(request, 'accounts/login.html', {'form': form})

                # Flask API authentication was successful
                api_data = response
                token = api_data.get('token')
                user_data = api_data.get('user')

                if token and user_data:
                    # Find or create the user in the Django database
                    try:
                        user = User.objects.get(username=user_data['username'])
                    except User.DoesNotExist:
                        user = User.objects.create_user(
                            username=user_data['username'],
                            email=user_data.get('email', ''),
                            password=password  # You might not need to set the password again if Flask is the source of truth
                        )
                        logger.info(f"Created user {user.username} in Django database after successful Flask login")

                    # Log the user in to Django
                    login(request, user)
                    request.session['flask_token'] = token  # Store the Flask token
                    logger.info(f"User {user.username} logged in successfully via Flask API")
                    messages.success(request, f"Welcome back, {user.username}!")

                    next_url = request.GET.get('next')
                    if next_url:
                        return redirect(next_url)
                    return redirect('dashboard')
                else:
                    logger.error("Flask API returned invalid login response data")
                    messages.error(request, "Authentication failed: Invalid data from API.")
                    return render(request, 'accounts/login.html', {'form': form})

            except Exception as e:
                logger.error(f"Error during login: {str(e)}")
                messages.error(request, f"An error occurred during login: {str(e)}")
        else:
            logger.warning(f"Invalid login form: {form.errors}")
            messages.error(request, "Invalid form submission.")

    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})
def logout_view(request):
    """Log out a user"""
    logout(request)
    logger.info(f"User {request.user.username if hasattr(request, 'user') else 'Unknown'} logged out")
    messages.info(request, "You have been logged out.")
    return redirect('login')

def home(request):
    """Home page - redirect to dashboard or login"""
    # Redirect to dashboard if authenticated, otherwise to login
    if request.user.is_authenticated:
        return redirect('dashboard')
    else:
        return redirect('login')

@login_required
def dashboard(request):
    """Main dashboard view with enhanced data for charts"""
    try:
        # Get dashboard data from Flask API
        token = generate_token(request.user)  # Generate token
        response, status_code = api_request('GET', 'dashboard-data', token=token)  # Use token instead of user
        
        if status_code >= 400:
            logger.error(f"API Error getting dashboard data: {response.get('error', 'Unknown error')}")
            messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            context = {
                'is_superuser': request.user.is_superuser,
                'is_staff': request.user.is_staff,
            }
            return render(request, 'dashboard/index.html', context)
        
        # Add user info to context
        response['is_superuser'] = request.user.is_superuser
        response['is_staff'] = request.user.is_staff
        
        return render(request, 'dashboard/index.html', response)
    except Exception as e:
        logger.error(f"Error in dashboard view: {str(e)}")
        messages.error(request, f"An error occurred: {str(e)}")
        return render(request, 'dashboard/index.html', {
            'is_superuser': request.user.is_superuser,
            'is_staff': request.user.is_staff,
        })

# Category Views
@login_required
def category_list(request):
    """List all categories"""
    try:
        token = generate_token(request.user)
        response, status_code = api_request('GET', 'categories', token=token)
        
        if status_code >= 400:
            logger.error(f"API Error getting categories: {response.get('error', 'Unknown error')}")
            messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            return render(request, 'dashboard/category/category_list.html', {'categories': []})
        
        # Debug the response
        logger.info(f"Categories response type: {type(response)}")
        logger.info(f"Categories response: {response}")
        
        # Convert the response to a list of Category objects for the template
        category_objects = []
        if isinstance(response, list):
            for cat_data in response:
                category = Category(
                    id=cat_data.get('id'),
                    name=cat_data.get('name'),
                    description=cat_data.get('description', ''),
                    created_at=datetime.datetime.fromisoformat(cat_data.get('created_at')) if cat_data.get('created_at') else datetime.datetime.now()
                )
                # Add a dummy products count property
                category.products = {'count': 0}
                category_objects.append(category)
        
        return render(request, 'dashboard/category/category_list.html', {'categories': category_objects})
    except Exception as e:
        logger.error(f"Error in category_list view: {str(e)}")
        messages.error(request, f"An error occurred: {str(e)}")
        return render(request, 'dashboard/category/category_list.html', {'categories': []})

@login_required
def category_create(request):
    """Create a new category"""
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            try:
                token = generate_token(request.user) # Get the token
                api_data = {
                    'name': form.cleaned_data['name'],
                    'description': form.cleaned_data['description']
                }
                print(f"Sending data to Flask: {api_data}")  
                response, status_code = api_request('POST', 'categories', api_data, token=token) # Include the token
                
                if status_code >= 400:
                    logger.error(f"API Error creating category: {response.get('error', 'Unknown error')}")
                    messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                    return render(request, 'dashboard/category/category_form.html', {'form': form})
                
                logger.info(f"Category created: {form.cleaned_data['name']}")
                messages.success(request, 'Category created successfully!')
                return redirect('category_list')
            except Exception as e:
                logger.error(f"Error creating category: {str(e)}")
                messages.error(request, f"An error occurred: {str(e)}")
                return render(request, 'dashboard/category/category_form.html', {'form': form})
    else:
        form = CategoryForm()
    
    return render(request, 'dashboard/category/category_form.html', {'form': form})

@login_required
def category_update(request, pk):
    """Update an existing category"""
    token = generate_token(request.user) # Get the token
    response, status_code = api_request('GET', f'categories/{pk}', token=token) # Include the token
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('category_list')
    
    category = response
    
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            api_data = {
                'name': form.cleaned_data['name'],
                'description': form.cleaned_data['description']
            }
            token = generate_token(request.user) # Get the token
            response, status_code = api_request('PUT', f'categories/{pk}', api_data, token=token) # Include the token
            
            if status_code >= 400:
                messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                return render(request, 'dashboard/category/category_form.html', {'form': form, 'category': category})
            
            messages.success(request, 'Category updated successfully!')
            return redirect('category_list')
    else:
        form = CategoryForm(initial={
            'name': category['name'],
            'description': category['description']
        })
    
    return render(request, 'dashboard/category/category_form.html', {'form': form, 'category': category})

@login_required
def category_delete(request, pk):
    """Delete a category"""
    token = generate_token(request.user) # Get the token
    response, status_code = api_request('GET', f'categories/{pk}', token=token) # Include the token
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('category_list')
    
    category = response
    
    if request.method == 'POST':
        token = generate_token(request.user) # Get the token
        response, status_code = api_request('DELETE', f'categories/{pk}', token=token) # Include the token
        
        if status_code >= 400:
            messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            return render(request, 'dashboard/category/category_delete.html', {'category': category})
        
        messages.success(request, 'Category deleted successfully!')
        return redirect('category_list')
    
    return render(request, 'dashboard/category/category_delete.html', {'category': category})




# Product Views
@login_required
def product_list(request):
    """List all products"""
    try:
        token = generate_token(request.user)
        response, status_code = api_request('GET', 'products', token=token)
        
        if status_code >= 400:
            logger.error(f"API Error getting products: {response.get('error', 'Unknown error')}")
            messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            return render(request, 'dashboard/product/product_list.html', {'products': []})
        
        # Debug the response
        logger.info(f"Products response type: {type(response)}")
        logger.info(f"Products response: {response}")
        
        # Convert the response to a list of Product objects for the template
        product_objects = []
        if isinstance(response, list):
            for prod_data in response:
                product = Product(
                    id=prod_data.get('id'),
                    name=prod_data.get('name'),
                    description=prod_data.get('description', ''),
                    price=prod_data.get('price', 0),
                    quantity=prod_data.get('quantity', 0),
                    category_id=prod_data.get('category_id'),
                    image=prod_data.get('image')
                )
                
                # Get category info
                cat_response, cat_status = api_request('GET', f'categories/{prod_data.get("category_id")}', token=token)
                if cat_status < 400 and cat_response:
                    category = Category(
                        id=cat_response.get('id'),
                        name=cat_response.get('name')
                    )
                    product.category = category
                else:
                    # Create a dummy category if we can't get the real one
                    product.category = Category(id=0, name="Unknown")
                
                # Set is_in_stock property
                product.is_in_stock = prod_data.get('is_in_stock', product.quantity > 0)
                
                product_objects.append(product)
        
        return render(request, 'dashboard/product/product_list.html', {'products': product_objects})
    except Exception as e:
        logger.error(f"Error in product_list view: {str(e)}")
        messages.error(request, f"An error occurred: {str(e)}")
        return render(request, 'dashboard/product/product_list.html', {'products': []})

@login_required
def product_create(request):
    """Create a new product"""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            # Handle file upload separately
            image_path = None
            if 'image' in request.FILES:
                # In a real app, you'd upload the file to a storage service
                # and get a URL back. For simplicity, we'll just use a placeholder.
                image_path = '/media/products/placeholder.jpg'
            
            # Send data to Flask API
            api_data = {
                'name': form.cleaned_data['name'],
                'description': form.cleaned_data['description'],
                'price': float(form.cleaned_data['price']),
                'quantity': form.cleaned_data['quantity'],
                'category_id': form.cleaned_data['category'].id,
                'image': image_path
            }
            response, status_code = api_request('POST', 'products', api_data)
            
            if status_code >= 400:
                messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                return render(request, 'dashboard/product/product_form.html', {'form': form})
            
            messages.success(request, 'Product created successfully!')
            return redirect('product_list')
        else:
            messages.error(request, 'Please correct the error(s) below.')
    else:
        form = ProductForm()

    return render(request, 'dashboard/product/product_form.html', {'form': form})

@login_required
def product_update(request, pk):
    """Update an existing product"""
    # Get product from Flask API
    response, status_code = api_request('GET', f'products/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('product_list')
    
    product_data = response
    
    # Create a Product object for the form
    product = Product(
        id=product_data['id'],
        name=product_data['name'],
        description=product_data['description'],
        price=product_data['price'],
        quantity=product_data['quantity'],
        category_id=product_data['category_id'],
        image=product_data.get('image')
    )
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            # Handle file upload separately
            image_path = product_data.get('image')
            if 'image' in request.FILES:
                # In a real app, you'd upload the file to a storage service
                # and get a URL back. For simplicity, we'll just use a placeholder.
                image_path = '/media/products/placeholder.jpg'
            
            # Send data to Flask API
            api_data = {
                'name': form.cleaned_data['name'],
                'description': form.cleaned_data['description'],
                'price': float(form.cleaned_data['price']),
                'quantity': form.cleaned_data['quantity'],
                'category_id': form.cleaned_data['category'].id
            }
            
            if image_path:
                api_data['image'] = image_path
            
            response, status_code = api_request('PUT', f'products/{pk}', api_data)
            
            if status_code >= 400:
                messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                return render(request, 'dashboard/product/product_form.html', {'form': form, 'product': product})
            
            messages.success(request, 'Product updated successfully!')
            return redirect('product_list')
        else:
            messages.error(request, 'Please correct the error(s) below.')
    else:
        # Get category for the form
        category_response, _ = api_request('GET', f'categories/{product_data["category_id"]}')
        category = Category(
            id=category_response['id'],
            name=category_response['name']
        )
        product.category = category
        
        form = ProductForm(instance=product)

    return render(request, 'dashboard/product/product_form.html', {'form': form, 'product': product})

@login_required
def product_delete(request, pk):
    """Delete a product"""
    # Get product from Flask API
    response, status_code = api_request('GET', f'products/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('product_list')
    
    product_data = response
    
    # Create a Product object for the template
    product = Product(
        id=product_data['id'],
        name=product_data['name'],
        description=product_data['description'],
        price=product_data['price'],
        quantity=product_data['quantity'],
        category_id=product_data['category_id'],
        image=product_data.get('image')
    )
    
    if request.method == 'POST':
        # Send delete request to Flask API
        response, status_code = api_request('DELETE', f'products/{pk}')
        
        if status_code >= 400:
            messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            return render(request, 'dashboard/product/product_delete.html', {'product': product})
        
        messages.success(request, 'Product deleted successfully!')
        return redirect('product_list')

    return render(request, 'dashboard/product/product_delete.html', {'product': product})

@login_required
def product_detail(request, pk):
    """View product details"""
    # Get product from Flask API
    response, status_code = api_request('GET', f'products/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('product_list')
    
    product_data = response
    
    # Create a Product object for the template
    product = Product(
        id=product_data['id'],
        name=product_data['name'],
        description=product_data['description'],
        price=product_data['price'],
        quantity=product_data['quantity'],
        category_id=product_data['category_id'],
        image=product_data.get('image')
    )
    
    return render(request, 'dashboard/product/product_detail.html', {'product': product})

# Stock Transaction Views
@login_required
def stock_transaction_list(request):
    """List all stock transactions"""
    # Prepare filter parameters
    params = {}
    
    product_id = request.GET.get('product')
    if product_id:
        params['product'] = product_id
    
    transaction_type = request.GET.get('type')
    if transaction_type:
        params['type'] = transaction_type
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date and end_date:
        params['start_date'] = start_date
        params['end_date'] = end_date
    
    # Get transactions from Flask API
    response, status_code = api_request('GET', 'stock-transactions', params=params)
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return render(request, 'dashboard/stock/transaction_list.html', {'transactions': []})
    
    # Get products for filter dropdown
    products_response, _ = api_request('GET', 'products')
    
    # Pagination (client-side for simplicity)
    page = int(request.GET.get('page', 1))
    per_page = 10
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    transactions_page = response[start_idx:end_idx]
    total_pages = (len(response) + per_page - 1) // per_page
    
    context = {
        'transactions': transactions_page,
        'products': products_response,
        'page': page,
        'total_pages': total_pages,
        'has_previous': page > 1,
        'has_next': page < total_pages,
        'previous_page': page - 1,
        'next_page': page + 1,
    }
    
    return render(request, 'dashboard/stock/transaction_list.html', context)

@login_required
def stock_transaction_create(request):
    """Create a new stock transaction"""
    if request.method == 'POST':
        form = StockTransactionForm(request.POST)
        if form.is_valid():
            # Send data to Flask API
            api_data = {
                'product_id': form.cleaned_data['product'].id,
                'quantity': form.cleaned_data['quantity'],
                'transaction_type': form.cleaned_data['transaction_type'],
                'notes': form.cleaned_data['notes'],
                'created_by_id': request.user.id
            }
            response, status_code = api_request('POST', 'stock-transactions', api_data)
            
            if status_code >= 400:
                messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                return render(request, 'dashboard/stock/transaction_form.html', {'form': form})
            
            messages.success(request, 'Stock transaction recorded successfully!')
            return redirect('stock_transaction_list')
    else:
        # Pre-fill product if provided in URL
        product_id = request.GET.get('product')
        if product_id:
            # Get product from Flask API
            product_response, status_code = api_request('GET', f'products/{product_id}')
            
            if status_code >= 400:
                messages.error(request, f"API Error: {product_response.get('error', 'Unknown error')}")
                form = StockTransactionForm()
            else:
                # Create a Product object for the form
                product = Product(
                    id=product_response['id'],
                    name=product_response['name']
                )
                form = StockTransactionForm(initial={'product': product})
        else:
            form = StockTransactionForm()
    
    return render(request, 'dashboard/stock/transaction_form.html', {'form': form})

@login_required
def stock_transaction_detail(request, pk):
    """View details of a stock transaction"""
    # Get transaction from Flask API
    response, status_code = api_request('GET', f'stock-transactions/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('stock_transaction_list')
    
    transaction_data = response
    
    # Create a StockTransaction object for the template
    transaction = StockTransaction(
        id=transaction_data['id'],
        product_id=transaction_data['product_id'],
        quantity=transaction_data['quantity'],
        transaction_type=transaction_data['transaction_type'],
        transaction_date=datetime.datetime.fromisoformat(transaction_data['transaction_date']),
        notes=transaction_data['notes'],
        created_by_id=transaction_data['created_by_id']
    )
    
    # Add product name
    transaction.product_name = transaction_data.get('product_name', 'Unknown Product')
    
    return render(request, 'dashboard/stock/transaction_detail.html', {'transaction': transaction})

# Invoice Views
@login_required
def invoice_list(request):
    """List all invoices"""
    # Prepare filter parameters
    params = {}
    
    status = request.GET.get('status')
    if status:
        params['status'] = status
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date and end_date:
        params['start_date'] = start_date
        params['end_date'] = end_date
    
    # Get invoices from Flask API
    response, status_code = api_request('GET', 'invoices', params=params)
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return render(request, 'dashboard/invoice/invoice_list.html', {'invoices': []})
    
    # Pagination (client-side for simplicity)
    page = int(request.GET.get('page', 1))
    per_page = 10
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    invoices_page = response[start_idx:end_idx]
    total_pages = (len(response) + per_page - 1) // per_page
    
    context = {
        'invoices': invoices_page,
        'page': page,
        'total_pages': total_pages,
        'has_previous': page > 1,
        'has_next': page < total_pages,
        'previous_page': page - 1,
        'next_page': page + 1,
    }
    
    return render(request, 'dashboard/invoice/invoice_list.html', context)

@login_required
def invoice_create(request):
    """Create a new invoice"""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            formset = InvoiceItemFormSet(request.POST)
            if formset.is_valid():
                # Prepare invoice data for API
                api_data = {
                    'customer_name': form.cleaned_data['customer_name'],
                    'customer_email': form.cleaned_data['customer_email'],
                    'customer_phone': form.cleaned_data['customer_phone'],
                    'customer_address': form.cleaned_data['customer_address'],
                    'issue_date': form.cleaned_data['issue_date'].strftime('%Y-%m-%d'),
                    'due_date': form.cleaned_data['due_date'].strftime('%Y-%m-%d'),
                    'tax_rate': float(form.cleaned_data['tax_rate']),
                    'discount': float(form.cleaned_data['discount']),
                    'notes': form.cleaned_data['notes'],
                    'created_by_id': request.user.id,
                    'items': []
                }
                
                # Add invoice items
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                        item_data = {
                            'product_id': form.cleaned_data['product'].id,
                            'quantity': form.cleaned_data['quantity'],
                            'unit_price': float(form.cleaned_data['unit_price'])
                        }
                        api_data['items'].append(item_data)
                
                # Send data to Flask API
                response, status_code = api_request('POST', 'invoices', api_data)
                
                if status_code >= 400:
                    messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                    return render(request, 'dashboard/invoice/invoice_form.html', {
                        'form': form,
                        'formset': formset,
                        'products': Product.objects.filter(quantity__gt=0)
                    })
                
                messages.success(request, f'Invoice #{response["invoice_number"]} created successfully!')
                return redirect('invoice_detail', pk=response['id'])
            else:
                messages.error(request, 'Error in invoice items. Please check the form.')
        else:
            messages.error(request, 'Error in invoice form. Please check the form.')
    else:
        form = InvoiceForm(initial={
            'issue_date': timezone.now().date(),
            'due_date': timezone.now().date() + datetime.timedelta(days=30),
        })
        formset = InvoiceItemFormSet()
    
    # Get products with stock
    products_response, _ = api_request('GET', 'products')
    products = [p for p in products_response if p['quantity'] > 0]
    
    context = {
        'form': form,
        'formset': formset,
        'products': products
    }
    
    return render(request, 'dashboard/invoice/invoice_form.html', context)

@login_required
def invoice_detail(request, pk):
    """View details of an invoice"""
    # Get invoice from Flask API
    response, status_code = api_request('GET', f'invoices/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('invoice_list')
    
    invoice_data = response
    
    # Create an Invoice object for the template
    invoice = Invoice(
        id=invoice_data['id'],
        invoice_number=invoice_data['invoice_number'],
        customer_name=invoice_data['customer_name'],
        customer_email=invoice_data['customer_email'],
        customer_phone=invoice_data['customer_phone'],
        customer_address=invoice_data['customer_address'],
        issue_date=datetime.datetime.strptime(invoice_data['issue_date'], '%Y-%m-%d').date(),
        due_date=datetime.datetime.strptime(invoice_data['due_date'], '%Y-%m-%d').date(),
        subtotal=invoice_data['subtotal'],
        tax_rate=invoice_data['tax_rate'],
        tax_amount=invoice_data['tax_amount'],
        discount=invoice_data['discount'],
        total=invoice_data['total'],
        status=invoice_data['status'],
        notes=invoice_data['notes'],
        created_by_id=invoice_data['created_by_id'],
        created_at=datetime.datetime.fromisoformat(invoice_data['created_at']),
        updated_at=datetime.datetime.fromisoformat(invoice_data['updated_at'])
    )
    
    # Add items to invoice
    invoice.items = []
    for item_data in invoice_data['items']:
        item = InvoiceItem(
            id=item_data['id'],
            invoice_id=invoice.id,
            product_id=item_data['product_id'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            total=item_data['total']
        )
        item.product_name = item_data.get('product_name', 'Unknown Product')
        invoice.items.append(item)
    
    return render(request, 'dashboard/invoice/invoice_detail.html', {'invoice': invoice})

@login_required
def invoice_edit(request, pk):
    """Edit an existing invoice"""
    # Get invoice from Flask API
    response, status_code = api_request('GET', f'invoices/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('invoice_list')
    
    invoice_data = response
    
    # Don't allow editing paid invoices
    if invoice_data['status'] == 'PAID':
        messages.error(request, 'Cannot edit a paid invoice!')
        return redirect('invoice_detail', pk=pk)
    
    # Create an Invoice object for the form
    invoice = Invoice(
        id=invoice_data['id'],
        invoice_number=invoice_data['invoice_number'],
        customer_name=invoice_data['customer_name'],
        customer_email=invoice_data['customer_email'],
        customer_phone=invoice_data['customer_phone'],
        customer_address=invoice_data['customer_address'],
        issue_date=datetime.datetime.strptime(invoice_data['issue_date'], '%Y-%m-%d').date(),
        due_date=datetime.datetime.strptime(invoice_data['due_date'], '%Y-%m-%d').date(),
        tax_rate=invoice_data['tax_rate'],
        discount=invoice_data['discount'],
        notes=invoice_data['notes']
    )
    
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            formset = InvoiceItemFormSet(request.POST, instance=invoice)
            if formset.is_valid():
                # Prepare invoice data for API
                api_data = {
                    'customer_name': form.cleaned_data['customer_name'],
                    'customer_email': form.cleaned_data['customer_email'],
                    'customer_phone': form.cleaned_data['customer_phone'],
                    'customer_address': form.cleaned_data['customer_address'],
                    'issue_date': form.cleaned_data['issue_date'].strftime('%Y-%m-%d'),
                    'due_date': form.cleaned_data['due_date'].strftime('%Y-%m-%d'),
                    'tax_rate': float(form.cleaned_data['tax_rate']),
                    'discount': float(form.cleaned_data['discount']),
                    'notes': form.cleaned_data['notes'],
                    'items': []
                }
                
                # Add invoice items
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                        item_data = {
                            'product_id': form.cleaned_data['product'].id,
                            'quantity': form.cleaned_data['quantity'],
                            'unit_price': float(form.cleaned_data['unit_price'])
                        }
                        api_data['items'].append(item_data)
                
                # Send data to Flask API
                response, status_code = api_request('PUT', f'invoices/{pk}', api_data)
                
                if status_code >= 400:
                    messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
                    return render(request, 'dashboard/invoice/invoice_form.html', {
                        'form': form,
                        'formset': formset,
                        'invoice': invoice,
                        'products': Product.objects.filter(quantity__gt=0)
                    })
                
                messages.success(request, f'Invoice #{invoice_data["invoice_number"]} updated successfully!')
                return redirect('invoice_detail', pk=pk)
            else:
                messages.error(request, 'Error in invoice items. Please check the form.')
        else:
            messages.error(request, 'Error in invoice form. Please check the form.')
    else:
        form = InvoiceForm(instance=invoice)
        
        # Create formset with items from API
        initial_items = []
        for item_data in invoice_data['items']:
            # Get product for the form
            product_response, _ = api_request('GET', f'products/{item_data["product_id"]}')
            product = Product(
                id=product_response['id'],
                name=product_response['name']
            )
            
            initial_items.append({
                'product': product,
                'quantity': item_data['quantity'],
                'unit_price': item_data['unit_price']
            })
        
        formset = InvoiceItemFormSet(initial=initial_items)
    
    # Get products with stock
    products_response, _ = api_request('GET', 'products')
    products = [p for p in products_response if p['quantity'] > 0]
    
    context = {
        'form': form,
        'formset': formset,
        'invoice': invoice,
        'products': products
    }
    
    return render(request, 'dashboard/invoice/invoice_form.html', context)

@login_required
def invoice_delete(request, pk):
    """Delete an invoice"""
    # Get invoice from Flask API
    response, status_code = api_request('GET', f'invoices/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('invoice_list')
    
    invoice_data = response
    
    # Create an Invoice object for the template
    invoice = Invoice(
        id=invoice_data['id'],
        invoice_number=invoice_data['invoice_number'],
        customer_name=invoice_data['customer_name'],
        status=invoice_data['status']
    )
    
    if request.method == 'POST':
        # Send delete request to Flask API
        response, status_code = api_request('DELETE', f'invoices/{pk}')
        
        if status_code >= 400:
            messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            return render(request, 'dashboard/invoice/invoice_delete.html', {'invoice': invoice})
        
        messages.success(request, 'Invoice deleted successfully!')
        return redirect('invoice_list')
    
    return render(request, 'dashboard/invoice/invoice_delete.html', {'invoice': invoice})

@login_required
def invoice_print(request, pk):
    """Print an invoice"""
    # Get invoice from Flask API
    response, status_code = api_request('GET', f'invoices/{pk}')
    
    if status_code >= 400:
        messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
        return redirect('invoice_list')
    
    invoice_data = response
    
    # Create an Invoice object for the template
    invoice = Invoice(
        id=invoice_data['id'],
        invoice_number=invoice_data['invoice_number'],
        customer_name=invoice_data['customer_name'],
        customer_email=invoice_data['customer_email'],
        customer_phone=invoice_data['customer_phone'],
        customer_address=invoice_data['customer_address'],
        issue_date=datetime.datetime.strptime(invoice_data['issue_date'], '%Y-%m-%d').date(),
        due_date=datetime.datetime.strptime(invoice_data['due_date'], '%Y-%m-%d').date(),
        subtotal=invoice_data['subtotal'],
        tax_rate=invoice_data['tax_rate'],
        tax_amount=invoice_data['tax_amount'],
        discount=invoice_data['discount'],
        total=invoice_data['total'],
        status=invoice_data['status'],
        notes=invoice_data['notes']
    )
    
    # Add items to invoice
    invoice.items = []
    for item_data in invoice_data['items']:
        item = InvoiceItem(
            id=item_data['id'],
            invoice_id=invoice.id,
            product_id=item_data['product_id'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            total=item_data['total']
        )
        item.product_name = item_data.get('product_name', 'Unknown Product')
        invoice.items.append(item)
    
    return render(request, 'dashboard/invoice/invoice_print.html', {'invoice': invoice})

@login_required
def invoice_status_update(request, pk):
    """Update invoice status"""
    if request.method == 'POST':
        status = request.POST.get('status')
        
        if status in dict(Invoice.STATUS_CHOICES):
            # Send status update to Flask API
            api_data = {'status': status}
            response, status_code = api_request('PUT', f'invoices/{pk}/status', api_data)
            
            if status_code >= 400:
                messages.error(request, f"API Error: {response.get('error', 'Unknown error')}")
            else:
                messages.success(request, response['message'])
        else:
            messages.error(request, 'Invalid status!')
        
        return redirect('invoice_detail', pk=pk)
    
    return redirect('invoice_list')

# Product availability for invoice items
@login_required
def get_product_info(request):
    """Get product info for invoice creation"""
    if request.method == 'GET':
        try:
            product_id = request.GET.get('product_id')
            if product_id:
                # Get product info from Flask API
                token = generate_token(request.user)  # Generate token
                params = {'product_id': product_id}
                response, status_code = api_request('GET', 'product-info', params=params, token=token)  # Use token instead of user
                
                if status_code >= 400:
                    logger.error(f"API Error getting product info: {response.get('error', 'Unknown error')}")
                    return JsonResponse({'success': False, 'error': response.get('error', 'Unknown error')})
                
                return JsonResponse(response)
            else:
                return JsonResponse({'success': False, 'error': 'Product ID is required'})
        except Exception as e:
            logger.error(f"Error getting product info: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})
