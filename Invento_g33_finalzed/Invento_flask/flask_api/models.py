from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app

# User model (simplified version of Django's auth_user)
class User(db.Model):
    __tablename__ = 'auth_user'
    
    id = db.Column(db.Integer, primary_key=True)
    password_hash = db.Column(db.String(128))
    last_login = db.Column(db.DateTime, nullable=True)
    is_superuser = db.Column(db.Boolean, default=False)
    username = db.Column(db.String(150), unique=True)
    first_name = db.Column(db.String(150))
    last_name = db.Column(db.String(150))
    email = db.Column(db.String(254))
    is_staff = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    date_joined = db.Column(db.DateTime, default=datetime.now)
    
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    pass

# Category model
class Category(db.Model):
    __tablename__ = 'accounts_category'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

# Product model
class Product(db.Model):
    __tablename__ = 'accounts_product'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2))
    quantity = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('accounts_category.id'))
    image = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

# StockTransaction model
class StockTransaction(db.Model):
    __tablename__ = 'accounts_stocktransaction'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('accounts_product.id'))
    quantity = db.Column(db.Integer)
    transaction_type = db.Column(db.String(3))  # 'IN' or 'OUT'
    transaction_date = db.Column(db.DateTime, default=datetime.now)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('auth_user.id'), nullable=True)

# Invoice model
class Invoice(db.Model):
    __tablename__ = 'accounts_invoice'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True)
    customer_name = db.Column(db.String(200))
    customer_email = db.Column(db.String(254), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    issue_date = db.Column(db.Date, default=datetime.now)
    due_date = db.Column(db.Date, default=datetime.now)
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    discount = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2), default=0)
    status = db.Column(db.String(10), default='DRAFT')  # 'DRAFT', 'PAID', 'UNPAID', 'CANCELED'
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('auth_user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

# InvoiceItem model
class InvoiceItem(db.Model):
    __tablename__ = 'accounts_invoiceitem'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('accounts_invoice.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('accounts_product.id'))
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Numeric(10, 2))
    total = db.Column(db.Numeric(10, 2))
