from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.home, name='home'), 
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Category URLs
    path('dashboard/categories/', views.category_list, name='category_list'),
    path('dashboard/categories/create/', views.category_create, name='category_create'),
    path('dashboard/categories/update/<int:pk>/', views.category_update, name='category_update'),
    path('dashboard/categories/delete/<int:pk>/', views.category_delete, name='category_delete'),
    
    # Product URLs
    path('dashboard/products/', views.product_list, name='product_list'),
    path('dashboard/products/create/', views.product_create, name='product_create'),
    path('dashboard/products/update/<int:pk>/', views.product_update, name='product_update'),
    path('dashboard/products/delete/<int:pk>/', views.product_delete, name='product_delete'),
    path('dashboard/products/detail/<int:pk>/', views.product_detail, name='product_detail'),
    
    # Stock Transaction URLs
    path('dashboard/stock/transactions/', views.stock_transaction_list, name='stock_transaction_list'),
    path('dashboard/stock/transactions/create/', views.stock_transaction_create, name='stock_transaction_create'),
    path('dashboard/stock/transactions/detail/<int:pk>/', views.stock_transaction_detail, name='stock_transaction_detail'),
    
    # Invoice URLs
    path('dashboard/invoices/', views.invoice_list, name='invoice_list'),
    path('dashboard/invoices/create/', views.invoice_create, name='invoice_create'),
    path('dashboard/invoices/edit/<int:pk>/', views.invoice_edit, name='invoice_edit'),
    path('dashboard/invoices/delete/<int:pk>/', views.invoice_delete, name='invoice_delete'),
    path('dashboard/invoices/detail/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('dashboard/invoices/print/<int:pk>/', views.invoice_print, name='invoice_print'),
    path('dashboard/invoices/status/<int:pk>/', views.invoice_status_update, name='invoice_status_update'),
    
    # API endpoints
    path('api/product-info/', views.get_product_info, name='get_product_info'),
]

# Media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)