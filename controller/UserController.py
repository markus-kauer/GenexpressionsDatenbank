import jwt
from datetime import datetime, timedelta, timezone
import re
from quart import current_app as app, request, redirect, url_for, render_template, jsonify, current_app, flash
from werkzeug.security import check_password_hash
from services.user_service import UserService

def encode_auth_token(user_id, role):
    try:
        payload = {
            'exp': datetime.now(timezone.utc) + timedelta(days=1),  
            'iat': datetime.now(timezone.utc),  
            'sub': user_id,
            'role': role
        }
        return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    except Exception as e:
        return e

class UserController:
    # Statuscode 401: Unauthorized
    def __init__(self):
        self.user_service = UserService()

    async def get_login(self):
        return await render_template('login.html')

    async def post_login(self):
        data = await request.form
        username = data.get('username').strip()
        password = data.get('password').strip()

        if not self.validate_parameters([(username, 'username'), (password, 'password')]):
            await flash('Invalid input. Please check your username and password.', 'danger')
            return redirect(url_for('login'))

        user = await self.user_service.fetch_user_by_username(username)
        if user:
            if check_password_hash(user['password_hash'], password):
                token = jwt.encode({
                    'sub': user['id'],
                    'role': user['role'],
                    'exp': (datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp() 
                }, app.secret_key, algorithm='HS256')

                response = redirect(url_for('information'))
                response.set_cookie('auth_token', token, httponly=True)
                return response
            else:
                await flash('Incorrect password. Please try again.', 'danger')
        else:
            await flash('User not found. Please check your username.', 'danger')

        return redirect(url_for('login'))

    async def logout(self):
        response = redirect(url_for('login'))
        response.delete_cookie('auth_token')
        return response

    async def create_admin_user(self):
        await self.user_service.create_admin_user_if_not_exists()

    async def get_export_history(self, user_id):
        user_id = str(user_id)
        if not self.validate_parameters([(user_id, 'int')]):
            return await render_template('information.html', message="Invalid parameters")

        history = await self.user_service.get_export_history(user_id)
        return await render_template('export_history.html', history=history)
        
    async def manage_users(self):
        users = await self.user_service.fetch_all_users()
        return await render_template('manage_users.html', users=users)

    async def create_user(self, username, password, role='user'):
        # Validierung der Eingaben
        if not self.validate_parameters([(username, 'username'), (password, 'password'), (role, 'role')]):
            return await render_template('manage_users.html', error="Invalid input", users=await self.user_service.fetch_all_users())

        try:
            await self.user_service.create_user(username, password, role)
            return redirect(url_for('manage_users'))
        except ValueError as e:
            return await render_template('manage_users.html', error=str(e), users=await self.user_service.fetch_all_users())

    async def update_user(self, user_id, username, password, role):
        user_id = str(user_id)
        if not self.validate_parameters([(user_id, 'int'), (username, 'username'), (password, 'password'), (role, 'role')]):
            return await render_template('manage_users.html', error="Invalid input", users=await self.user_service.fetch_all_users())

        await self.user_service.update_user(user_id, username, password, role)
        return redirect(url_for('manage_users'))

    async def delete_user(self, user_id):
        user_id = str(user_id)
        if not self.validate_parameters([(user_id, 'int')]):
            return await render_template('manage_users.html', error="Invalid input", users=await self.user_service.fetch_all_users())

        await self.user_service.delete_user(user_id)
        return redirect(url_for('manage_users'))

    def validate_parameters(self, parameters):
        for value, validation_type in parameters:
            value = str(value)  
            if validation_type == 'username':
                if not re.match(r"^[a-zA-Z0-9_]+$", value):
                    print("Invalid username")
                    return False
            elif validation_type == 'password':
                if not value:
                    print("Invalid password")
                    return False
            elif validation_type == 'role':
                if value not in ['user', 'admin', 'datamanager']:
                    print("Invalid role")
                    return False
            elif validation_type == 'int':
                if not value.isdigit():
                    print("Invalid int")
                    return False
            else:
                return False
        return True
