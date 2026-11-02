from django.contrib.auth import views as auth
from django.urls import path, reverse_lazy

from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', auth.LoginView.as_view(template_name='accounts/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth.LogoutView.as_view(), name='logout'),
    path('profile/', views.profile, name='profile'),
    path('users/', views.users, name='users'),
    path('users/new/', views.user_form, name='user_new'),
    path('users/<int:pk>/', views.user_form, name='user_edit'),
    path('departments/', views.departments, name='departments'),
    path('departments/new/', views.department_form, name='department_new'),
    path('departments/<int:pk>/', views.department, name='department'),
    path('departments/<int:pk>/edit/', views.department_form, name='department_edit'),
    path('departments/<int:pk>/people/', views.assign, name='assign'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),
    path('password/', auth.PasswordChangeView.as_view(
        template_name='accounts/password_change.html', success_url=reverse_lazy('accounts:password_changed')), name='password_change'),
    path('password/changed/', auth.PasswordChangeDoneView.as_view(template_name='accounts/password_changed.html'),
         name='password_changed'),
    path('reset/', auth.PasswordResetView.as_view(
        template_name='accounts/reset.html', email_template_name='accounts/reset_email.txt',
        subject_template_name='accounts/reset_subject.txt', success_url=reverse_lazy('accounts:reset_sent')), name='reset'),
    path('reset/sent/', auth.PasswordResetDoneView.as_view(template_name='accounts/reset_sent.html'), name='reset_sent'),
    path('reset/<uidb64>/<token>/', auth.PasswordResetConfirmView.as_view(
        template_name='accounts/reset_confirm.html', success_url=reverse_lazy('accounts:reset_done')), name='reset_confirm'),
    path('reset/done/', auth.PasswordResetCompleteView.as_view(template_name='accounts/reset_done.html'), name='reset_done'),
]
