import os
import aiomysql
from werkzeug.security import generate_password_hash
from services.database_connection_manager import DatabaseConnectionManager

class UserService:
    async def fetch_user_by_username(self, username):
        query = "SELECT * FROM User WHERE username = %s"
        conn = await DatabaseConnectionManager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(query, (username,))
            return await cursor.fetchone()
        finally:
            await cursor.close()
            await DatabaseConnectionManager.release_connection(conn)

    async def create_user(self, username, password, role='user'):
        existing_user = await self.fetch_user_by_username(username)
        if existing_user:
            raise ValueError("Benutzername existiert bereits.")
        password_hash = generate_password_hash(password)
        query = "INSERT INTO User (username, password_hash, role) VALUES (%s, %s, %s)"
        conn = await DatabaseConnectionManager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (username, password_hash, role))
            await conn.commit()
        finally:
            await cursor.close()
            await DatabaseConnectionManager.release_connection(conn)

    async def create_admin_user_if_not_exists(self):
        # Überprüfen, ob der Admin-Benutzer bereits existiert
        admin_user = await self.fetch_user_by_username(os.getenv('ADMIN_USERNAME'))
        if admin_user is not None:
            print("Admin user already exists. Skipping creation.")
            return
        
        conn = await DatabaseConnectionManager.get_write_connection()
        cursor = await conn.cursor()
        try:
            admin_pass = generate_password_hash(os.getenv('ADMIN_PASSWORD'))
            query = "INSERT INTO User (username, password_hash, role) VALUES (%s, %s, %s)"
            await cursor.execute(query, (os.getenv('ADMIN_USERNAME'), admin_pass, 'admin'))
            await conn.commit()
            print("Admin user created successfully.")
        except aiomysql.Error as e:
            print(f"Error creating admin user: {e}")
        finally:
            await cursor.close()
            await DatabaseConnectionManager.release_connection(conn)

    async def get_export_history(self, user_id):
        conn = await DatabaseConnectionManager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        await cursor.execute("SELECT export_date, sample_list, normalization_method, scaling_method FROM ExportHistory WHERE user_id = %s ORDER BY id DESC", (user_id,))
        history = await cursor.fetchall()
        await cursor.close()
        await DatabaseConnectionManager.release_connection(conn)
        return history

    async def update_user(self, user_id, username, password, role):
        conn = await DatabaseConnectionManager.get_write_connection()
        cursor = await conn.cursor()
        password_hash = generate_password_hash(password)
        await cursor.execute("UPDATE User SET username = %s, password_hash = %s, role = %s WHERE id = %s",
                             (username, password_hash, role, user_id))
        await conn.commit()
        await cursor.close()
        await DatabaseConnectionManager.release_connection(conn)

    async def delete_user(self, user_id):
        conn = await DatabaseConnectionManager.get_write_connection()
        cursor = await conn.cursor()
        await cursor.execute("DELETE FROM User WHERE id = %s", (user_id,))
        await conn.commit()
        await cursor.close()
        await DatabaseConnectionManager.release_connection(conn)
        
    async def fetch_all_users(self):
        conn = await DatabaseConnectionManager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        await cursor.execute("SELECT id, username, role FROM User")
        users = await cursor.fetchall()
        await cursor.close()
        await DatabaseConnectionManager.release_connection(conn)
        return users
